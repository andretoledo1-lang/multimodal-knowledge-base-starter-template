"""Read-only graph explorer routes."""
from __future__ import annotations

from functools import lru_cache
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..graph_explorer import GraphExplorer, GraphExplorerError, build_from_env
from ..graph_gateway import GraphGateway, GraphGatewayError, KnowledgeHubGraphBackend
from ..knowledge_hub_client import KnowledgeHubClient

router = APIRouter(prefix="/graph", tags=["graph"])


class GraphSourceDTO(BaseModel):
    source_name: str
    exists: bool
    size_bytes: int | None = None
    mtime_ns: int | None = None
    mtime_iso: str | None = None
    metadata_hash: str | None = None


class GraphCacheDTO(BaseModel):
    loaded: bool
    fresh: bool
    stale: bool
    loaded_at: str | None = None
    metadata_hash: str | None = None


class GraphCountItemDTO(BaseModel):
    id: str
    label: str
    count: int


class ObsidianHintDTO(BaseModel):
    source_file: str
    best_effort_rel_path: str
    obsidian_uri: str


class PreparedQueryDTO(BaseModel):
    surface: str
    query: str


class GraphNodeCardDTO(BaseModel):
    id: str
    label: str
    entity_type: str
    routes: list[str]
    route_labels: list[str]
    source_families: list[str]
    degree: int
    weighted_degree: float
    description: str
    source_files: list[str]
    source_ids: list[str]
    obsidian_hints: list[ObsidianHintDTO]
    prepared_queries: list[PreparedQueryDTO]
    score: float | None = None
    snippet: str | None = None


class GraphEdgeCardDTO(BaseModel):
    id: str
    source: str
    target: str
    other_node_id: str | None = None
    weight: float
    keywords: list[str]
    routes: list[str]
    route_labels: list[str]
    source_files: list[str]
    description: str


class GraphNodeDetailDTO(GraphNodeCardDTO):
    descriptions: list[str] = Field(default_factory=list)
    created_at: str | None = None
    truncate: str | None = None
    adjacent_edges: list[GraphEdgeCardDTO]
    backend: dict[str, Any] | None = None


class GraphVisualNodeDTO(BaseModel):
    id: str
    label: str
    entity_type: str
    routes: list[str]
    route_labels: list[str]
    source_families: list[str]
    degree: int
    weighted_degree: float
    description: str


class GraphVisualEdgeDTO(BaseModel):
    id: str
    source: str
    target: str
    weight: float
    routes: list[str]
    route_labels: list[str]
    keywords: list[str]
    description: str


class GraphPayloadDTO(BaseModel):
    nodes: list[GraphVisualNodeDTO]
    edges: list[GraphVisualEdgeDTO]
    returned_nodes: int
    returned_edges: int
    truncated_edges: bool


class GraphHealthResponse(BaseModel):
    ok: bool
    dataset_id: str
    source: GraphSourceDTO
    native: bool | None = None
    manifest: dict[str, Any] | None = None
    loaded: bool
    cache: GraphCacheDTO
    node_count: int | None = None
    edge_count: int | None = None
    loaded_at: str | None = None
    read_only: bool
    error: str | None = None
    backend: dict[str, Any] | None = None


class GraphSummaryResponse(BaseModel):
    dataset_id: str
    source: GraphSourceDTO
    cache: GraphCacheDTO
    node_count: int
    edge_count: int
    entity_type_counts: list[GraphCountItemDTO]
    route_counts: list[GraphCountItemDTO]
    source_family_counts: list[GraphCountItemDTO]
    top_nodes: list[GraphNodeCardDTO]
    graph: GraphPayloadDTO
    backend: dict[str, Any] | None = None


class GraphSearchResponse(BaseModel):
    query: str
    results: list[GraphNodeCardDTO]
    backend: dict[str, Any] | None = None


class GraphSubgraphResponse(BaseModel):
    dataset_id: str
    center: GraphNodeCardDTO | None = None
    depth: int
    graph: GraphPayloadDTO
    backend: dict[str, Any] | None = None


@lru_cache(maxsize=1)
def get_graph_explorer() -> GraphExplorer:
    return build_from_env()


@lru_cache(maxsize=1)
def get_graph_gateway() -> GraphGateway:
    return GraphGateway(
        mode=os.getenv("DANTEDASH_GRAPH_BACKEND", "graphml").strip().lower() or "graphml",
        graphml=get_graph_explorer,
        knowledge_hub=KnowledgeHubGraphBackend(
            KnowledgeHubClient(
                base_url=os.getenv("KNOWLEDGE_HUB_BASE_URL", "http://127.0.0.1:8080").rstrip("/"),
                actions_base_url=os.getenv("KNOWLEDGE_HUB_ACTIONS_BASE_URL", "http://127.0.0.1:8098").rstrip("/"),
                actions_bearer_token=os.getenv("KNOWLEDGE_HUB_ACTIONS_BEARER_TOKEN", "").strip() or None,
                timeout_s=float(os.getenv("KNOWLEDGE_HUB_TIMEOUT_S", "4")),
            )
        ),
        graphml_fallback_enabled=os.getenv("DANTEDASH_GRAPH_KH_FALLBACK_ENABLED", "false").strip().lower()
        in {"1", "true", "yes", "on"},
    )


@router.get("/health", response_model=GraphHealthResponse)
async def health(load: bool = False) -> dict[str, Any]:
    return await run_in_threadpool(get_graph_gateway().health, load=load)


@router.get("/summary", response_model=GraphSummaryResponse)
async def summary(
    top_nodes_limit: int = Query(default=40, ge=1, le=120),
    max_nodes: int = Query(default=700, ge=40, le=1500),
    max_edges: int = Query(default=1400, ge=40, le=4000),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            get_graph_gateway().summary,
            top_nodes_limit=top_nodes_limit,
            max_nodes=max_nodes,
            max_edges=max_edges,
        )
    except (GraphExplorerError, GraphGatewayError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("/search", response_model=GraphSearchResponse)
async def search(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=80),
    entity_type: str | None = None,
    route: str | None = None,
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            get_graph_gateway().search,
            q,
            limit=limit,
            entity_type=entity_type,
            route=route,
        )
    except (GraphExplorerError, GraphGatewayError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("/subgraph", response_model=GraphSubgraphResponse)
async def subgraph(
    node_id: str | None = None,
    depth: int = Query(default=1, ge=0, le=3),
    max_nodes: int = Query(default=220, ge=10, le=800),
    max_edges: int = Query(default=900, ge=10, le=2500),
    entity_type: str | None = None,
    route: str | None = None,
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            get_graph_gateway().subgraph,
            node_id=node_id,
            depth=depth,
            max_nodes=max_nodes,
            max_edges=max_edges,
            entity_type=entity_type,
            route=route,
        )
    except (GraphExplorerError, GraphGatewayError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc


@router.get("/node/{node_id:path}", response_model=GraphNodeDetailDTO)
async def node_detail(
    node_id: str,
    edge_limit: int = Query(default=80, ge=1, le=250),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(
            get_graph_gateway().node_detail,
            node_id,
            edge_limit=edge_limit,
        )
    except (GraphExplorerError, GraphGatewayError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.public_message) from exc
