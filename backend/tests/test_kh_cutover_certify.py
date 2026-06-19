from __future__ import annotations

import importlib.util
from pathlib import Path

from app.kb import SearchResult


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dantedash_kh_cutover_certify.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("dantedash_kh_cutover_certify", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _EmptyKb:
    def search_text(self, _query: str, *, top_k: int):
        return []


class _FailingKb:
    def search_text(self, _query: str, *, top_k: int):
        raise RuntimeError("boom")


class _HitKb:
    def search_text(self, _query: str, *, top_k: int):
        return [
            SearchResult(
                node_id="node-a",
                score=0.9,
                modality="image",
                metadata={"id": "file-a", "source_sha256": "sha-a", "original_name": "A", "modality": "image"},
                snippet="alpha",
            )
        ]


class _Client:
    def __init__(self, items):
        self.items = items

    def retrieve(self, _payload):
        return {"ok": True, "data": {"items": self.items}}


def test_query_suite_fails_when_chroma_baseline_is_empty_or_errors() -> None:
    module = _load_module()

    empty_rows = module._run_query_suite(_EmptyKb(), _Client([]), top_k=1)
    failing_rows = module._run_query_suite(_FailingKb(), _Client([]), top_k=1)

    assert all(row["score"] == 0.0 and row["passed"] is False for row in empty_rows)
    assert {row["chroma_baseline_status"] for row in empty_rows} == {"empty"}
    assert all(row["score"] == 0.0 and row["passed"] is False for row in failing_rows)
    assert {row["chroma_baseline_status"] for row in failing_rows} == {"failed"}


def test_query_suite_can_pass_when_assets_overlap() -> None:
    module = _load_module()

    rows = module._run_query_suite(_HitKb(), _Client([{"metadata": {"source_sha256": "sha-a"}}]), top_k=1)

    assert all(row["score"] == 1.0 and row["passed"] is True for row in rows)


def test_public_no_leak_scan_detects_sensitive_strings() -> None:
    module = _load_module()

    clean = module._scan_public_no_leak({"status": "ok", "relative_path": "safe/file.md"})
    dirty = module._scan_public_no_leak({"status": "ok", "message": "postgresql://secret.example"})

    assert clean["checks_complete"] is True
    assert clean["leak_count"] == 0
    assert dirty["leak_count"] >= 1
    assert dirty["public_errors_safe"] is False
