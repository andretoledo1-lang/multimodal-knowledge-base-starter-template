from __future__ import annotations

import subprocess
import os
from pathlib import Path

from app.deps import get_settings
from app.main import validate_effective_bind_address


ROOT_DIR = Path(__file__).resolve().parents[2]
HELPER = ROOT_DIR / "scripts" / "dante_kb_runtime_env.sh"
LAUNCHER = ROOT_DIR / "scripts" / "start-dante-multimodal-rag.sh"


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


def test_kb_runtime_defaults_export_knowledge_hub_without_chroma_fallback() -> None:
    output = source_helper(
        "unset DANTEDASH_KB_BACKEND DANTEDASH_CHROMA_FALLBACK_ENABLED; "
        "dante_export_kb_runtime_defaults; "
        'printf "%s %s" "$DANTEDASH_KB_BACKEND" "$DANTEDASH_CHROMA_FALLBACK_ENABLED"'
    )

    assert output == "knowledge_hub false"


def test_python_settings_default_to_knowledge_hub_without_chroma_fallback(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("COHERE_API_KEY", "test")
    monkeypatch.delenv("DANTEDASH_KB_BACKEND", raising=False)
    monkeypatch.delenv("DANTEDASH_CHROMA_FALLBACK_ENABLED", raising=False)
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.dantedash_kb_backend == "knowledge_hub"
        assert settings.dantedash_chroma_fallback_enabled is False
    finally:
        get_settings.cache_clear()


def test_python_settings_preserve_explicit_chroma_fallback(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test")
    monkeypatch.setenv("COHERE_API_KEY", "test")
    monkeypatch.setenv("DANTEDASH_KB_BACKEND", "knowledge_hub")
    monkeypatch.setenv("DANTEDASH_CHROMA_FALLBACK_ENABLED", "true")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.dantedash_kb_backend == "knowledge_hub"
        assert settings.dantedash_chroma_fallback_enabled is True
    finally:
        get_settings.cache_clear()


def test_kb_runtime_defaults_preserve_explicit_operator_values() -> None:
    output = source_helper(
        "export DANTEDASH_KB_BACKEND=chroma; "
        "export DANTEDASH_CHROMA_FALLBACK_ENABLED=false; "
        "dante_export_kb_runtime_defaults; "
        'printf "%s %s" "$DANTEDASH_KB_BACKEND" "$DANTEDASH_CHROMA_FALLBACK_ENABLED"'
    )

    assert output == "chroma false"


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


def test_launcher_accepts_loopback_validation_only() -> None:
    env = dict(os.environ)
    env["DANTE_LAUNCHER_VALIDATE_ONLY"] = "true"
    result = subprocess.run([str(LAUNCHER)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 0


def test_launcher_rejects_non_loopback_bind() -> None:
    env = dict(os.environ)
    env.update(
        {
            "DANTE_LAUNCHER_VALIDATE_ONLY": "true",
            "DANTE_MULTIMODAL_BACKEND_HOST": "0.0.0.0",
        }
    )
    result = subprocess.run([str(LAUNCHER)], env=env, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert "refuses non-loopback binds" in result.stderr


def test_backend_rejects_non_loopback_effective_bind(monkeypatch) -> None:
    monkeypatch.setenv("DANTE_MULTIMODAL_EFFECTIVE_BIND_ADDRESS", "0.0.0.0")
    try:
        validate_effective_bind_address()
    except RuntimeError as exc:
        assert "non-loopback" in str(exc)
    else:
        raise AssertionError("non-loopback bind should be rejected")
