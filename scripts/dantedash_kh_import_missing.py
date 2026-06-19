#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DEFAULT_OUT_DIR = REPO_ROOT / "backend" / "runtime_reports" / "kh-cutover"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a safe dry-run manifest for DanteDash rows missing in KH.")
    parser.add_argument("--audit-summary", help="Existing kh-parity-audit-summary.json with real KH comparison evidence.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--run-id", default="kh-missing-import-dry-run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--execute", action="store_true", help="Reserved for future KH-owned granular import. Currently blocked.")
    args = parser.parse_args()

    if args.execute:
        raise SystemExit(
            "Execute is blocked: no KH-owned granular DanteDash package import or verified Chroma vector reuse path exists yet."
        )
    if not args.audit_summary:
        raise SystemExit("--audit-summary is required so missing rows come from real KH comparison evidence")

    rows = _load_rows(Path(args.audit_summary))
    candidates = [
        row
        for row in rows
        if row.get("row_class") == "canonical" and row.get("kh_relationship") == "missing_in_kh"
    ]
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir.chmod(0o700)
    manifest_path = out_dir / "kh-missing-import-dry-run.tsv"
    summary_path = out_dir / "kh-missing-import-dry-run-summary.json"

    with manifest_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "node_id",
                "file_id",
                "modality",
                "artifact_type",
                "package_key",
                "blocked_reason",
            ],
            delimiter="\t",
        )
        writer.writeheader()
        for row in candidates:
            writer.writerow(
                {
                    "node_id": row.get("node_id", ""),
                    "file_id": row.get("file_id", ""),
                    "modality": row.get("modality", ""),
                    "artifact_type": row.get("artifact_type", ""),
                    "package_key": row.get("package_key", ""),
                    "blocked_reason": "requires_kh_granular_package_import_or_targeted_vector_backfill",
                }
            )
    manifest_path.chmod(0o600)

    by_modality = Counter(str(row.get("modality") or "unknown") for row in candidates)
    by_artifact = Counter(str(row.get("artifact_type") or "unknown") for row in candidates)
    summary = {
        "run_id": args.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "dry_run": True,
        "execute_supported": False,
        "mutation_performed": False,
        "candidate_count": len(candidates),
        "by_modality": dict(by_modality),
        "by_artifact_type": dict(by_artifact),
        "manifest": _display_path(manifest_path),
        "blocked_reason": "No KH-owned granular DanteDash package import or verified Chroma vector reuse path exists yet.",
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.chmod(0o600)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return "[redacted-local-path]"


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError(f"Audit summary has no rows: {path}")
    return [item for item in rows if isinstance(item, dict)]


if __name__ == "__main__":
    raise SystemExit(main())
