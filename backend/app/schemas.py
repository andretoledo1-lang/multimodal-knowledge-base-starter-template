"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from .chat_models import CHAT_MODEL_DEEPSEEK, ChatModelId

if TYPE_CHECKING:
    from .kb import SearchResult


class SearchResultDTO(BaseModel):
    node_id: str
    score: float
    modality: str
    display_name: str
    file_id: str
    metadata: dict[str, Any]
    snippet: str = ""
    preview_url: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResultDTO]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    modality_filter: list[str] | None = None


class ChatRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    modality_filter: list[str] | None = None
    max_images: int = Field(default=6, ge=0, le=20)
    chat_model: ChatModelId = CHAT_MODEL_DEEPSEEK


class IngestItemDTO(BaseModel):
    file_id: str
    original_name: str
    modality: str
    node_ids: list[str]
    total_pages: int | None = None
    duration_seconds: float | None = None
    preview_url: str | None = None


class IngestResponse(BaseModel):
    items: list[IngestItemDTO]
    total: int


class ItemDTO(BaseModel):
    file_id: str
    original_name: str
    modality: str
    upload_time: str
    node_ids: list[str]
    preview_url: str | None = None


class ItemsResponse(BaseModel):
    items: list[ItemDTO]
    total: int
    returned: int
    limit: int | None = None
    offset: int = 0


class ItemNodeDTO(BaseModel):
    node_id: str
    snippet: str = ""
    metadata: dict[str, Any]


class ItemDetailResponse(BaseModel):
    file_id: str
    original_name: str
    modality: str
    upload_time: str
    node_ids: list[str]
    preview_url: str | None = None
    matched_node_id: str | None = None
    metadata: dict[str, Any]
    nodes: list[ItemNodeDTO]


class StatsResponse(BaseModel):
    total: int
    by_modality: dict[str, int]


class DeleteResponse(BaseModel):
    deleted: int


class ClearResponse(BaseModel):
    cleared: bool


def search_result_to_dto(r: SearchResult) -> SearchResultDTO:
    """Convert an internal SearchResult into the wire-format DTO, stripping
    server-side fields (e.g. on-disk file_path) from metadata."""
    meta = safe_metadata(r.metadata)
    return SearchResultDTO(
        node_id=r.node_id,
        score=r.score,
        modality=r.modality,
        display_name=r.display_name,
        file_id=r.metadata.get("id", ""),
        metadata=meta,
        snippet=r.snippet,
        preview_url=preview_url_for(r.metadata),
    )


def item_detail_to_dto(item: dict[str, Any]) -> ItemDetailResponse:
    """Convert an internal grouped item lookup into a safe public DTO."""
    meta = dict(item.get("metadata") or {})
    nodes = [
        ItemNodeDTO(
            node_id=node["node_id"],
            snippet=node.get("snippet") or "",
            metadata=safe_metadata(node.get("metadata") or {}),
        )
        for node in item.get("nodes") or []
    ]
    return ItemDetailResponse(
        file_id=item["file_id"],
        original_name=item.get("original_name") or item["file_id"],
        modality=item.get("modality") or "unknown",
        upload_time=item.get("upload_time") or "",
        node_ids=item.get("node_ids") or [node.node_id for node in nodes],
        preview_url=preview_url_for(meta),
        matched_node_id=item.get("matched_node_id"),
        metadata=safe_metadata(meta),
        nodes=nodes,
    )


def safe_metadata(meta: dict[str, Any]) -> dict[str, Any]:
    """Strip server-side metadata before returning API payloads."""
    out = dict(meta)
    out.pop("file_path", None)
    return out


def preview_url_for(meta: dict[str, Any]) -> str | None:
    """Build a preview URL for a search/library item based on its metadata."""
    preview_image_file_id = meta.get("preview_image_file_id")
    if meta.get("modality") == "text" and preview_image_file_id:
        return f"/api/preview/{preview_image_file_id}"
    file_id = meta.get("id")
    if not file_id:
        return None
    modality = meta.get("modality")
    if modality == "image":
        return f"/api/preview/{file_id}"
    if modality == "pdf":
        page = int(meta.get("page_start") or 1)
        return f"/api/preview/{file_id}/pdf-page/{page}"
    if modality == "video":
        t = meta.get("timestamp_seconds")
        t_val = float(t) if t is not None else 0.0
        return f"/api/preview/{file_id}/video-frame?t={t_val}"
    return None
