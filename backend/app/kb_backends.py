"""Read-only KB backend adapters for DanteDash.

The first migration step keeps Chroma as the safe implementation while giving
routes a backend-neutral surface. Knowledge Hub support intentionally degrades
when its visual package APIs do not yet satisfy the DanteDash DTO contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .kb import KnowledgeBase, ProgressCallback, SearchResult, _noop
from .knowledge_hub_client import KnowledgeHubClient, sanitize_public_payload


class KbBackendUnavailable(RuntimeError):
    """Raised when a selected KB backend cannot serve a read request."""


class KbWriteDisabled(RuntimeError):
    """Raised when a write route is disabled for the selected backend mode."""


@dataclass(frozen=True)
class PreviewLookup:
    path: Path
    metadata: dict[str, Any]
    upload_dir: Path
    preview_path: Path | None = None


class KbBackend(Protocol):
    backend_id: str

    def count(self) -> int: ...

    def count_by_modality(self) -> dict[str, int]: ...

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]: ...

    def search_image(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]: ...

    def list_items(self, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]: ...

    def get_item(self, *, file_id: str | None = None, node_id: str | None = None) -> dict[str, Any] | None: ...

    def lookup_preview(self, file_id: str, *, timestamp_s: float | None = None) -> PreviewLookup: ...


class ChromaKbBackend:
    backend_id = "chroma"

    def __init__(self, kb: KnowledgeBase) -> None:
        self.kb = kb

    def count(self) -> int:
        return self.kb.count()

    def count_by_modality(self) -> dict[str, int]:
        return self.kb.count_by_modality()

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        return self.kb.search_text(
            query,
            top_k=top_k,
            modality_filter=modality_filter,
            on_progress=on_progress,
        )

    def search_image(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        return self.kb.search_image(
            image_path,
            top_k=top_k,
            modality_filter=modality_filter,
            on_progress=on_progress,
        )

    def list_items(self, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self.kb.list_items(limit=limit, offset=offset)

    def get_item(self, *, file_id: str | None = None, node_id: str | None = None) -> dict[str, Any] | None:
        return self.kb.get_item(file_id=file_id, node_id=node_id)

    def lookup_preview(self, file_id: str, *, timestamp_s: float | None = None) -> PreviewLookup:
        data = self.kb.collection.get(where={"id": file_id}, include=["metadatas"])
        metas = data.get("metadatas") or []
        if not metas:
            raise KbBackendUnavailable("item_not_found")
        meta = dict(metas[0] or {})
        file_path = meta.get("file_path")
        if not isinstance(file_path, str) or not file_path:
            raise KbBackendUnavailable("preview_file_missing")
        preview_path = _preview_path_from_meta(meta)
        if meta.get("modality") == "video" and timestamp_s is not None:
            preview_path = self._lookup_video_preview_path(file_id, timestamp_s) or preview_path
        return PreviewLookup(
            path=Path(file_path),
            metadata=meta,
            upload_dir=self.kb.upload_dir,
            preview_path=preview_path,
        )

    def _lookup_video_preview_path(self, file_id: str, timestamp_s: float) -> Path | None:
        data = self.kb.collection.get(where={"id": file_id}, include=["metadatas"])
        candidates: list[tuple[float, dict[str, Any]]] = []
        for meta in data.get("metadatas") or []:
            if not isinstance(meta, dict) or meta.get("modality") != "video":
                continue
            if not _preview_path_from_meta(meta):
                continue
            try:
                distance = abs(float(meta.get("timestamp_seconds") or 0.0) - timestamp_s)
            except (TypeError, ValueError):
                distance = 0.0
            candidates.append((distance, meta))
        if not candidates:
            return None
        _distance, meta = min(candidates, key=lambda item: item[0])
        return _preview_path_from_meta(meta)

    def delete_by_file_id(self, file_id: str) -> int:
        return self.kb.delete_by_file_id(file_id)

    def clear(self) -> None:
        self.kb.clear()


class KnowledgeHubKbBackend:
    backend_id = "knowledge_hub"

    def __init__(self, client: KnowledgeHubClient) -> None:
        self.client = client

    def count(self) -> int:
        raise KbBackendUnavailable("knowledge_hub_stats_not_available")

    def count_by_modality(self) -> dict[str, int]:
        raise KbBackendUnavailable("knowledge_hub_stats_not_available")

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        payload: dict[str, Any] = {"query": query, "top_k": top_k}
        if modality_filter:
            payload["modality_filter"] = modality_filter
        response = self.client.retrieve(payload)
        if not response.get("ok"):
            raise KbBackendUnavailable(str(response.get("error") or "knowledge_hub_unavailable"))
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            raise KbBackendUnavailable("knowledge_hub_items_malformed")
        bounded_items = [item for item in items if isinstance(item, dict)][:top_k]
        return [_item_to_result(item, index) for index, item in enumerate(bounded_items)]

    def search_image(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        raise KbBackendUnavailable("knowledge_hub_image_search_not_available")

    def list_items(self, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        raise KbBackendUnavailable("knowledge_hub_listing_not_available")

    def get_item(self, *, file_id: str | None = None, node_id: str | None = None) -> dict[str, Any] | None:
        raise KbBackendUnavailable("knowledge_hub_item_lookup_not_available")

    def lookup_preview(self, file_id: str, *, timestamp_s: float | None = None) -> PreviewLookup:
        raise KbBackendUnavailable("knowledge_hub_preview_not_available")


def _item_to_result(item: dict[str, Any], index: int) -> SearchResult:
    metadata = sanitize_public_payload(dict(item))
    if not isinstance(metadata, dict):
        metadata = {}
    item_id = _first_text(item, "id", "node_id", "chunk_id", "document_id") or f"kh-item-{index}"
    file_id = _first_text(item, "file_id", "document_id", "id") or item_id
    title = _first_text(item, "display_name", "title", "source_title", "document_title") or file_id
    modality = _first_text(item, "modality", "media_type") or "text"
    snippet = _first_text(item, "snippet", "text", "content", "chunk_text", "summary") or ""
    score = _first_number(item, "score", "rerank_score", "similarity", "vector_score")
    metadata.setdefault("id", file_id)
    metadata.setdefault("original_name", title)
    metadata.setdefault("modality", modality)
    return SearchResult(
        node_id=item_id,
        score=score if score is not None else 0.0,
        modality=modality,
        metadata=metadata,
        snippet=snippet,
    )


def _first_text(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_number(item: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, int | float):
            return float(value)
    return None


def _preview_path_from_meta(meta: dict[str, Any]) -> Path | None:
    preview_file_path = meta.get("preview_file_path")
    if not isinstance(preview_file_path, str) or not preview_file_path:
        return None
    return Path(preview_file_path)
