"""Pydantic request/response models for the API layer."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

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
    meta = dict(r.metadata)
    meta.pop("file_path", None)
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


def preview_url_for(meta: dict[str, Any]) -> str | None:
    """Build a preview URL for a search/library item based on its metadata."""
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
