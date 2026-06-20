"""Backend-neutral Graph gateway for KH-native graph cutover."""
from __future__ import annotations

import logging
from typing import Any, Callable

from .graph_explorer import GraphExplorer, GraphExplorerError
from .knowledge_hub_client import KnowledgeHubClient

logger = logging.getLogger("graph.gateway")

VALID_GRAPH_BACKEND_MODES = {"graphml", "dual", "knowledge_hub"}
DEFAULT_GRAPH_DATASET_ID = "commercial-film-production-kb"


class GraphGatewayError(RuntimeError):
    """Public-safe graph gateway error."""

    def __init__(self, public_message: str, *, status_code: int = 503) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.status_code = status_code


class KnowledgeHubGraphBackend:
    """Read-only adapter for KH-native DanteDash graph endpoints."""

    def __init__(self, client: KnowledgeHubClient) -> None:
        self.client = client

    def health(self, *, load: bool = False) -> dict[str, Any]:
        response = self.client.dantedash_graph_health(load=load)
        if not response.get("ok"):
            return _unavailable_health(str(response.get("error") or "knowledge_hub_graph_unavailable"))
        data = response.get("data")
        if not isinstance(data, dict):
            return _unavailable_health("knowledge_hub_graph_health_malformed")
        return data

    def summary(self, *, top_nodes_limit: int, max_nodes: int, max_edges: int) -> dict[str, Any]:
        return self._data_or_raise(
            self.client.dantedash_graph_summary(
                top_nodes_limit=top_nodes_limit,
                max_nodes=max_nodes,
                max_edges=max_edges,
            ),
            "knowledge_hub_graph_summary_unavailable",
        )

    def search(
        self,
        q: str,
        *,
        limit: int,
        entity_type: str | None = None,
        route: str | None = None,
    ) -> dict[str, Any]:
        return self._data_or_raise(
            self.client.dantedash_graph_search(q=q, limit=limit, entity_type=entity_type, route=route),
            "knowledge_hub_graph_search_unavailable",
        )

    def subgraph(
        self,
        *,
        node_id: str | None = None,
        depth: int,
        max_nodes: int,
        max_edges: int,
        entity_type: str | None = None,
        route: str | None = None,
    ) -> dict[str, Any]:
        return self._data_or_raise(
            self.client.dantedash_graph_subgraph(
                node_id=node_id,
                depth=depth,
                max_nodes=max_nodes,
                max_edges=max_edges,
                entity_type=entity_type,
                route=route,
            ),
            "knowledge_hub_graph_subgraph_unavailable",
        )

    def node_detail(self, node_id: str, *, edge_limit: int) -> dict[str, Any]:
        return self._data_or_raise(
            self.client.dantedash_graph_node(node_id, edge_limit=edge_limit),
            "knowledge_hub_graph_node_unavailable",
        )

    @staticmethod
    def _data_or_raise(response: dict[str, Any], fallback_error: str) -> dict[str, Any]:
        if not response.get("ok"):
            raise GraphGatewayError(
                str(response.get("error") or fallback_error),
                status_code=int(response.get("status_code") or 503),
            )
        data = response.get("data")
        if not isinstance(data, dict):
            raise GraphGatewayError(f"{fallback_error}_malformed")
        return data


