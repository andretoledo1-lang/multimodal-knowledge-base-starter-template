#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.kb_parity import evaluate_result_parity  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate dry-run search result parity between Chroma and Knowledge Hub.")
    parser.add_argument("--chroma-results", required=True, help="JSON file containing Chroma result objects.")
    parser.add_argument("--knowledge-hub-results", required=True, help="JSON file containing Knowledge Hub result objects.")
    parser.add_argument("--min-asset-overlap", type=float, default=0.8, help="Minimum Chroma asset recall required.")
    parser.add_argument("--output-json", help="Optional path to write the evaluation payload.")
    args = parser.parse_args()

    chroma_results = _read_results(Path(args.chroma_results))
    kh_results = _read_results(Path(args.knowledge_hub_results))
    result = evaluate_result_parity(
        chroma_results,
        kh_results,
        min_asset_overlap=args.min_asset_overlap,
    )

    payload = json.dumps(result, indent=2, sort_keys=True)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + "\n", encoding="utf-8")
        output_path.chmod(0o600)
    print(payload)
    return 0 if result["passed"] else 2


def _read_results(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        for key in ("results", "items", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    raise ValueError(f"Unsupported result JSON shape in {path}")


if __name__ == "__main__":
    raise SystemExit(main())
