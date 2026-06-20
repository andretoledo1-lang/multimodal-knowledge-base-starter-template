from __future__ import annotations

from pathlib import Path

import pytest

from app.graph_explorer import GraphExplorer
from app.graph_gateway import GraphGateway, GraphGatewayError


def write_graphml(path: Path) -> None:
    path.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<graphml xmlns="http://graphml.graphdrawing.org/xmlns">
  <key id="n0" for="node" attr.name="entity_id" attr.type="string"/>
  <key id="n1" for="node" attr.name="entity_type" attr.type="string"/>
  <key id="n2" for="node" attr.name="description" attr.type="string"/>
  <key id="e0" for="edge" attr.name="weight" attr.type="double"/>
  <graph edgedefault="undirected">
    <node id="Core"><data key="n0">Core</data><data key="n1">content</data><data key="n2">Graph core node</data></node>
    <node id="Visual/Card"><data key="n0">Visual Card</data><data key="n1">content</data><data key="n2">Visual analysis card node</data></node>
    <edge source="Core" target="Visual/Card"><data key="e0">2</data></edge>
  </graph>
</graphml>
""",
        encoding="utf-8",
    )


class FakeKhGraph:
    def __init__(self, explorer: GraphExplorer | None = None, *, fail: bool = False) -> None:
        self.explorer = explorer
        self.fail = fail
        self.calls: list[str] = []

    def health(self, *, load: bool = False):
        self.calls.append("health")
        if self.fail:
            return {"ok": False, "error": "knowledge_hub_graph_unavailable"}
        assert self.explorer is not None
        payload = self.explorer.health(load=load)
        payload["native"] = True
        return payload

    def summary(self, *, top_nodes_limit: int, max_nodes: int, max_edges: int):
        self.calls.append("summary")
        if self.fail:
            raise GraphGatewayError("knowledge_hub_graph_summary_unavailable")
        assert self.explorer is not None
        payload = self.explorer.summary(top_nodes_limit=top_nodes_limit, max_nodes=max_nodes, max_edges=max_edges)
        payload["source"]["source_name"] = "dantedash-lightrag.json"
        return payload

    def search(self, q: str, *, limit: int, entity_type: str | None = None, route: str | None = None):
        self.calls.append("search")
        if self.fail:
            raise GraphGatewayError("knowledge_hub_graph_search_unavailable")
        assert self.explorer is not None
        return self.explorer.search(q, limit=limit, entity_type=entity_type, route=route)


def _gateway(tmp_path: Path, *, mode: str, kh_fail: bool = False, fallback: bool = False) -> GraphGateway:
    graphml = tmp_path / "graph.graphml"
    write_graphml(graphml)
    explorer = GraphExplorer(graphml)
    return GraphGateway(
        mode=mode,
        graphml=explorer,
        knowledge_hub=FakeKhGraph(explorer, fail=kh_fail),  # type: ignore[arg-type]
        graphml_fallback_enabled=fallback,
    )


def test_graph_gateway_graphml_mode_serves_current_explorer(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, mode="graphml")

    summary = gateway.summary(top_nodes_limit=5, max_nodes=10, max_edges=10)

    assert summary["node_count"] == 2
    assert summary["edge_count"] == 1
    assert summary["backend"]["mode"] == "graphml"
    assert summary["backend"]["primary"] == "graphml"


def test_graph_gateway_knowledge_hub_mode_serves_kh_payload(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, mode="knowledge_hub")

    summary = gateway.summary(top_nodes_limit=5, max_nodes=10, max_edges=10)

    assert summary["source"]["source_name"] == "dantedash-lightrag.json"
    assert summary["backend"]["primary"] == "knowledge_hub"


def test_graph_gateway_dual_mode_keeps_graphml_primary_and_records_shadow(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path, mode="dual")

    search = gateway.search("visual", limit=3)

    assert search["backend"]["mode"] == "dual"
    assert search["backend"]["primary"] == "graphml"
    assert search["backend"]["shadow"]["ok"] is True
    assert search["backend"]["shadow"]["result_count"] == 1


def test_graph_gateway_knowledge_hub_fallback_is_explicit(tmp_path: Path) -> None:
    without_fallback = _gateway(tmp_path, mode="knowledge_hub", kh_fail=True, fallback=False)
    with pytest.raises(GraphGatewayError):
        without_fallback.summary(top_nodes_limit=5, max_nodes=10, max_edges=10)

    with_fallback = _gateway(tmp_path, mode="knowledge_hub", kh_fail=True, fallback=True)
    summary = with_fallback.summary(top_nodes_limit=5, max_nodes=10, max_edges=10)

    assert summary["backend"]["primary"] == "graphml"
    assert summary["backend"]["fallback_from"] == "knowledge_hub"
    assert summary["backend"]["fallback_error"] == "knowledge_hub_graph_summary_unavailable"
