from __future__ import annotations

import subprocess
import threading
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.provider_readiness import (
    ProviderProbeConfig,
    ProviderReadinessService,
    clear_runtime_failure,
    record_runtime_failure,
)
from app.routes.provider_status import get_provider_readiness_service


def _config(*, claude_enabled: bool = True) -> ProviderProbeConfig:
    return ProviderProbeConfig(
        deepseek_api_key="secret-not-for-response",
        deepseek_base_url="https://deepseek.test",
        deepseek_model="deepseek-v4-pro",
        codex_bin="codex",
        codex_model="gpt-5.5",
        claude_bin="claude",
        claude_sonnet_model="claude-sonnet-4-6",
        claude_opus_model="claude-opus-4-8",
        claude_haiku_model="claude-haiku-4-5",
        claude_enabled=claude_enabled,
    )


def _http_get(url: str, **_kwargs) -> httpx.Response:
    if url.endswith("/user/balance"):
        return httpx.Response(200, json={"is_available": True, "balance_infos": [{"total_balance": "99"}]})
    return httpx.Response(200, json={"data": [{"id": "deepseek-v4-pro"}]})


def test_readiness_separates_metadata_capacity_from_cli_auth(monkeypatch) -> None:
    seen_envs: list[dict[str, str]] = []

    def fake_run(command, **kwargs):
        seen_envs.append(kwargs["env"])
        if command[0] == "codex":
            return subprocess.CompletedProcess(command, 0, stdout="Logged in using ChatGPT", stderr="")
        return subprocess.CompletedProcess(
            command,
            1,
            stdout='{"loggedIn": false, "account": "private@example.test"}',
            stderr="private-auth-url",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-forward")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "do-not-forward")
    service = ProviderReadinessService(_config(), http_get=_http_get)

    payload = service.status_payload()
    by_id = {row["model_id"]: row for row in payload["providers"]}

    assert by_id["deepseek-v4-pro"]["state"] == "ready"
    assert by_id["deepseek-v4-pro"]["capacity"]["state"] == "available"
    assert by_id["codex-gpt-5.5-oauth"]["state"] == "authenticated_unverified"
    assert by_id["codex-gpt-5.5-oauth"]["capacity"]["state"] == "unknown"
    assert by_id["claude-sonnet-4-6-oauth"]["cause"] == "auth_required"
    assert by_id["claude-opus-4-8-oauth"]["available"] is False
    assert "secret-not-for-response" not in str(payload)
    assert "private@example" not in str(payload)
    assert "private-auth-url" not in str(payload)
    assert all("OPENAI_API_KEY" not in env for env in seen_envs)
    assert all("ANTHROPIC_API_KEY" not in env for env in seen_envs)


def test_operator_disabled_claude_is_unavailable_without_invoking_cli(monkeypatch) -> None:
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="Logged in", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    payload = ProviderReadinessService(
        _config(claude_enabled=False),
        http_get=_http_get,
    ).status_payload()
    claude_rows = [row for row in payload["providers"] if row["provider_family"] == "anthropic"]

    assert len(claude_rows) == 2
    assert all(row["available"] is False for row in claude_rows)
    assert all(row["cause"] == "operator_disabled" for row in claude_rows)
    assert all(row["retryable"] is False for row in claude_rows)
    assert all(command[0] != "claude" for command in commands)


def test_operator_disabled_is_configuration_state_not_runtime_overlay(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="Logged in" if command[0] == "codex" else '{"loggedIn": true}',
            stderr="",
        ),
    )
    record_runtime_failure("claude-sonnet-4-6-oauth", "operator_disabled")
    row = next(
        item
        for item in ProviderReadinessService(_config(), http_get=_http_get).status_payload()["providers"]
        if item["model_id"] == "claude-sonnet-4-6-oauth"
    )

    assert row["available"] is True
    assert row["cause"] == "capacity_unverified"


def test_status_cache_and_refresh_rate_limit_cli_probes(monkeypatch) -> None:
    calls = 0

    def fake_run(command, **_kwargs):
        nonlocal calls
        calls += 1
        stdout = "Logged in" if command[0] == "codex" else '{"loggedIn": true}'
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    service = ProviderReadinessService(
        _config(),
        http_get=_http_get,
        cache_ttl_s=60,
        min_probe_interval_s=60,
    )
    initial = service.status_payload()
    cached_refresh = service.status_payload(refresh=True)

    assert calls == 2
    assert cached_refresh["checked_at"] == initial["checked_at"]
    assert all(
        row["auth"]["checked_at"] == initial["checked_at"]
        for row in cached_refresh["providers"]
    )


def test_provider_families_are_probed_concurrently(monkeypatch) -> None:
    service = ProviderReadinessService(_config(), http_get=_http_get)
    barrier = threading.Barrier(3)

    def parallel_probe(checked_at: str):
        barrier.wait(timeout=1)
        return service._unavailable("verification_unavailable", checked_at)

    monkeypatch.setattr(service, "_probe_deepseek", parallel_probe)
    monkeypatch.setattr(service, "_probe_codex", parallel_probe)
    monkeypatch.setattr(service, "_probe_claude", parallel_probe)

    payload = service.status_payload()

    assert payload["status"] == "verified"