class GraphGateway:
    """Routes Graph View reads across GraphML, KH-native, or dual mode."""

    def __init__(
        self,
        *,
        mode: str,
        graphml: GraphExplorer | Callable[[], GraphExplorer],
        knowledge_hub: KnowledgeHubGraphBackend,
        graphml_fallback_enabled: bool = False,
    ) -> None:
        if mode not in VALID_GRAPH_BACKEND_MODES:
            raise ValueError(f"Invalid DANTEDASH_GRAPH_BACKEND={mode!r}")
        self.mode = mode
        self._graphml = graphml
        self._graphml_instance: GraphExplorer | None = None if callable(graphml) else graphml
        self.knowledge_hub = knowledge_hub
        self.graphml_fallback_enabled = graphml_fallback_enabled

    @property
    def graphml(self) -> GraphExplorer:
        if self._graphml_instance is None:
            if not callable(self._graphml):
                raise GraphGatewayError("graphml_backend_unavailable")
            self._graphml_instance = self._graphml()
        return self._graphml_instance

    def health(self, *, load: bool = False) -> dict[str, Any]:
        if self.mode == "knowledge_hub":
            payload = self.knowledge_hub.health(load=load)
            if payload.get("ok") is False and self.graphml_fallback_enabled:
                fallback = self.graphml.health(load=load)
                return self._with_backend(
                    fallback,
                    primary="graphml",
                    fallback_from="knowledge_hub",
                    fallback_error=str(payload.get("error") or "knowledge_hub_graph_unavailable"),
                )
            return self._with_backend(payload, primary="knowledge_hub")

        payload = self.graphml.health(load=load)
        if self.mode == "dual":
            return self._with_backend(payload, primary="graphml", shadow=self._shadow("health", load=load))
        return self._with_backend(payload, primary="graphml")

    def summary(self, *, top_nodes_limit: int, max_nodes: int, max_edges: int) -> dict[str, Any]:
        return self._read(
            "summary",
            top_nodes_limit=top_nodes_limit,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )

    def search(
        self,
        q: str,
        *,
        limit: int,
        entity_type: str | None = None,
        route: str | None = None,
    ) -> dict[str, Any]:
        return self._read("search", q, limit=limit, entity_type=entity_type, route=route)

    def subgraph(
        self,
        *,
        node_id: str | None = None,
        depth: int,
        max_nodes: int,
        max_edges: int,
        entity_type: str | None = None,
        route: str | None = None,
    ) -> dict[str, Any]:
        return self._read(
            "subgraph",
            node_id=node_id,
            depth=depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            entity_type=entity_type,
            route=route,
        )

    def node_detail(self, node_id: str, *, edge_limit: int) -> dict[str, Any]:
        return self._read("node_detail", node_id, edge_limit=edge_limit)

    def _read(self, method_name: str, *args, **kwargs) -> dict[str, Any]:
        if self.mode == "graphml":
            return self._with_backend(self._read_graphml(method_name, *args, **kwargs), primary="graphml")

        if self.mode == "dual":
            payload = self._read_graphml(method_name, *args, **kwargs)
            shadow = self._shadow(method_name, *args, **kwargs)
            return self._with_backend(payload, primary="graphml", shadow=shadow)

        try:
            return self._with_backend(
                getattr(self.knowledge_hub, method_name)(*args, **kwargs),
                primary="knowledge_hub",
            )
        except GraphGatewayError as exc:
            if not self.graphml_fallback_enabled:
                raise
            logger.info("KH graph %s unavailable; serving GraphML fallback", method_name)
            return self._with_backend(
                self._read_graphml(method_name, *args, **kwargs),
                primary="graphml",
                fallback_from="knowledge_hub",
                fallback_error=exc.public_message,
            )

    def _read_graphml(self, method_name: str, *args, **kwargs) -> dict[str, Any]:
        try:
            return getattr(self.graphml, method_name)(*args, **kwargs)
        except GraphExplorerError as exc:
            raise GraphGatewayError(exc.public_message, status_code=exc.status_code) from exc

    def _shadow(self, method_name: str, *args, **kwargs) -> dict[str, Any]:
        try:
            payload = getattr(self.knowledge_hub, method_name)(*args, **kwargs)
            return _shadow_payload(ok=True, payload=payload)
        except Exception as exc:  # noqa: BLE001
            logger.debug("KH graph shadow %s unavailable: %s", method_name, exc)
            return _shadow_payload(ok=False, error=str(getattr(exc, "public_message", "knowledge_hub_graph_unavailable")))

    def _with_backend(
        self,
        payload: dict[str, Any],
        *,
        primary: str,
        shadow: dict[str, Any] | None = None,
        fallback_from: str | None = None,
        fallback_error: str | None = None,
    ) -> dict[str, Any]:
        result = dict(payload)
        result["backend"] = {
            "mode": self.mode,
            "primary": primary,
            "shadow": shadow,
            "fallback_enabled": self.graphml_fallback_enabled,
            "fallback_from": fallback_from,
            "fallback_error": fallback_error,
        }
        return result


def _shadow_payload(
    *,
    ok: bool,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    compact: dict[str, Any] = {"ok": ok}
    if error:
        compact["error"] = error
    if payload:
        for key in ("ok", "dataset_id", "node_count", "edge_count", "query"):
            if key in payload:
                compact[key] = payload[key]
        if isinstance(payload.get("results"), list):
            compact["result_count"] = len(payload["results"])
        graph = payload.get("graph")
        if isinstance(graph, dict):
            compact["returned_nodes"] = graph.get("returned_nodes")
            compact["returned_edges"] = graph.get("returned_edges")
    return compact


def _unavailable_health(error: str) -> dict[str, Any]:
    return {
        "ok": False,
        "dataset_id": DEFAULT_GRAPH_DATASET_ID,
        "source": {
            "source_name": "knowledge-hub-native-graph",
            "exists": False,
            "size_bytes": None,
            "mtime_ns": None,
            "mtime_iso": None,
            "metadata_hash": None,
        },
        "loaded": False,
        "cache": {"loaded": False, "fresh": False, "stale": False},
        "node_count": None,
        "edge_count": None,
        "loaded_at": None,
        "read_only": True,
        "error": error,
    }
