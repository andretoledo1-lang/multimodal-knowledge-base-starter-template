"""Read-only KB backend adapters for DanteDash.

The first migration step keeps Chroma as the safe implementation while giving
routes a backend-neutral surface. Knowledge Hub support intentionally degrades
when its visual package APIs do not yet satisfy the DanteDash DTO contract.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .kb import KnowledgeBase, ProgressCallback, SearchResult, _noop
from .knowledge_hub_client import KnowledgeHubClient, sanitize_public_payload

LOCAL_PATH_RE = re.compile(
    r"(?:~|/(?:Applications|Users|home|opt|private|tmp|var|Volumes)/)[^\s`'\"),;]+",
    re.IGNORECASE,
)


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

    def stats(self) -> dict[str, Any]: ...

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

    def stats(self) -> dict[str, Any]:
        return {"total": self.count(), "by_modality": self.count_by_modality()}

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

    def __init__(self, client: KnowledgeHubClient, *, multimodal_corpora: tuple[str, ...] = ()) -> None:
        self.client = client
        self.multimodal_corpora = tuple(
            corpus for corpus in multimodal_corpora if corpus and corpus != "dantedash"
        )

    def stats(self) -> dict[str, Any]:
        data = self._dantedash_stats()
        by_modality = data.get("by_modality")
        if not isinstance(by_modality, dict):
            raise KbBackendUnavailable("knowledge_hub_stats_malformed")
        counts: dict[str, int] = {}
        for key, value in by_modality.items():
            try:
                counts[str(key)] = int(value)
            except (TypeError, ValueError):
                continue
        try:
            total = int(data.get("total") or 0)
        except (TypeError, ValueError) as exc:
            raise KbBackendUnavailable("knowledge_hub_stats_malformed") from exc
        return {"total": total, "by_modality": counts}

    def count(self) -> int:
        return int(self.stats()["total"])

    def count_by_modality(self) -> dict[str, int]:
        return dict(self.stats()["by_modality"])

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        visual_first = _is_visual_first_query(query, modality_filter)
        request_top_k = _expanded_top_k(top_k) if visual_first else top_k
        payload: dict[str, Any] = {"query": query, "top_k": request_top_k}
        if modality_filter:
            payload["modality_filter"] = modality_filter
        items, error = self._text_search_items(payload)
        if not items and error:
            raise KbBackendUnavailable(error)
        deduped_items = _dedupe_items(items)
        if visual_first:
            deduped_items = _visual_first_items(deduped_items)
        bounded_items = deduped_items[:top_k]
        bounded_items = [self._enrich_multimodal_context(item) for item in bounded_items]
        return [_item_to_result(item, index) for index, item in enumerate(bounded_items)]

    def search_image(
        self,
        image_path: str | Path,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        limit = max(1, min(int(top_k), 50))
        request_top_k = max(1, min(limit * 4 if modality_filter else limit, 50))
        last_error = "knowledge_hub_image_search_unavailable"
        data: dict[str, Any] | None = None
        for attempt in range(2):
            items, attempt_error = self._image_search_items(image_path, top_k=request_top_k)
            if items:
                data = {"items": items}
                break
            if attempt_error:
                last_error = attempt_error
            if attempt == 0:
                time.sleep(0.5)
        if data is None:
            raise KbBackendUnavailable(last_error)
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            raise KbBackendUnavailable("knowledge_hub_image_items_malformed")
        bounded_items = _dedupe_items([item for item in items if isinstance(item, dict)])
        bounded_items = [self._enrich_multimodal_context(item) for item in bounded_items]
        results = [_item_to_result(item, index) for index, item in enumerate(bounded_items)]
        if modality_filter:
            allowed = {str(modality).strip().lower() for modality in modality_filter if str(modality).strip()}
            results = [result for result in results if result.modality.lower() in allowed]
        return results[:limit]

    def list_items(self, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        response = self.client.dantedash_package_items(limit=limit, offset=offset)
        if not response.get("ok"):
            raise KbBackendUnavailable(str(response.get("error") or "knowledge_hub_listing_unavailable"))
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        items = data.get("items") if isinstance(data, dict) else []
        if not isinstance(items, list):
            raise KbBackendUnavailable("knowledge_hub_listing_malformed")
        try:
            total = int(data.get("total") or len(items))
        except (TypeError, ValueError):
            total = len(items)
        return [item for item in items if isinstance(item, dict)], total

    def get_item(self, *, file_id: str | None = None, node_id: str | None = None) -> dict[str, Any] | None:
        item_id = file_id or node_id
        if not item_id:
            return None
        response = self.client.dantedash_package_item(item_id, include_private=False)
        if response.get("status_code") == 404:
            return self._public_multimodal_item(item_id)
        if not response.get("ok"):
            raise KbBackendUnavailable(str(response.get("error") or "knowledge_hub_item_unavailable"))
        data = response.get("data")
        return dict(data) if isinstance(data, dict) else None

    def lookup_preview(self, file_id: str, *, timestamp_s: float | None = None) -> PreviewLookup:
        del timestamp_s
        try:
            item = self._private_dantedash_item(file_id)
        except KbBackendUnavailable as exc:
            if str(exc) != "item_not_found":
                raise
            package = self._private_multimodal_item(file_id)
            return _multimodal_package_preview_lookup(package)
        meta = dict(item.get("metadata") or {})
        file_path = _private_file_path_from_meta(meta)
        preview_path = _private_preview_path_from_meta(meta)
        if meta.get("modality") == "image":
            if file_path is None:
                raise KbBackendUnavailable("preview_file_missing")
            return PreviewLookup(
                path=file_path,
                metadata=meta,
                upload_dir=_preview_upload_root(file_path),
                preview_path=preview_path,
            )

        preview_id = meta.get("preview_image_file_id")
        if isinstance(preview_id, str) and preview_id and preview_id != file_id:
            preview_item = self._private_dantedash_item(preview_id)
            preview_meta = dict(preview_item.get("metadata") or {})
            preview_path = _private_preview_path_from_meta(preview_meta)
            file_path = _private_file_path_from_meta(preview_meta)
            if file_path is not None:
                return PreviewLookup(
                    path=file_path,
                    metadata=preview_meta,
                    upload_dir=_preview_upload_root(file_path),
                    preview_path=preview_path,
                )

        if file_path is None:
            raise KbBackendUnavailable("preview_file_missing")
        return PreviewLookup(
            path=file_path,
            metadata=meta,
            upload_dir=_preview_upload_root(file_path),
            preview_path=_private_preview_path_from_meta(meta),
        )

    def _dantedash_stats(self) -> dict[str, Any]:
        response = self.client.dantedash_package_stats()
        if not response.get("ok"):
            raise KbBackendUnavailable(str(response.get("error") or "knowledge_hub_stats_unavailable"))
        return _kh_data_or_unavailable(response, "knowledge_hub_stats_unavailable")

    def _multimodal_stats(self, corpus_slug: str) -> dict[str, Any] | None:
        method = getattr(self.client, "multimodal_package_stats", None)
        if not callable(method):
            return None
        response = method(corpus_slug)
        if not response.get("ok"):
            return None
        try:
            return _kh_data_or_unavailable(response, "knowledge_hub_multimodal_stats_unavailable")
        except KbBackendUnavailable:
            return None

    def _text_search_items(self, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        last_error: str | None = None
        response = self.client.dantedash_search_packages(payload)
        if not response.get("ok"):
            last_error = str(response.get("error") or "knowledge_hub_unavailable")
        else:
            try:
                data = _kh_data_or_unavailable(response, "knowledge_hub_search_unavailable")
                data_items = data.get("items") if isinstance(data, dict) else []
                if not isinstance(data_items, list):
                    raise KbBackendUnavailable("knowledge_hub_items_malformed")
                items.extend(item for item in data_items if isinstance(item, dict))
            except KbBackendUnavailable as exc:
                last_error = str(exc) or last_error

        method = getattr(self.client, "multimodal_search_packages", None)
        if not callable(method):
            return items, last_error
        for corpus_slug in self._selected_multimodal_corpora(payload):
            response = method(corpus_slug, payload)
            if not response.get("ok"):
                last_error = str(response.get("error") or last_error or "knowledge_hub_multimodal_search_unavailable")
                continue
            try:
                data = _kh_data_or_unavailable(response, "knowledge_hub_multimodal_search_unavailable")
            except KbBackendUnavailable as exc:
                last_error = str(exc) or last_error
                continue
            data_items = data.get("items") if isinstance(data, dict) else []
            if isinstance(data_items, list):
                items.extend(item for item in data_items if isinstance(item, dict))
        return items, last_error

    def _image_search_items(self, image_path: str | Path, *, top_k: int) -> tuple[list[dict[str, Any]], str | None]:
        items: list[dict[str, Any]] = []
        last_error: str | None = None
        response = self.client.dantedash_search_packages_by_image(image_path, top_k=top_k)
        if not response.get("ok"):
            last_error = str(response.get("error") or "knowledge_hub_image_search_unavailable")
        else:
            try:
                data = _kh_data_or_unavailable(response, "knowledge_hub_image_search_unavailable")
                data_items = data.get("items") if isinstance(data, dict) else []
                if not isinstance(data_items, list):
                    raise KbBackendUnavailable("knowledge_hub_image_items_malformed")
                items.extend(item for item in data_items if isinstance(item, dict))
            except KbBackendUnavailable as exc:
                last_error = str(exc) or last_error

        return items, last_error

    def _private_dantedash_item(self, item_id: str) -> dict[str, Any]:
        response = self.client.dantedash_package_item(item_id, include_private=True)
        if response.get("status_code") == 404:
            raise KbBackendUnavailable("item_not_found")
        if not response.get("ok"):
            raise KbBackendUnavailable(str(response.get("error") or "knowledge_hub_preview_unavailable"))
        data = response.get("data")
        if not isinstance(data, dict):
            raise KbBackendUnavailable("knowledge_hub_item_malformed")
        return data

    def _public_multimodal_item(self, item_id: str) -> dict[str, Any] | None:
        method = getattr(self.client, "multimodal_package_item", None)
        if not callable(method):
            return None
        for corpus_slug in self.multimodal_corpora:
            response = method(corpus_slug, item_id, include_private=False)
            if response.get("status_code") == 404:
                continue
            if not response.get("ok"):
                continue
            data = response.get("data")
            item = data.get("item") if isinstance(data, dict) else None
            if isinstance(item, dict):
                return _multimodal_package_to_item_detail(item)
        return None

    def _private_multimodal_item(self, item_id: str) -> dict[str, Any]:
        method = getattr(self.client, "multimodal_package_item", None)
        if not callable(method):
            raise KbBackendUnavailable("item_not_found")
        for corpus_slug in self.multimodal_corpora:
            response = method(corpus_slug, item_id, include_private=True)
            if response.get("status_code") == 404:
                continue
            if not response.get("ok"):
                continue
            data = response.get("data")
            item = data.get("item") if isinstance(data, dict) else None
            if isinstance(item, dict):
                return item
        raise KbBackendUnavailable("item_not_found")

    def _enrich_multimodal_context(self, item: dict[str, Any]) -> dict[str, Any]:
        package_id = _first_text(item, "package_id")
        asset_id = _first_text(item, "asset_id", "preview_ref")
        if not package_id and not asset_id:
            return item
        try:
            private_item = self._private_multimodal_item(asset_id or package_id or "")
        except KbBackendUnavailable:
            return item
        kb_root = _multimodal_kb_root(private_item)
        if kb_root is None:
            return item
        context = _multimodal_layer_context(private_item, kb_root)
        if not context:
            return item
        enriched = dict(item)
        existing_excerpt = _first_text(enriched, "snippet", "excerpt", "text", "content", "chunk_text", "summary")
        enriched["excerpt"] = _join_context_parts([context, existing_excerpt])
        nested = dict(enriched.get("metadata") if isinstance(enriched.get("metadata"), dict) else {})
        nested["analysis_context_available"] = True
        nested["analysis_layer_count"] = len(_context_layers(private_item))
        enriched["metadata"] = nested
        return enriched

    def _selected_multimodal_corpora(self, payload: dict[str, Any]) -> tuple[str, ...]:
        query = str(payload.get("query") or "")
        if not query.strip():
            return ()
        return tuple(
            corpus_slug
            for corpus_slug in self.multimodal_corpora
            if _query_mentions_corpus(query, corpus_slug)
        )


def _item_to_result(item: dict[str, Any], index: int) -> SearchResult:
    nested_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    metadata = sanitize_public_payload({**dict(item), **dict(nested_meta)})
    if not isinstance(metadata, dict):
        metadata = {}
    item_id = _first_text(
        item,
        "node_id",
        "package_id",
        "asset_id",
        "id",
        "chunk_id",
        "document_id",
    ) or f"kh-item-{index}"
    file_id = _first_text(metadata, "id", "file_id", "asset_id", "preview_ref", "document_id", "package_id") or item_id
    title = _first_text(
        metadata,
        "display_label",
        "citation_label",
        "original_name",
        "display_name",
        "title",
        "source_title",
        "document_title",
    )
    title = title or _first_text(item, "display_label", "citation_label", "display_name", "title") or file_id
    modality = _coerce_modality(metadata) or _coerce_modality(item) or "text"
    snippet = _first_text(item, "snippet", "excerpt", "text", "content", "chunk_text", "summary") or ""
    score = _first_number(item, "score", "rerank_score", "similarity", "vector_score")
    visual_asset_key = _visual_display_key(title)
    if visual_asset_key:
        metadata.setdefault("visual_asset_key", visual_asset_key)
    metadata.setdefault("id", file_id)
    metadata.setdefault("file_id", file_id)
    metadata.setdefault("original_name", title)
    metadata.setdefault("modality", modality)
    return SearchResult(
        node_id=item_id,
        score=score if score is not None else 0.0,
        modality=modality,
        metadata=metadata,
        snippet=snippet,
    )


def _kh_data_or_unavailable(response: dict[str, Any], default_error: str) -> dict[str, Any]:
    data = response.get("data")
    if not isinstance(data, dict):
        raise KbBackendUnavailable(default_error)
    status = str(data.get("status") or "ok").strip().lower()
    if status not in {"ok", "indexed", "dry_run", "certified"}:
        raise KbBackendUnavailable(status or default_error)
    return data


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    unkeyed: list[dict[str, Any]] = []
    for item in items:
        key = _item_package_key(item)
        if not key:
            unkeyed.append(item)
            continue
        current = by_key.get(key)
        if current is None or _item_duplicate_rank(item) > _item_duplicate_rank(current):
            by_key[key] = item
    return sorted(
        [*by_key.values(), *unkeyed],
        key=_item_result_sort_rank,
        reverse=True,
    )


def _item_package_key(item: dict[str, Any]) -> str:
    nested_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for source in (item, nested_meta):
        for key in (
            "source_sha256",
            "dante_image_id",
            "linked_image_file_id",
            "preview_image_file_id",
            "visual_asset_key",
        ):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    visual_key = _visual_display_key_from_item(item)
    if visual_key:
        return visual_key
    for source in (item, nested_meta):
        for key in (
            "content_hash",
            "asset_identity",
            "package_id",
            "asset_id",
            "id",
            "file_id",
            "node_id",
        ):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _item_duplicate_rank(item: dict[str, Any]) -> tuple[int, float]:
    score = _first_number(item, "score", "rerank_score", "similarity", "vector_score") or 0.0
    return _item_visual_rank(item), score


def _item_result_sort_rank(item: dict[str, Any]) -> tuple[float, int]:
    score = _first_number(item, "score", "rerank_score", "similarity", "vector_score") or 0.0
    return score, _item_visual_rank(item)


def _item_visual_rank(item: dict[str, Any]) -> int:
    nested_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    modality = _coerce_modality(nested_meta) or _coerce_modality(item) or "text"
    preview = _first_text(item, "preview_url", "preview_ref") or _first_text(nested_meta, "preview_url", "preview_ref")
    media_type = (_first_text(item, "media_type", "mime_type") or _first_text(nested_meta, "media_type", "mime_type") or "").lower()
    artifact_type = _first_text(item, "artifact_type") or _first_text(nested_meta, "artifact_type") or ""
    linked_image = _first_text(item, "linked_image_file_id", "preview_image_file_id") or _first_text(
        nested_meta,
        "linked_image_file_id",
        "preview_image_file_id",
    )
    visual_rank = 0
    if preview:
        visual_rank += 4
    if modality == "image" or media_type.startswith("image"):
        visual_rank += 2
    if artifact_type in {"visual_analysis_bundle", "visual_decoupage_bundle"} or linked_image:
        visual_rank += 2
    if _first_text(item, "display_label", "citation_label") or _first_text(nested_meta, "display_label", "citation_label"):
        visual_rank += 1
    return visual_rank


def _visual_first_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        items,
        key=lambda item: (
            1 if _item_visual_rank(item) > 0 else 0,
            _first_number(item, "score", "rerank_score", "similarity", "vector_score") or 0.0,
            _item_visual_rank(item),
        ),
        reverse=True,
    )


def _expanded_top_k(top_k: int) -> int:
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        value = 5
    return max(value, min(max(value * 6, 24), 50))


def _is_visual_first_query(query: str, modality_filter: list[str] | None) -> bool:
    if modality_filter:
        allowed = {str(value).strip().lower() for value in modality_filter if str(value).strip()}
        if allowed <= {"image", "video"} or "image" in allowed:
            return True
    normalized = " ".join(query.lower().split())
    if not normalized:
        return False
    visual_terms = (
        "imagem",
        "imagens",
        "foto",
        "fotos",
        "frame",
        "frames",
        "shot",
        "shots",
        "still",
        "stills",
        "cena",
        "cenas",
        "visual",
        "visuais",
        "preview",
        "previews",
        "contact sheet",
        "enquadramento",
        "enquadramentos",
        "lente",
        "lentes",
        "grande-angular",
        "grande angular",
        "wide angle",
        "wide-angle",
    )
    action_terms = (
        "mostre",
        "mostrar",
        "mostra",
        "ver",
        "veja",
        "quero ver",
        "separe",
        "separa",
        "show",
        "see",
        "find",
        "give me",
    )
    has_visual_term = any(term in normalized for term in visual_terms)
    has_action_term = any(term in normalized for term in action_terms)
    return has_visual_term and (has_action_term or any(term in normalized for term in ("shot", "shots", "frame", "frames")))


def _query_mentions_corpus(query: str, corpus_slug: str) -> bool:
    normalized_query = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
    normalized_slug = re.sub(r"[^a-z0-9]+", "-", corpus_slug.lower()).strip("-")
    if not normalized_query or not normalized_slug:
        return False
    return normalized_slug in normalized_query.split("-") or normalized_slug in normalized_query


def _visual_display_key_from_item(item: dict[str, Any]) -> str:
    nested_meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    for source in (nested_meta, item):
        title = _first_text(
            source,
            "display_label",
            "citation_label",
            "original_name",
            "display_name",
            "title",
            "source_title",
            "document_title",
        )
        key = _visual_display_key(title or "")
        if key:
            return key
    return ""


def _visual_display_key(title: str) -> str:
    normalized = re.sub(r"[_-]+", " ", title).strip().lower()
    if not normalized:
        return ""
    year_match = re.search(r"\b(?:19|20)\d{2}\b", normalized)
    if not year_match:
        return ""
    frame_match = re.search(r"\bframe\s*0*(\d{1,4})\b", normalized)
    sheet_match = re.search(r"\b(?:contact\s*)?sheet\s*0*(\d{1,3})\b", normalized)
    if frame_match:
        kind = "frame"
        index = int(frame_match.group(1))
        index_text = f"{index:03d}"
    elif sheet_match:
        kind = "sheet"
        index = int(sheet_match.group(1))
        index_text = f"{index:02d}"
    else:
        return ""
    title_prefix = normalized[: year_match.end()]
    title_slug = re.sub(r"[^a-z0-9]+", "-", title_prefix).strip("-")
    if not title_slug:
        return ""
    return f"visual:{title_slug}:{kind}:{index_text}"


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


def _join_context_parts(parts: list[str | None], *, max_chars: int = 6000) -> str:
    clean = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    return "\n\n".join(clean)[:max_chars]


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _multimodal_kb_root(item: dict[str, Any]) -> Path | None:
    private = item.get("private") if isinstance(item.get("private"), dict) else {}
    for key in ("source_path", "asset_path"):
        value = private.get(key)
        if not isinstance(value, str) or not value:
            continue
        root = _root_before_marker(Path(value), {"02-sources", "03-assets", "04-derived"})
        if root and root.exists():
            return root
    return None


def _root_before_marker(path: Path, markers: set[str]) -> Path | None:
    parts = path.expanduser().parts
    for index, part in enumerate(parts):
        if part in markers and index > 0:
            return Path(*parts[:index])
    return None


def _context_layers(item: dict[str, Any]) -> list[dict[str, Any]]:
    layers = item.get("layers")
    if not isinstance(layers, list):
        return []
    out: list[dict[str, Any]] = []
    for layer in layers:
        if isinstance(layer, dict) and layer.get("layer_type") in {"source_map", "derived_analysis"}:
            out.append(layer)
    return out


def _multimodal_layer_context(item: dict[str, Any], kb_root: Path) -> str:
    parts: list[str] = []
    label = _first_text(item, "display_label", "citation_label", "title") or "visual asset"
    for layer in _context_layers(item):
        rel = _first_text(layer, "relative_path")
        if not rel:
            continue
        path = _safe_layer_path(kb_root, rel)
        if path is None:
            continue
        text = _read_layer_text(path)
        if not text:
            continue
        focused = _focused_layer_excerpt(text, item, path)
        if not focused:
            continue
        layer_type = str(layer.get("layer_type") or "analysis")
        parts.append(f"{layer_type} for {label}:\n{focused}")
    return _join_context_parts(parts, max_chars=6500)


def _safe_layer_path(kb_root: Path, relative_path: str) -> Path | None:
    if relative_path.startswith("/") or ".." in Path(relative_path).parts:
        return None
    path = (kb_root / relative_path).resolve()
    root = kb_root.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    if path.suffix.lower() not in {".md", ".txt", ".json"}:
        return None
    if not path.is_file():
        return None
    return path


def _read_layer_text(path: Path, *, max_bytes: int = 320_000) -> str:
    try:
        data = path.read_bytes()[:max_bytes]
    except OSError:
        return ""
    return data.decode("utf-8", errors="replace")


def _focused_layer_excerpt(text: str, item: dict[str, Any], path: Path) -> str:
    if path.suffix.lower() == ".json":
        return _clean_public_layer_excerpt(_json_layer_excerpt(text, item))
    focused = _asset_section_excerpt(text, item)
    if focused:
        return _clean_public_layer_excerpt(focused[:3500])
    return _clean_public_layer_excerpt(_trim_frontmatter(text)[:2200].strip())


def _clean_public_layer_excerpt(text: str) -> str:
    if not text:
        return ""
    file_ref = re.compile(
        r"`[^`]*(?:\.(?:jpe?g|png|webp|gif|mp4|mov|m4v|webm|json|md|txt))[^`]*`",
        re.IGNORECASE,
    )
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        clean = file_ref.sub("", line)
        clean = re.sub(
            r"\b(?:filename|source_file|source_path|asset_path|relative_path|raw_response_path|"
            r"source_size_bytes|kb_slug|file_hash|sha256)\s*:\s*[^\s,;]+",
            "",
            clean,
            flags=re.IGNORECASE,
        )
        clean = _redact_local_paths(clean)
        clean = re.sub(r"\s+—\s+\(", " (", clean)
        clean = re.sub(r"\s+—\s*$", "", clean)
        clean = re.sub(r"^(\s*[-*]\s*)[–—-]\s*", r"\1", clean)
        clean = re.sub(r"[ \t]{2,}", " ", clean).rstrip()
        cleaned_lines.append(clean)
    return "\n".join(cleaned_lines).strip()


def _redact_local_paths(text: str) -> str:
    return LOCAL_PATH_RE.sub("[redacted-local-path]", text)


def _asset_section_excerpt(text: str, item: dict[str, Any]) -> str:
    patterns = _asset_heading_patterns(item)
    if not patterns:
        return ""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not any(pattern.search(line) for pattern in patterns):
            continue
        end = len(lines)
        for next_index in range(index + 1, len(lines)):
            if re.match(r"^#{2,6}\s+", lines[next_index]):
                end = next_index
                break
        return "\n".join(lines[index:end]).strip()
    return ""


def _asset_heading_patterns(item: dict[str, Any]) -> list[re.Pattern[str]]:
    patterns: list[re.Pattern[str]] = []
    frame_index = _first_number(item, "frame_index")
    sheet_index = _first_number(item, "sheet_index")
    if frame_index is not None:
        number = int(frame_index)
        patterns.extend(
            [
                re.compile(rf"\bframe\s+0*{number}\b", re.IGNORECASE),
                re.compile(rf"_frame_0*{number}\b", re.IGNORECASE),
            ]
        )
    if sheet_index is not None:
        number = int(sheet_index)
        patterns.extend(
            [
                re.compile(rf"\b(?:contact\s*)?sheet\s+0*{number}\b", re.IGNORECASE),
                re.compile(rf"_sheet_0*{number}\b", re.IGNORECASE),
            ]
        )
    return patterns


def _trim_frontmatter(text: str) -> str:
    if text.startswith("---"):
        closing = text.find("\n---", 3)
        if closing != -1:
            return text[closing + 4 :].strip()
    return text.strip()


def _json_layer_excerpt(text: str, item: dict[str, Any]) -> str:
    try:
        data = json_loads_safe(text)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    frame_index = _first_number(item, "frame_index")
    if frame_index is not None:
        focused = _find_frame_payload(data, int(frame_index))
        if isinstance(focused, dict):
            return _public_json_summary(focused)
    return _public_json_summary(data)


def json_loads_safe(text: str) -> Any:
    import json

    return json.loads(text)


def _find_frame_payload(value: Any, frame_index: int) -> dict[str, Any] | None:
    if isinstance(value, dict):
        index_value = value.get("frame_index") or value.get("frame") or value.get("index")
        try:
            if index_value is not None and int(index_value) == frame_index:
                return value
        except (TypeError, ValueError):
            pass
        for key in ("frames", "keyframes", "analyzed_frames", "items"):
            child = value.get(key)
            found = _find_frame_payload(child, frame_index)
            if found is not None:
                return found
        for child in value.values():
            found = _find_frame_payload(child, frame_index)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _find_frame_payload(child, frame_index)
            if found is not None:
                return found
    return None


def _public_json_summary(value: dict[str, Any], *, max_chars: int = 2200) -> str:
    blocked = {"source_file", "source_path", "asset_path", "file_path", "absolute_path", "private"}
    parts: list[str] = []
    for key, item in value.items():
        if key in blocked:
            continue
        if isinstance(item, str):
            clean_item = _redact_local_paths(item)
            parts.append(f"{key}: {clean_item}")
        elif isinstance(item, int | float | bool):
            parts.append(f"{key}: {item}")
        elif isinstance(item, list) and all(isinstance(child, str) for child in item[:8]):
            parts.append(f"{key}: {', '.join(_redact_local_paths(child) for child in item[:8])}")
        elif isinstance(item, dict):
            nested = _public_json_summary(item, max_chars=600)
            if nested:
                parts.append(f"{key}: {nested}")
        if sum(len(part) for part in parts) > max_chars:
            break
    return "\n".join(parts)[:max_chars].strip()


def _coerce_modality(item: dict[str, Any]) -> str | None:
    modality = _first_text(item, "modality")
    if modality:
        return modality
    media_type = _first_text(item, "media_type", "mime_type")
    if not media_type:
        return None
    lowered = media_type.lower()
    if lowered.startswith("image"):
        return "image"
    if lowered.startswith("video"):
        return "video"
    if "pdf" in lowered:
        return "pdf"
    if lowered.startswith("text"):
        return "text"
    return None


def _multimodal_package_to_item_detail(item: dict[str, Any]) -> dict[str, Any]:
    file_id = _first_text(item, "asset_id", "preview_ref", "package_id") or "multimodal-package"
    title = _first_text(item, "display_label", "citation_label", "title") or file_id
    meta = {
        **item,
        "id": file_id,
        "file_id": file_id,
        "original_name": title,
        "modality": _coerce_modality(item) or "image",
    }
    return {
        "file_id": file_id,
        "original_name": title,
        "modality": meta["modality"],
        "upload_time": "",
        "node_ids": [str(item.get("package_id") or file_id)],
        "metadata": meta,
        "nodes": [
            {
                "node_id": str(item.get("package_id") or file_id),
                "metadata": meta,
                "snippet": str(item.get("citation_label") or title),
            }
        ],
    }


def _multimodal_package_preview_lookup(item: dict[str, Any]) -> PreviewLookup:
    private = item.get("private") if isinstance(item.get("private"), dict) else {}
    asset_path = private.get("asset_path")
    if not isinstance(asset_path, str) or not asset_path:
        raise KbBackendUnavailable("preview_file_missing")
    path = Path(asset_path)
    file_id = _first_text(item, "asset_id", "preview_ref", "package_id") or path.name
    metadata = {
        **{key: value for key, value in item.items() if key != "private"},
        "id": file_id,
        "file_id": file_id,
        "original_name": _first_text(item, "display_label", "title") or file_id,
        "modality": "image",
    }
    return PreviewLookup(
        path=path,
        metadata=metadata,
        upload_dir=_preview_upload_root(path),
        preview_path=path,
    )


def _preview_path_from_meta(meta: dict[str, Any]) -> Path | None:
    preview_file_path = meta.get("preview_file_path")
    if not isinstance(preview_file_path, str) or not preview_file_path:
        return None
    return Path(preview_file_path)


def _private_file_path_from_meta(meta: dict[str, Any]) -> Path | None:
    for key in ("file_path", "preview_file_path", "source_path"):
        value = meta.get(key)
        if isinstance(value, str) and value:
            return Path(value)
    return None


def _private_preview_path_from_meta(meta: dict[str, Any]) -> Path | None:
    value = meta.get("preview_file_path")
    if isinstance(value, str) and value:
        return Path(value)
    return None


def _preview_upload_root(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    known_roots = [
        Path("/Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/source-assets"),
        Path("/Users/vidigal/Library/CloudStorage/Dropbox/andre/inbox"),
        Path("/Users/vidigal/codex/dantedash/uploads"),
    ]
    for root in known_roots:
        try:
            resolved.relative_to(root.resolve())
        except ValueError:
            continue
        return root
    return Path("/Users/vidigal/codex/dantedash/uploads")