def test_malformed_deepseek_model_metadata_fails_probe_closed(monkeypatch) -> None:
    def malformed_http_get(url: str, **_kwargs) -> httpx.Response:
        if url.endswith("/user/balance"):
            return httpx.Response(200, json={"is_available": True})
        return httpx.Response(200, json=[{"id": "deepseek-v4-pro"}])

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(command, 0, stdout="Logged in", stderr=""),
    )
    payload = ProviderReadinessService(_config(), http_get=malformed_http_get).status_payload()
    deepseek = next(row for row in payload["providers"] if row["provider_family"] == "deepseek")

    assert deepseek["available"] is False
    assert deepseek["cause"] == "verification_unavailable"


@pytest.mark.parametrize(
    ("status_code", "expected_cause"),
    [
        (401, "auth_required"),
        (402, "billing_required"),
        (404, "model_unavailable"),
        (429, "rate_limited"),
        (503, "integration_error"),
    ],
)
def test_deepseek_probe_classifies_http_failures(status_code: int, expected_cause: str) -> None:
    service = ProviderReadinessService(
        _config(),
        http_get=lambda *_args, **_kwargs: httpx.Response(status_code),
    )

    probe = service._probe_deepseek("2026-08-13T00:00:00+00:00")

    assert probe.selectable is False
    assert probe.cause == expected_cause


def test_runtime_failure_overlay_is_redacted_and_clearable(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="Logged in" if command[0] == "codex" else '{"loggedIn": true}',
            stderr="",
        ),
    )
    service = ProviderReadinessService(_config(), http_get=_http_get)
    record_runtime_failure("codex-gpt-5.5-oauth", "rate_limited")
    try:
        row = next(
            item
            for item in service.status_payload()["providers"]
            if item["model_id"] == "codex-gpt-5.5-oauth"
        )
        assert row["available"] is False
        assert row["cause"] == "rate_limited"
    finally:
        clear_runtime_failure("codex-gpt-5.5-oauth")


def test_authoritative_refresh_clears_resolved_auth_overlay(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            0,
            stdout="Logged in" if command[0] == "codex" else '{"loggedIn": true}',
            stderr="",
        ),
    )
    service = ProviderReadinessService(
        _config(),
        http_get=_http_get,
        min_probe_interval_s=0,
    )
    record_runtime_failure("codex-gpt-5.5-oauth", "auth_required")
    try:
        row = next(
            item
            for item in service.status_payload(refresh=True)["providers"]
            if item["model_id"] == "codex-gpt-5.5-oauth"
        )
        assert row["available"] is True
        assert row["state"] == "authenticated_unverified"
        assert row["cause"] == "capacity_unverified"
    finally:
        clear_runtime_failure("codex-gpt-5.5-oauth")


def test_cli_probe_preserves_redacted_oauth_expired_cause(monkeypatch) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **_kwargs: subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr="OAuth token expired for private@example.test",
        ),
    )
    service = ProviderReadinessService(_config(), http_get=_http_get)

    row = next(
        item
        for item in service.status_payload()["providers"]
        if item["model_id"] == "codex-gpt-5.5-oauth"
    )

    assert row["available"] is False
    assert row["cause"] == "oauth_expired"
    assert "private@example.test" not in str(row)


def test_runtime_model_overrides_fail_readiness_closed(monkeypatch) -> None:
    def fail_http(*_args, **_kwargs):
        raise AssertionError("invalid model configuration must not reach provider metadata")

    def fail_cli(*_args, **_kwargs):
        raise AssertionError("invalid model configuration must not invoke provider CLIs")

    monkeypatch.setattr(subprocess, "run", fail_cli)
    config = replace(
        _config(),
        deepseek_model="deepseek-v4-flash",
        codex_model="gpt-unverified",
        claude_sonnet_model="claude-opus-4-8",
        claude_opus_model="claude-sonnet-4-6",
    )
    payload = ProviderReadinessService(config, http_get=fail_http).status_payload()

    assert {row["cause"] for row in payload["providers"]} == {"model_unavailable"}
    assert all(row["available"] is False for row in payload["providers"])


class _FakeService:
    def status_payload(self, *, refresh: bool = False):
        return {
            "status": "verified",
            "checked_at": "2026-08-13T00:00:00+00:00",
            "providers": [],
        }


def test_provider_route_rejects_untrusted_host_origin_and_fetch_metadata() -> None:
    app.dependency_overrides[get_provider_readiness_service] = lambda: _FakeService()
    try:
        client = TestClient(app, client=("127.0.0.1", 50000))
        assert client.get("/api/chat/providers", headers={"Host": "localhost"}).status_code == 200
        assert client.get("/api/chat/providers", headers={"Host": "evil.test"}).status_code == 403
        assert client.get(
            "/api/chat/providers",
            headers={"Host": "localhost", "Origin": "https://evil.test"},
        ).status_code == 403
        assert client.get(
            "/api/chat/providers",
            headers={"Host": "localhost", "Sec-Fetch-Site": "cross-site"},
        ).status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_provider_route_rejects_spoofed_loopback_host_from_remote_client() -> None:
    app.dependency_overrides[get_provider_readiness_service] = lambda: _FakeService()
    try:
        client = TestClient(app, client=("203.0.113.17", 50000))
        response = client.get("/api/chat/providers", headers={"Host": "localhost"})
        assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()
