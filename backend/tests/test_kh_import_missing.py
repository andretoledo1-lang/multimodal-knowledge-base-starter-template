from __future__ import annotations

import json
import subprocess
import sys
import csv
import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "dantedash_kh_import_missing.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dantedash_kh_import_missing_test_module", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_import_missing_execute_without_candidates_is_safe(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(json.dumps({"rows": []}), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--execute",
            "--audit-summary",
            str(audit),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    assert payload["dry_run"] is False
    assert payload["execute_supported"] is True
    assert payload["mutation_performed"] is False
    assert payload["execution"]["status"] == "skipped"


def test_import_missing_dry_run_writes_candidate_manifest(tmp_path: Path) -> None:
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "node_id": "node-a",
                        "file_id": "file-a",
                        "modality": "image",
                        "artifact_type": "unknown",
                        "package_key": "sha-a",
                        "row_class": "canonical",
                        "kh_relationship": "missing_in_kh",
                    },
                    {
                        "node_id": "node-b",
                        "file_id": "file-b",
                        "modality": "text",
                        "artifact_type": "visual_analysis_bundle",
                        "package_key": "sha-b",
                        "row_class": "canonical",
                        "kh_relationship": "matched",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--audit-summary",
            str(audit),
            "--output-dir",
            str(tmp_path / "out"),
        ],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(result.stdout)
    manifest = tmp_path / "out" / "kh-missing-import-dry-run.tsv"
    summary = json.loads((tmp_path / "out" / "kh-missing-import-dry-run-summary.json").read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["mutation_performed"] is False
    assert payload["candidate_count"] == 1
    assert summary["candidate_count"] == 1
    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))
    assert rows == [
        {
            "node_id": "node-a",
            "file_id": "file-a",
            "modality": "image",
            "artifact_type": "unknown",
            "package_key": "sha-a",
            "planned_action": "import_through_kh_dantedash_packages_api",
        }
    ]


def test_import_missing_requires_real_audit_summary() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "--audit-summary is required" in result.stderr or "--audit-summary is required" in result.stdout


def test_import_missing_retries_transient_batch_failure(monkeypatch) -> None:
    module = _load_script_module()
    sleeps: list[float] = []
    monkeypatch.setattr(module.time, "sleep", lambda seconds: sleeps.append(seconds))

    class FlakyClient:
        def __init__(self) -> None:
            self.calls = 0

        def dantedash_import_packages(self, payload):  # noqa: ANN001
            self.calls += 1
            if self.calls == 1:
                return {"ok": False, "error": "request_timeout"}
            return {"ok": True, "data": {"status": "indexed", "indexed_count": len(payload["rows"]), "invalid_count": 0}}

    client = FlakyClient()
    result = module._post_import_batch(
        client,
        {"rows": [{"node_id": "node-a"}]},
        max_retries=2,
        retry_sleep_s=0.01,
    )

    assert result["status"] == "indexed"
    assert result["attempts"] == 2
    assert client.calls == 2
    assert sleeps == [0.01]
