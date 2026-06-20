#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.graph_explorer import GraphExplorerError, build_from_env  # noqa: E402
from app.knowledge_hub_client import KnowledgeHubClient, sanitize_public_payload  # noqa: E402


DEFAULT_REPORT_DIR = REPO_ROOT / "backend" / "runtime_reports" / "kh-graph-parity"
DEFAULT_DOC_REPORT = REPO_ROOT / "docs" / "reports" / "kh-native-lightrag-graph-parity.md"
DEFAULT_QUERIES = [
    "visual cards",
    "treatment ppm pitch",
    "source routing",
    "composition lighting",
    "commercial film production",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Certify GraphML to KH-native graph parity for DanteDash.")
    parser.add_argument("--run-id", default=_default_run_id())
    parser.add_argument("--knowledge-hub-base-url", default=os.getenv("KNOWLEDGE_HUB_BASE_URL", "http://127.0.0.1:8080"))
    parser.add_argument("--report-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--doc-report", default=str(DEFAULT_DOC_REPORT))
    parser.add_argument("--query", action="append", default=[])
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.89)
    parser.add_argument("--no-doc-report", action="store_true")
    args = parser.parse_args()

    top_k = max(1, min(int(args.top_k), 50))
    threshold = max(0.0, min(float(args.threshold), 1.0))
    queries = [q.strip() for q in args.query if q.strip()] or DEFAULT_QUERIES

    graphml = build_from_env()
    client = KnowledgeHubClient(
        base_url=args.knowledge_hub_base_url.rstrip("/"),
        actions_base_url=os.getenv("KNOWLEDGE_HUB_ACTIONS_BASE_URL", "http://127.0.0.1:8098").rstrip("/"),
        actions_bearer_token=os.getenv("KNOWLEDGE_HUB_ACTIONS_BEARER_TOKEN", "").strip() or None,
        timeout_s=float(os.getenv("KNOWLEDGE_HUB_TIMEOUT_S", "10")),
    )

    graphml_health = _safe_graphml(lambda: graphml.health(load=True))
    kh_health = client.dantedash_graph_health(load=True)
    graphml_summary = _safe_graphml(lambda: graphml.summary(top_nodes_limit=top_k, max_nodes=120, max_edges=220))
    kh_summary = client.dantedash_graph_summary(top_nodes_limit=top_k, max_nodes=120, max_edges=220)

    query_rows = [
        _compare_query(graphml=graphml, client=client, query=query, top_k=top_k)
        for query in queries
    ]
    node_id = _first_node_id(graphml_summary)
    node_detail = _compare_node_detail(graphml=graphml, client=client, node_id=node_id) if node_id else {
        "node_id": None,
        "passed": False,
        "reason": "no_graphml_node_available",
    }

    score = _score(
        graphml_health=graphml_health,
        kh_health=kh_health,
        graphml_summary=graphml_summary,
        kh_summary=kh_summary,
        query_rows=query_rows,
        node_detail=node_detail,
    )
    passed = score >= threshold
    payload = {
        "run_id": args.run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "threshold": threshold,
        "passed": passed,
        "score": score,
        "graphml_health": sanitize_public_payload(graphml_health),
        "knowledge_hub_health": sanitize_public_payload(kh_health),
        "graphml_summary": _summary_digest(graphml_summary),
        "knowledge_hub_summary": _kh_summary_digest(kh_summary),
        "query_rows": query_rows,
        "node_detail": node_detail,
        "recommendation": _recommendation(passed=passed, score=score, threshold=threshold),
    }

    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    report_dir.chmod(0o700)
    json_path = report_dir / "kh-graph-parity-certification.json"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    json_path.chmod(0o600)

    doc_path: Path | None = None
    if not args.no_doc_report:
        doc_path = Path(args.doc_report)
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(json.dumps({"passed": passed, "score": score, "threshold": threshold, "json_report": str(json_path), "doc_report": str(doc_path) if doc_path else None}, sort_keys=True))
    return 0 if passed else 2


def _safe_graphml(builder) -> dict[str, Any]:
    try:
        payload = builder()
    except GraphExplorerError as exc:
        return {"ok": False, "error": exc.public_message, "status_code": exc.status_code}
    return {"ok": True, "data": payload}


def _compare_query(*, graphml: Any, client: KnowledgeHubClient, query: str, top_k: int) -> dict[str, Any]:
    graphml_result = _safe_graphml(lambda: graphml.search(query, limit=top_k))
    kh_result = client.dantedash_graph_search(q=query, limit=top_k)
    graphml_ids = _result_ids((graphml_result.get("data") or {}).get("results") if graphml_result.get("ok") else [])
    kh_ids = _result_ids((kh_result.get("data") or {}).get("results") if kh_result.get("ok") else [])
    denominator = max(1, min(len(graphml_ids), top_k))
    overlap = len(set(graphml_ids) & set(kh_ids))
    overlap_ratio = round(overlap / denominator, 4)
    return {
        "query": query,
        "graphml_returned": len(graphml_ids),
        "knowledge_hub_ok": kh_result.get("ok") is True,
        "knowledge_hub_returned": len(kh_ids),
        "overlap": overlap,
        "overlap_ratio": overlap_ratio,
        "passed": kh_result.get("ok") is True and overlap_ratio >= 0.8,
        "graphml_top_ids": graphml_ids[:5],
        "knowledge_hub_top_ids": kh_ids[:5],
        "knowledge_hub_error": kh_result.get("error"),
    }


