"""Provider preflight and safe failure classification helpers."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal

ProviderCause = Literal[
    "ready",
    "operator_disabled",
    "auth_required",
    "oauth_expired",
    "billing_required",
    "quota_exhausted",
    "rate_limited",
    "model_unavailable",
    "timeout",
    "binary_missing",
    "config_missing",
    "verification_unavailable",
    "capacity_unverified",
    "integration_error",
]


def classify_provider_failure(
    detail: str = "",
    *,
    status_code: int | None = None,
) -> ProviderCause:
    """Reduce provider output to a fixed, non-sensitive cause code."""
    text = detail.casefold()
    if any(
        marker in text
        for marker in ("oauth token expired", "oauth expired", "expired oauth", "token has expired")
    ):
        return "oauth_expired"
    if status_code in {401, 403} or any(
        marker in text
        for marker in ("not logged in", "login required", "unauthorized", "authentication", "oauth")
    ):
        return "auth_required"
    if status_code == 402 or any(
        marker in text for marker in ("billing", "payment required", "insufficient balance")
    ):
        return "billing_required"
    if any(marker in text for marker in ("quota", "usage limit", "credit balance")):
        return "quota_exhausted"
    if status_code == 429 or any(marker in text for marker in ("rate limit", "too many requests")):
        return "rate_limited"
    if status_code in {404, 422} or any(
        marker in text for marker in ("model not found", "unknown model", "invalid model")
    ):
        return "model_unavailable"
    if any(marker in text for marker in ("timed out", "timeout")):
        return "timeout"
    return "integration_error"


def recovery_hint_for_cause(cause: ProviderCause) -> str:
    """Return a fixed operator hint without echoing provider output."""
    return {
        "ready": "Provider is ready.",
        "operator_disabled": "This provider is temporarily disabled by the operator.",
        "auth_required": "Sign in to this provider, then refresh provider status.",
        "oauth_expired": "Sign in to this provider again, then refresh provider status.",
        "billing_required": "Review provider billing, then refresh provider status.",
        "quota_exhausted": "Wait for quota renewal or add capacity, then refresh.",
        "rate_limited": "Wait briefly, then refresh provider status.",
        "model_unavailable": "Verify that the configured model is available to this account.",
        "timeout": "Check provider connectivity, then retry.",
        "binary_missing": "Install the provider CLI or correct its configured path.",
        "config_missing": "Configure this provider, then refresh provider status.",
        "verification_unavailable": "Provider status could not be verified. Retry the check.",
        "capacity_unverified": "Authentication is valid, but execution capacity has not been smoke-tested.",
        "integration_error": "Check the provider integration, then retry.",
    }[cause]


@dataclass(frozen=True)
class ChatPreflightResult:
    provider: str
    ok: bool
    model: str
    details: tuple[str, ...]


def preflight_deepseek_config(
    *,
    api_key_present: bool,
    base_url: str,
    model: str,
) -> ChatPreflightResult:
    details: list[str] = []
    if not api_key_present:
        details.append("DEEPSEEK_API_KEY is missing")
    if not base_url.startswith("https://"):
        details.append("DeepSeek base URL should be HTTPS")
    if model not in {"deepseek-v4-pro", "deepseek-v4-flash"}:
        details.append("DeepSeek model is not one of the verified V4 IDs")
    return ChatPreflightResult(
        provider="deepseek",
        ok=not details,
        model=model,
        details=tuple(details or ("ready",)),
    )


def preflight_codex_oauth_runtime(
    *,
    codex_bin: str,
    model: str,
) -> ChatPreflightResult:
    details: list[str] = []
    if shutil.which(codex_bin) is None:
        details.append(f"Codex binary not found: {codex_bin}")
    if model != "gpt-5.5":
        details.append("Codex OAuth principal model should be gpt-5.5")
    return ChatPreflightResult(
        provider="openai_codex",
        ok=not details,
        model=model,
        details=tuple(details or ("ready",)),
    )


def preflight_claude_oauth_runtime(
    *,
    claude_bin: str,
    sonnet_model: str,
    opus_model: str,
    haiku_model: str,
) -> ChatPreflightResult:
    details: list[str] = []
    if shutil.which(claude_bin) is None:
        details.append(f"Claude binary not found: {claude_bin}")
    expected = {
        "sonnet": "claude-sonnet-4-6",
        "opus": "claude-opus-4-8",
        "haiku": "claude-haiku-4-5",
    }
    if sonnet_model != expected["sonnet"]:
        details.append("Claude Sonnet OAuth model should be claude-sonnet-4-6")
    if opus_model != expected["opus"]:
        details.append("Claude Opus OAuth model should be claude-opus-4-8")
    if haiku_model != expected["haiku"]:
        details.append("Claude Haiku OAuth worker model should be claude-haiku-4-5")
    return ChatPreflightResult(
        provider="anthropic",
        ok=not details,
        model=opus_model,
        details=tuple(details or ("ready",)),
    )
