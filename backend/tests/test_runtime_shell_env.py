from __future__ import annotations

import subprocess
from pathlib import Path

from app import deps
from app.deps import get_settings


ROOT_DIR = Path(__file__).resolve().parents[2]
HELPER = ROOT_DIR / "scripts" / "dante_kb_runtime_env.sh"


def run_bash(script: str) -> str:
    completed = subprocess.run(
        ["bash", "-c", script],
        cwd=ROOT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def source_helper(command: str) -> str:
    return run_bash(f"source {HELPER!s}; {command}")


def set_required_settings_env(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek-key")
    monkeypatch.setenv("ENABLE_COHERE_RERANK", "false")


class FakeKnowledgeHubClient:
    def __init__(self) -> None:
        self.search_payloads: list[dict] = []

    def dantedash_search_packages(self, payload):
        self.search_payloads.append(dict(payload))
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "node_id": "generic-board",
                        "title": "dooh spectacle board",
                        "score": 0.95,
                        "metadata": {"id": "generic-board", "modality": "text"},
                    },
                    {
                        "node_id": "premium-frame",
                        "title": "barry-lyndon-1975-042 premium decoupage",
                        "score": 0.55,
                        "metadata": {
                            "id": "premium-frame",
                            "artifact_type": "visual_decoupage_bundle",
                            "group": "barry-lyndon-1975",
                            "preview_image_file_id": "preview-premium-frame",
                            "editorial_tier": "premium_s_tier",
                        },
                    },
                ]
            },
        }


def test_kb_runtime_defaults_export_knowledge_hub_without_chroma_fallback() -> None:
    output = source_helper(
        "unset DANTEDASH_KB_BACKEND DANTEDASH_CHROMA_FALLBACK_ENABLED DANTEDASH_CURATORIAL_RERANK; "
        "dante_export_kb_runtime_defaults; "
        'printf "%s %s %s" "$DANTEDASH_KB_BACKEND" "$DANTEDASH_CHROMA_FALLBACK_ENABLED" "$DANTEDASH_CURATORIAL_RERANK"'
    )

    assert output == "knowledge_hub false false"


def test_python_settings_default_to_knowledge_hub_without_chroma_fallback(monkeypatch) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.delenv("DANTEDASH_KB_BACKEND", raising=False)
    monkeypatch.delenv("DANTEDASH_CHROMA_FALLBACK_ENABLED", raising=False)
    monkeypatch.delenv("DANTEDASH_CURATORIAL_RERANK", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.dantedash_kb_backend == "knowledge_hub"
        assert settings.dantedash_chroma_fallback_enabled is False
        assert settings.dantedash_curatorial_rerank is False
    finally:
        get_settings.cache_clear()


def test_python_settings_preserve_explicit_chroma_fallback(monkeypatch) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.setenv("DANTEDASH_KB_BACKEND", "knowledge_hub")
    monkeypatch.setenv("DANTEDASH_CHROMA_FALLBACK_ENABLED", "true")
    monkeypatch.setenv("DANTEDASH_CURATORIAL_RERANK", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.dantedash_kb_backend == "knowledge_hub"
        assert settings.dantedash_chroma_fallback_enabled is True
        assert settings.dantedash_curatorial_rerank is True
    finally:
        get_settings.cache_clear()


def test_gateway_dependency_wires_curatorial_rerank_flag(monkeypatch) -> None:
    set_required_settings_env(monkeypatch)
    monkeypatch.setenv("DANTEDASH_KB_BACKEND", "knowledge_hub")
    monkeypatch.setenv("DANTEDASH_CHROMA_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("DANTEDASH_CURATORIAL_RERANK", "true")
    fake_client = FakeKnowledgeHubClient()
    monkeypatch.setattr(deps, "get_knowledge_hub_client", lambda: fake_client)
    get_settings.cache_clear()
    deps.get_kb_gateway.cache_clear()
    try:
        results = deps.get_kb_gateway().search_text("me mostre shots incriveis s-tier", top_k=2)

        assert [result.node_id for result in results] == ["premium-frame", "generic-board"]
        assert results[0].metadata["curatorial_intent"] == "quality"
        assert results[0].score == results[0].metadata["curatorial_score"]
        assert fake_client.search_payloads[0]["top_k"] == 8
    finally:
        get_settings.cache_clear()
        deps.get_kb_gateway.cache_clear()


def test_kb_runtime_defaults_preserve_explicit_operator_values() -> None:
    output = source_helper(
        "export DANTEDASH_KB_BACKEND=chroma; "
        "export DANTEDASH_CHROMA_FALLBACK_ENABLED=false; "
        "export DANTEDASH_CURATORIAL_RERANK=true; "
        "dante_export_kb_runtime_defaults; "
        'printf "%s %s %s" "$DANTEDASH_KB_BACKEND" "$DANTEDASH_CHROMA_FALLBACK_ENABLED" "$DANTEDASH_CURATORIAL_RERANK"'
    )

    assert output == "chroma false true"


def test_default_chroma_fallback_matches_backend_mode() -> None:
    output = source_helper(
        'printf "%s %s %s %s" '
        '"$(dante_default_chroma_fallback_for_backend knowledge_hub)" '
        '"$(dante_default_chroma_fallback_for_backend chroma)" '
        '"$(dante_default_chroma_fallback_for_backend dual)" '
        '"$(dante_default_chroma_fallback_for_backend "")"'
    )

    assert output == "false false false false"


def test_truthy_helper_is_case_insensitive_and_strict() -> None:
    output = source_helper(
        "for value in 1 true TRUE yes On 0 false no off ''; do "
        "if dante_truthy \"$value\"; then printf 'T'; else printf 'F'; fi; "
        "done"
    )

    assert output == "TTTTTFFFFF"