def _compare_node_detail(*, graphml: Any, client: KnowledgeHubClient, node_id: str) -> dict[str, Any]:
    graphml_result = _safe_graphml(lambda: graphml.node_detail(node_id, edge_limit=20))
    kh_result = client.dantedash_graph_node(node_id, edge_limit=20)
    graphml_data = graphml_result.get("data") if graphml_result.get("ok") else {}
    kh_data = kh_result.get("data") if kh_result.get("ok") else {}
    same_id = isinstance(kh_data, dict) and kh_data.get("id") == node_id
    edge_delta = abs(len(graphml_data.get("adjacent_edges", []) or []) - len(kh_data.get("adjacent_edges", []) or []))
    return {
        "node_id": node_id,
        "knowledge_hub_ok": kh_result.get("ok") is True,
        "same_id": same_id,
        "edge_delta": edge_delta,
        "passed": kh_result.get("ok") is True and same_id and edge_delta == 0,
        "knowledge_hub_error": kh_result.get("error"),
    }


def _score(
    *,
    graphml_health: dict[str, Any],
    kh_health: dict[str, Any],
    graphml_summary: dict[str, Any],
    kh_summary: dict[str, Any],
    query_rows: list[dict[str, Any]],
    node_detail: dict[str, Any],
) -> float:
    kh_health_ok = 1.0 if kh_health.get("ok") and (kh_health.get("data") or {}).get("ok") else 0.0
    count_match = 0.0
    graphml_data = graphml_summary.get("data") if graphml_summary.get("ok") else {}
    kh_data = kh_summary.get("data") if kh_summary.get("ok") else {}
    if kh_summary.get("ok") and graphml_summary.get("ok"):
        count_match = 1.0 if (
            graphml_data.get("node_count") == kh_data.get("node_count")
            and graphml_data.get("edge_count") == kh_data.get("edge_count")
        ) else 0.0
    query_score = sum(float(row.get("overlap_ratio") or 0.0) for row in query_rows) / max(1, len(query_rows))
    detail_score = 1.0 if node_detail.get("passed") else 0.0
    safety_score = 1.0 if "/Users/" not in json.dumps(kh_health, sort_keys=True) and "/Users/" not in json.dumps(kh_summary, sort_keys=True) else 0.0
    return round((kh_health_ok * 0.2) + (count_match * 0.25) + (query_score * 0.35) + (detail_score * 0.1) + (safety_score * 0.1), 4)


def _summary_digest(summary: dict[str, Any]) -> dict[str, Any]:
    data = summary.get("data") if summary.get("ok") else {}
    return {
        "ok": summary.get("ok") is True,
        "node_count": data.get("node_count"),
        "edge_count": data.get("edge_count"),
        "source_name": (data.get("source") or {}).get("source_name") if isinstance(data, dict) else None,
        "top_node_count": len(data.get("top_nodes") or []) if isinstance(data, dict) else 0,
        "error": summary.get("error"),
    }


def _kh_summary_digest(summary: dict[str, Any]) -> dict[str, Any]:
    if not summary.get("ok"):
        return {"ok": False, "error": summary.get("error"), "status_code": summary.get("status_code")}
    return _summary_digest({"ok": True, "data": summary.get("data") or {}})


def _first_node_id(summary: dict[str, Any]) -> str | None:
    data = summary.get("data") if summary.get("ok") else {}
    nodes = data.get("top_nodes") if isinstance(data, dict) else []
    if isinstance(nodes, list) and nodes:
        first = nodes[0]
        if isinstance(first, dict):
            return str(first.get("id") or "") or None
    return None


def _result_ids(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [str(item.get("id") or "") for item in items if isinstance(item, dict) and item.get("id")]


def _recommendation(*, passed: bool, score: float, threshold: float) -> str:
    if passed:
        return "Graph parity passed. DanteDash can use KH-native graph reads by flag while keeping GraphML as rollback."
    return f"Graph parity is below threshold ({score:.4f} < {threshold:.4f}). Keep GraphML primary and repair KH graph import/parity before cutover."


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# KH Native LightRAG Graph Parity Certification",
        "",
        f"- Run id: `{payload['run_id']}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Score: `{payload['score']}`",
        f"- Threshold: `{payload['threshold']}`",
        f"- Passed: `{payload['passed']}`",
        f"- Recommendation: {payload['recommendation']}",
        "",
        "## Counts",
        "",
        "| Source | Nodes | Edges |",
        "|---|---:|---:|",
        f"| GraphML | {payload['graphml_summary'].get('node_count')} | {payload['graphml_summary'].get('edge_count')} |",
        f"| Knowledge Hub | {payload['knowledge_hub_summary'].get('node_count')} | {payload['knowledge_hub_summary'].get('edge_count')} |",
        "",
        "## Query Parity",
        "",
        "| Query | GraphML | KH | Overlap | Passed |",
        "|---|---:|---:|---:|---|",
    ]
    for row in payload["query_rows"]:
        lines.append(
            f"| {row['query']} | {row['graphml_returned']} | {row['knowledge_hub_returned']} | "
            f"{row['overlap_ratio']} | {row['passed']} |"
        )
    lines.extend(
        [
            "",
            "## Node Detail",
            "",
            f"- Node id: `{payload['node_detail'].get('node_id')}`",
            f"- Passed: `{payload['node_detail'].get('passed')}`",
            f"- Edge delta: `{payload['node_detail'].get('edge_delta')}`",
            "",
        ]
    )
    return "\n".join(lines)


def _default_run_id() -> str:
    return f"kh-graph-parity-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}"


if __name__ == "__main__":
    raise SystemExit(main())
