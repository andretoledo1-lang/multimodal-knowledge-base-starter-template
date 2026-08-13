"""Cached, redacted readiness checks for user-visible chat providers."""
from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Callable, Literal

import httpx

from .chat_models import (
    CHAT_MODEL_CLAUDE_OPUS,
    CHAT_MODEL_CLAUDE_SONNET,
    CHAT_MODEL_CODEX_OAUTH,
    CHAT_MODEL_DEEPSEEK,
)
from .chat_profiles import active_chat_profiles, get_chat_profile
from .provider_preflight import (
    ProviderCause,
    classify_provider_failure,
    recovery_hint_for_cause,
)
from .providers import _claude_oauth_env, _codex_oauth_env

ReadinessState = Literal["ready", "authenticated_unverified", "unavailable"]
AuthState = Literal["authenticated", "unauthenticated", "unknown"]
CapacityState = Literal["available", "unavailable", "unknown"]


@dataclass(frozen=True)
class ProviderProbeConfig:
    deepseek_api_key: str
    deepseek_base_url: str
    deepseek_model: str
    codex_bin: str
    codex_model: str
    claude_bin: str
    claude_sonnet_model: str
    claude_opus_model: str
    claude_haiku_model: str


@dataclass(frozen=True)
class ProviderProbe:
    state: ReadinessState
    selectable: bool
    cause: ProviderCause
    auth_state: AuthState
    capacity_state: CapacityState
    checked_at: str
    retryable: bool = True


@dataclass(frozen=True)
class RuntimeOverlay:
    cause: ProviderCause
    expires_at: float


_overlay_lock = threading.Lock()
_runtime_overlays: dict[str, RuntimeOverlay] = {}


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def record_runtime_failure(model_id: str, cause: ProviderCause) -> None:
    """Record only a safe cause code; raw provider output never enters state."""
    ttl = {
        "rate_limited": 30.0,
        "timeout": 60.0,
        "auth_required": 300.0,
        "billing_required": 300.0,
        "quota_exhausted": 300.0,
        "model_unavailable": 300.0,
    }.get(cause, 90.0)
    with _overlay_lock:
        _runtime_overlays[model_id] = RuntimeOverlay(cause=cause, expires_at=time.monotonic() + ttl)


def clear_runtime_failure(model_id: str) -> None:
    with _overlay_lock:
        _runtime_overlays.pop(model_id, None)


def _active_overlay(model_id: str) -> RuntimeOverlay | None:
    now = time.monotonic()
    with _overlay_lock:
        overlay = _runtime_overlays.get(model_id)
        if overlay and overlay.expires_at > now:
            return overlay
        _runtime_overlays.pop(model_id, None)
    return None


