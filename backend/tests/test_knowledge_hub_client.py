from __future__ import annotations

from pathlib import Path

import httpx

from app import knowledge_hub_client as knowledge_hub_client_module
from app.knowledge_hub_client import KnowledgeHubClient, sanitize_public_payload


def make_client(handler) -> KnowledgeHubClient:
    return KnowledgeHubClient(
        base_url="http://kh.test",
        actions_base_url="http://actions.test",
        actions_bearer_token="secret-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_default_client_disables_environment_proxy_routing(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeHttpClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self) -> None:
            pass

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.setattr(knowledge_hub_client_module.httpx, "Client", FakeHttpClient)

    client = KnowledgeHubClient(
        base_url="http://127.0.0.1:8080",
        actions_base_url="http://127.0.0.1:8098",
        actions_bearer_token="secret-token",
    )

    assert captured["trust_env"] is False
    assert captured["follow_redirects"] is False
    client.close()


def test_healthy_kh_api_returns_sanitized_payloads() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "runtime_root": "/Users/vidigal/.knowledge-hub",
                    "hub_profile": "local_full_power",
                },
            )
        if request.url.path == "/topology":
            return httpx.Response(200, json={"stance": "unified", "postgres_dsn": "postgres://secret"})
        if request.url.path == "/kbs":
            return httpx.Response(200, json={"items": [{"kb_slug": "film", "root": "/Users/vidigal/knowledge-base"}]})
        raise AssertionError(request.url.path)

    client = make_client(handler)

    assert client.health()["data"] == {"status": "ok", "hub_profile": "local_full_power"}
    assert client.topology()["data"] == {"stance": "unified"}
    assert client.kbs()["data"] == {"items": [{"kb_slug": "film"}]}


def test_down_service_returns_unavailable_without_raw_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused with local details")

    result = make_client(handler).health()

    assert result == {
        "ok": False,
        "surface": "knowledge_hub",
        "status": "unavailable",
        "status_code": None,
        "error": "service_unavailable",
    }


def test_timeout_returns_redacted_public_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out at /private/socket")

    result = make_client(handler).health()

    assert result["ok"] is False
    assert result["error"] == "request_timeout"
    assert "private" not in str(result)


def test_actions_openapi_filters_to_read_only_operations() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-token"
        return httpx.Response(
            200,
            json={
                "paths": {
                    "/health": {"get": {"operationId": "health", "summary": "Health"}},
                    "/retrieve": {"post": {"operationId": "retrieve", "summary": "Retrieve"}},
                    "/inbox/bundles": {"post": {"operationId": "submitBundle", "summary": "Mutating"}},
                    "/jobs/run-once": {"post": {"operationId": "runJob", "summary": "Mutating"}},
                }
            },
        )

    result = make_client(handler).actions_openapi_operations()

    assert result["ok"] is True
    assert result["data"]["operations"] == [
        {"method": "GET", "path": "/health", "operation_id": "health", "summary": "Health"},
        {"method": "POST", "path": "/retrieve", "operation_id": "retrieve", "summary": "Retrieve"},
    ]


def test_dantedash_image_search_posts_multipart_file(tmp_path: Path) -> None:
    query_image = tmp_path / "query.jpg"
    query_image.write_bytes(b"fake-image")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/dantedash/packages/search-image"
        assert "multipart/form-data" in request.headers["content-type"]
        assert request.extensions["timeout"]["read"] == 15.0
        body = request.read()
        assert b'name=\"top_k\"' in body
        assert b"3" in body
        assert b"query.jpg" in body
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "items": [
                    {
                        "node_id": "kh-image-a",
                        "metadata": {"id": "kh-image-a", "file_path": "/Users/vidigal/private.jpg"},
                    }
                ],
            },
        )

    result = make_client(handler).dantedash_search_packages_by_image(query_image, top_k=3)

    assert result["ok"] is True
    assert result["data"]["items"][0]["metadata"] == {"id": "kh-image-a"}


def test_dantedash_image_search_missing_file_returns_public_error(tmp_path: Path) -> None:
    result = make_client(lambda _request: httpx.Response(500)).dantedash_search_packages_by_image(
        tmp_path / "missing.jpg",
        top_k=3,
    )

    assert result == {
        "ok": False,
        "surface": "knowledge_hub",
        "status": "unavailable",
        "status_code": None,
        "error": "image_query_file_unavailable",
    }


def test_dantedash_recovery_reads_are_unauthenticated() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert "authorization" not in request.headers
        paths.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    client = make_client(handler)
    assert client.dantedash_package_audit()["ok"] is True
    assert client.dantedash_package_snapshots()["ok"] is True
    assert paths == ["/dantedash/packages/audit", "/dantedash/packages/snapshots"]


def test_dantedash_recovery_mutations_send_bearer_only_to_loopback() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret-token"
        paths.append(request.url.path)
        return httpx.Response(200, json={"status": "ok"})

    client = KnowledgeHubClient(
        base_url="http://127.0.0.1:8080",
        actions_base_url="http://actions.test",
        actions_bearer_token="secret-token",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.dantedash_import_packages({"execute": True, "rows": []})["ok"] is True
    assert client.dantedash_create_package_snapshot({"run_id": "run-a"})["ok"] is True
    assert client.dantedash_acquire_recovery_lease({"run_id": "run-a"})["ok"] is True
    assert client.dantedash_release_recovery_lease({"run_id": "run-a", "lease_token": "opaque"})["ok"] is True
    assert paths == [
        "/dantedash/packages/import",
        "/dantedash/packages/snapshots",
        "/dantedash/packages/recovery/lease",
        "/dantedash/packages/recovery/lease/release",
    ]


def test_dantedash_recovery_mutations_refuse_non_loopback_bearer_target() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "ok"})

    client = make_client(handler)

    result = client.dantedash_create_package_snapshot({"run_id": "run-a"})

    assert result["ok"] is False
    assert result["error"] == "local_action_endpoint_required"
    assert calls == 0


def test_dantedash_recovery_mutations_refuse_missing_bearer() -> None:
    client = KnowledgeHubClient(
        base_url="http://127.0.0.1:8080",
        actions_base_url="http://actions.test",
        actions_bearer_token=None,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500))),
    )

    result = client.dantedash_acquire_recovery_lease({"run_id": "run-a"})

    assert result["ok"] is False
    assert result["error"] == "actions_bearer_required"


def test_dantedash_import_rejects_non_boolean_execute_without_request() -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"status": "ok"})

    client = make_client(handler)

    result = client.dantedash_import_packages({"execute": 1, "rows": []})

    assert result["ok"] is False
    assert result["error"] == "execute_flag_must_be_boolean"
    assert calls == 0


def test_sanitize_public_payload_removes_sensitive_keys_and_paths() -> None:
    payload = {
        "safe": "value",
        "token": "secret",
        "api_path": "/health",
        "nested": {
            "source_path": "/Users/vidigal/private.md",
            "relative_path": "notes/file.md",
            "text": "open /Users/vidigal/private.md",
        },
    }

    assert sanitize_public_payload(payload) == {
        "safe": "value",
        "api_path": "/health",
        "nested": {
            "relative_path": "notes/file.md",
            "text": "[redacted-local-path]",
        },
    }