class ProviderReadinessService:
    """Serialize probes and cache their redacted result for a short TTL."""

    def __init__(
        self,
        config: ProviderProbeConfig,
        *,
        cache_ttl_s: float = 30.0,
        min_probe_interval_s: float = 5.0,
        cli_timeout_s: float = 5.0,
        http_timeout_s: float = 5.0,
        http_get: Callable[..., httpx.Response] = httpx.get,
    ) -> None:
        self.config = config
        self.cache_ttl_s = cache_ttl_s
        self.min_probe_interval_s = min_probe_interval_s
        self.cli_timeout_s = cli_timeout_s
        self.http_timeout_s = http_timeout_s
        self.http_get = http_get
        self._lock = threading.Lock()
        self._cached: dict[str, ProviderProbe] | None = None
        self._cached_at = 0.0
        self._cached_checked_at: str | None = None
        self._last_probe_at = 0.0

    def status_payload(self, *, refresh: bool = False) -> dict[str, object]:
        probes, checked_at, probed_now = self._probes(refresh=refresh)
        providers: list[dict[str, object]] = []
        for profile in active_chat_profiles():
            probe = probes[profile.provider_family]
            overlay = _active_overlay(profile.public_id)
            if (
                refresh
                and probed_now
                and probe.auth_state == "authenticated"
                and overlay is not None
                and overlay.cause == "auth_required"
            ):
                clear_runtime_failure(profile.public_id)
                overlay = None
            if overlay is not None:
                probe = replace(
                    probe,
                    state="unavailable",
                    selectable=False,
                    cause=overlay.cause,
                    capacity_state="unavailable",
                    retryable=overlay.cause not in {"billing_required", "quota_exhausted"},
                )
            providers.append(
                {
                    "model_id": profile.public_id,
                    "label": profile.label,
                    "provider_family": profile.provider_family,
                    "state": probe.state,
                    "available": probe.selectable,
                    "cause": probe.cause,
                    "retryable": probe.retryable,
                    "recovery_hint": recovery_hint_for_cause(probe.cause),
                    "auth": {"state": probe.auth_state, "checked_at": probe.checked_at},
                    "capacity": {"state": probe.capacity_state, "checked_at": probe.checked_at},
                    "last_smoke": {"state": "not_run", "checked_at": None},
                }
            )
        return {"status": "verified", "checked_at": checked_at, "providers": providers}

    def _probes(self, *, refresh: bool) -> tuple[dict[str, ProviderProbe], str, bool]:
        now = time.monotonic()
        with self._lock:
            cache_age = now - self._cached_at
            since_probe = now - self._last_probe_at
            if self._cached is not None and (
                (not refresh and cache_age < self.cache_ttl_s)
                or (refresh and since_probe < self.min_probe_interval_s)
            ):
                assert self._cached_checked_at is not None
                return dict(self._cached), self._cached_checked_at, False

            self._last_probe_at = now
            checked_at = _now_iso()
            probes = {
                "deepseek": self._probe_deepseek(checked_at),
                "openai_codex": self._probe_codex(checked_at),
                "anthropic": self._probe_claude(checked_at),
            }
            self._cached = probes
            self._cached_at = time.monotonic()
            self._cached_checked_at = checked_at
            return dict(probes), checked_at, True

    def _probe_deepseek(self, checked_at: str) -> ProviderProbe:
        if not self.config.deepseek_api_key:
            return self._unavailable("config_missing", checked_at, auth_state="unknown")
        expected_model = get_chat_profile(CHAT_MODEL_DEEPSEEK).principal_model
        if self.config.deepseek_model != expected_model:
            return self._unavailable("model_unavailable", checked_at, retryable=False)
        headers = {"Authorization": f"Bearer {self.config.deepseek_api_key}"}
        base = self.config.deepseek_base_url.rstrip("/")
        try:
            balance = self.http_get(
                f"{base}/user/balance",
                headers=headers,
                timeout=self.http_timeout_s,
            )
            if balance.status_code >= 400:
                return self._http_failure(balance, checked_at)
            balance_payload = balance.json()
            if not isinstance(balance_payload, dict) or balance_payload.get("is_available") is not True:
                return self._unavailable(
                    "billing_required",
                    checked_at,
                    auth_state="authenticated",
                    capacity_state="unavailable",
                    retryable=False,
                )

            models = self.http_get(
                f"{base}/models",
                headers=headers,
                timeout=self.http_timeout_s,
            )
            if models.status_code >= 400:
                return self._http_failure(models, checked_at)
            model_payload = models.json()
            model_ids = {
                row.get("id")
                for row in model_payload.get("data", [])
                if isinstance(row, dict) and isinstance(row.get("id"), str)
            }
            if self.config.deepseek_model not in model_ids:
                return self._unavailable(
                    "model_unavailable",
                    checked_at,
                    auth_state="authenticated",
                    capacity_state="unavailable",
                    retryable=False,
                )
        except (httpx.TimeoutException, TimeoutError):
            return self._unavailable("timeout", checked_at)
        except (httpx.HTTPError, ValueError, TypeError):
            return self._unavailable("verification_unavailable", checked_at)
        return ProviderProbe(
            state="ready",
            selectable=True,
            cause="ready",
            auth_state="authenticated",
            capacity_state="available",
            checked_at=checked_at,
            retryable=False,
        )

    def _http_failure(self, response: httpx.Response, checked_at: str) -> ProviderProbe:
        cause = classify_provider_failure(status_code=response.status_code)
        return self._unavailable(
            cause,
            checked_at,
            auth_state="unauthenticated" if cause == "auth_required" else "unknown",
            capacity_state="unavailable",
            retryable=cause not in {"billing_required", "quota_exhausted", "model_unavailable"},
        )

    def _probe_codex(self, checked_at: str) -> ProviderProbe:
        expected_model = get_chat_profile(CHAT_MODEL_CODEX_OAUTH).principal_model
        if self.config.codex_model != expected_model:
            return self._unavailable("model_unavailable", checked_at, retryable=False)
        return self._probe_cli_auth(
            [self.config.codex_bin, "login", "status"],
            env=_codex_oauth_env(),
            checked_at=checked_at,
            json_auth_key=None,
        )

    def _probe_claude(self, checked_at: str) -> ProviderProbe:
        sonnet_profile = get_chat_profile(CHAT_MODEL_CLAUDE_SONNET)
        opus_profile = get_chat_profile(CHAT_MODEL_CLAUDE_OPUS)
        expected_worker_model = sonnet_profile.worker.model if sonnet_profile.worker else None
        if (
            self.config.claude_sonnet_model != sonnet_profile.principal_model
            or self.config.claude_opus_model != opus_profile.principal_model
            or self.config.claude_haiku_model != expected_worker_model
        ):
            return self._unavailable("model_unavailable", checked_at, retryable=False)
        return self._probe_cli_auth(
            [self.config.claude_bin, "auth", "status", "--json"],
            env=_claude_oauth_env(),
            checked_at=checked_at,
            json_auth_key="loggedIn",
        )

    def _probe_cli_auth(
        self,
        command: list[str],
        *,
        env: dict[str, str],
        checked_at: str,
        json_auth_key: str | None,
    ) -> ProviderProbe:
        try:
            proc = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                text=True,
                timeout=self.cli_timeout_s,
            )
        except FileNotFoundError:
            return self._unavailable("binary_missing", checked_at, retryable=False)
        except subprocess.TimeoutExpired:
            return self._unavailable("timeout", checked_at)
        except OSError:
            return self._unavailable("verification_unavailable", checked_at)

        authenticated = False
        malformed = False
        if json_auth_key is None:
            authenticated = proc.returncode == 0 and "logged in" in f"{proc.stdout}\n{proc.stderr}".casefold()
        else:
            try:
                payload = json.loads(proc.stdout)
                authenticated = proc.returncode == 0 and payload.get(json_auth_key) is True
            except (json.JSONDecodeError, AttributeError):
                malformed = True

        # Raw stdout/stderr is deliberately discarded after classification.
        if authenticated:
            return ProviderProbe(
                state="authenticated_unverified",
                selectable=True,
                cause="capacity_unverified",
                auth_state="authenticated",
                capacity_state="unknown",
                checked_at=checked_at,
                retryable=False,
            )
        if malformed:
            return self._unavailable("verification_unavailable", checked_at)
        return self._unavailable("auth_required", checked_at, auth_state="unauthenticated")

    @staticmethod
    def _unavailable(
        cause: ProviderCause,
        checked_at: str,
        *,
        auth_state: AuthState = "unknown",
        capacity_state: CapacityState = "unknown",
        retryable: bool = True,
    ) -> ProviderProbe:
        return ProviderProbe(
            state="unavailable",
            selectable=False,
            cause=cause,
            auth_state=auth_state,
            capacity_state=capacity_state,
            checked_at=checked_at,
            retryable=retryable,
        )


def classify_runtime_exception(exc: BaseException) -> ProviderCause:
    cause = getattr(exc, "cause", None)
    if isinstance(cause, str) and cause in {
        "auth_required",
        "billing_required",
        "quota_exhausted",
        "rate_limited",
        "model_unavailable",
        "timeout",
        "integration_error",
    }:
        return cause  # type: ignore[return-value]
    return classify_provider_failure(str(exc))
