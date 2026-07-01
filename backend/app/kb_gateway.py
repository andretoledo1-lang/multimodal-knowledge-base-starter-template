"""Backend-neutral KB gateway for Chroma/KH parity work."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

from .kb import KnowledgeBase, ProgressCallback, SearchResult, _noop
from .kb_backends import (
    ChromaKbBackend,
    KbBackend,
    KbBackendUnavailable,
    KbWriteDisabled,
    KnowledgeHubKbBackend,
    PreviewLookup,
)

logger = logging.getLogger("kb.gateway")
VALID_BACKEND_MODES = {"chroma", "dual", "knowledge_hub"}


class KbGateway:
    """Read-oriented gateway used by routes during KH parity migration."""

    def __init__(
        self,
        *,
        mode: str,
        chroma: ChromaKbBackend | Callable[[], ChromaKbBackend],
        knowledge_hub: KnowledgeHubKbBackend,
        chroma_fallback_enabled: bool = True,
        chroma_visual_rescue_enabled: bool = False,
        strict_no_chroma: bool | None = None,
        chat_runtime: Any | None = None,
    ) -> None:
        if mode not in VALID_BACKEND_MODES:
            raise ValueError(f"Invalid DANTEDASH_KB_BACKEND={mode!r}")
        self.mode = mode
        self._chroma = chroma
        self._chroma_instance: Any | None = None if callable(chroma) else chroma
        self.knowledge_hub = knowledge_hub
        self.strict_no_chroma = (
            mode == "knowledge_hub" and not chroma_fallback_enabled
            if strict_no_chroma is None
            else bool(strict_no_chroma)
        )
        self.chroma_fallback_enabled = bool(chroma_fallback_enabled) and not self.strict_no_chroma
        self.chroma_visual_rescue_enabled = bool(chroma_visual_rescue_enabled) and not self.strict_no_chroma
        self.chat_runtime = chat_runtime

    @property
    def chroma(self) -> ChromaKbBackend:
        if self.strict_no_chroma and self.mode == "knowledge_hub":
            raise KbBackendUnavailable("chroma_disabled_in_strict_knowledge_hub_mode")
        if self._chroma_instance is None:
            if not callable(self._chroma):
                raise KbBackendUnavailable("chroma_backend_unavailable")
            self._chroma_instance = self._chroma()
        return self._chroma_instance

    @property
    def chroma_kb(self) -> KnowledgeBase:
        return self.chroma.kb

    @property
    def claude_premium_repair_cap(self) -> int:
        if self.chat_runtime is not None:
            return self.chat_runtime.claude_premium_repair_cap
        return self.chroma.kb.claude_premium_repair_cap

    @property
    def claude_opus_chat_client(self) -> Any:
        if self.chat_runtime is not None:
            return self.chat_runtime.claude_opus_chat_client
        return self.chroma.kb.claude_opus_chat_client

    @property
    def claude_sonnet_chief_client(self) -> Any:
        if self.chat_runtime is not None:
            return self.chat_runtime.claude_sonnet_chief_client
        return self.chroma.kb.claude_sonnet_chief_client

    @property
    def claude_haiku_worker_client(self) -> Any:
        if self.chat_runtime is not None:
            return self.chat_runtime.claude_haiku_worker_client
        return self.chroma.kb.claude_haiku_worker_client

    @property
    def claude_opus_judge_client(self) -> Any:
        if self.chat_runtime is not None:
            return self.chat_runtime.claude_opus_judge_client
        return self.chroma.kb.claude_opus_judge_client

    def chat_client_for_model(self, chat_model: str) -> Any:
        if self.chat_runtime is not None:
            return self.chat_runtime.chat_client_for_model(chat_model)
        return self.chroma.kb.chat_client_for_model(chat_model)

    @property
    def is_knowledge_hub_primary(self) -> bool:
        return self.mode == "knowledge_hub"

    @property
    def is_chroma_fallback_enabled(self) -> bool:
        return self.is_knowledge_hub_primary and self.chroma_fallback_enabled

    def status(self) -> dict[str, Any]:
        """Return public-safe routing status for smoke checks and operators."""
        primary_backend = "knowledge_hub" if self.mode == "knowledge_hub" else "chroma"
        shadow_backend = "knowledge_hub" if self.mode == "dual" else None
        if self.mode == "knowledge_hub":
            surfaces = {
                "text_search": "knowledge_hub",
                "chat_sources": "knowledge_hub",
                "stats": "knowledge_hub",
                "library": "knowledge_hub",
                "preview": "knowledge_hub",
                "image_query_search": "knowledge_hub",
                "visual_text_rescue": "chroma_visual_rescue"
                if self.chroma_visual_rescue_enabled
                else "disabled",
            }
        else:
            surfaces = {
                "text_search": "chroma",
                "chat_sources": "chroma",
                "stats": "chroma",
                "library": "chroma",
                "preview": "chroma",
                "image_query_search": "chroma",
                "visual_text_rescue": "disabled",
            }
        return {
            "mode": self.mode,
            "primary_backend": primary_backend,
            "shadow_backend": shadow_backend,
            "chroma_fallback_enabled": self.chroma_fallback_enabled,
            "chroma_available_as_fallback": self.is_chroma_fallback_enabled,
            "chroma_visual_rescue_enabled": self.chroma_visual_rescue_enabled,
            "strict_no_chroma": self.strict_no_chroma,
            "writes_enabled": self.mode != "knowledge_hub",
            "surfaces": surfaces,
        }

    def count(self) -> int:
        return self._read("count")

    def count_by_modality(self) -> dict[str, int]:
        return self._read("count_by_modality")

    def stats(self) -> dict[str, Any]:
        return self._read("stats")

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
        if self._should_use_chroma_visual_rescue(query, modality_filter):
            rescue = self._chroma_visual_rescue(
                query,
                top_k=top_k,
                modality_filter=modality_filter,
                on_progress=on_progress,
            )
            if rescue:
                return rescue
        return self._read(
            "search_text",
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
        return self._read(
            "search_image",
            image_path,
            top_k=top_k,
            modality_filter=modality_filter,
            on_progress=on_progress,
        )

    def list_items(self, *, limit: int | None = None, offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        return self._read("list_items", limit=limit, offset=offset)

    def get_item(self, *, file_id: str | None = None, node_id: str | None = None) -> dict[str, Any] | None:
        return self._read("get_item", file_id=file_id, node_id=node_id)

    def lookup_preview(self, file_id: str, *, timestamp_s: float | None = None) -> PreviewLookup:
        return self._read("lookup_preview", file_id, timestamp_s=timestamp_s)

    def delete_by_file_id(self, file_id: str) -> int:
        if self.mode == "knowledge_hub":
            raise KbWriteDisabled("write_disabled_in_knowledge_hub_mode")
        return self.chroma.delete_by_file_id(file_id)

    def clear(self) -> None:
        if self.mode == "knowledge_hub":
            raise KbWriteDisabled("write_disabled_in_knowledge_hub_mode")
        self.chroma.clear()

    def _read(self, method_name: str, *args, **kwargs):
        if self.mode == "chroma":
            return getattr(self.chroma, method_name)(*args, **kwargs)
        if self.mode == "dual":
            result = getattr(self.chroma, method_name)(*args, **kwargs)
            self._shadow(method_name, *args, **kwargs)
            return result
        try:
            return getattr(self.knowledge_hub, method_name)(*args, **kwargs)
        except KbBackendUnavailable:
            if self.chroma_fallback_enabled:
                logger.info("KH %s unavailable; serving Chroma fallback", method_name)
                return getattr(self.chroma, method_name)(*args, **kwargs)
            raise

    def _shadow(self, method_name: str, *args, **kwargs) -> None:
        try:
            getattr(self.knowledge_hub, method_name)(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("KH shadow %s unavailable: %s", method_name, exc)

    def _should_use_chroma_visual_rescue(self, query: str, modality_filter: list[str] | None) -> bool:
        if self.mode != "knowledge_hub" or not self.chroma_visual_rescue_enabled:
            return False
        normalized = " ".join(query.lower().split())
        if not normalized:
            return False
        if any(marker in normalized for marker in ("pirata", "pirata-kb", "super mario galaxy")):
            return False
        if modality_filter:
            allowed = {str(value).strip().lower() for value in modality_filter if str(value).strip()}
            if "image" in allowed or allowed <= {"image", "video"}:
                return True
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
        return has_visual_term and (
            has_action_term
            or any(term in normalized for term in ("shot", "shots", "frame", "frames", "still", "stills"))
        )

    def _chroma_visual_rescue(
        self,
        query: str,
        *,
        top_k: int,
        modality_filter: list[str] | None,
        on_progress: ProgressCallback,
    ) -> list[SearchResult]:
        try:
            expanded_top_k = _expanded_visual_rescue_top_k(top_k)
            candidates = self.chroma.search_text(
                query,
                top_k=expanded_top_k,
                modality_filter=modality_filter,
                on_progress=on_progress,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("Chroma visual rescue unavailable; serving KH search: %s", exc)
            return []
        visual = [_clean_visual_rescue_result(result) for result in candidates if _search_result_is_visual(result)]
        if not visual:
            return []
        rescue = _dedupe_search_results(visual)
        logger.info("Serving Chroma visual rescue for KH query q=%r results=%d", query, len(rescue[:top_k]))
        return rescue[:top_k]


def _expanded_visual_rescue_top_k(top_k: int) -> int:
    try:
        value = int(top_k)
    except (TypeError, ValueError):
        value = 5
    return max(value, min(max(value * 5, 20), 50))


def _search_result_is_visual(result: SearchResult) -> bool:
    meta = result.metadata
    artifact_type = str(meta.get("artifact_type") or "")
    return (
        result.modality in {"image", "video"}
        or artifact_type in {"visual_analysis_bundle", "visual_decoupage_bundle"}
        or bool(meta.get("linked_image_file_id"))
        or bool(meta.get("preview_image_file_id"))
    )


def _dedupe_search_results(results: list[SearchResult]) -> list[SearchResult]:
    by_key: dict[str, SearchResult] = {}
    unkeyed: list[SearchResult] = []
    for result in results:
        key = _search_result_package_key(result)
        if not key:
            unkeyed.append(result)
            continue
        current = by_key.get(key)
        if current is None or _search_result_rank(result) > _search_result_rank(current):
            by_key[key] = result
    return sorted([*by_key.values(), *unkeyed], key=_search_result_rank, reverse=True)


def _search_result_package_key(result: SearchResult) -> str:
    meta = result.metadata
    for key in (
        "source_sha256",
        "dante_image_id",
        "linked_image_file_id",
        "preview_image_file_id",
        "file_id",
        "id",
    ):
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return result.node_id


def _search_result_rank(result: SearchResult) -> tuple[float, int]:
    meta = result.metadata
    artifact_type = str(meta.get("artifact_type") or "")
    artifact_rank = {
        "visual_decoupage_bundle": 2,
        "visual_analysis_bundle": 1,
    }.get(artifact_type, 0)
    return (float(result.score or 0.0), artifact_rank)


def _clean_visual_rescue_result(result: SearchResult) -> SearchResult:
    meta = dict(result.metadata)
    meta["retrieval_source"] = "chroma_visual_rescue"
    public_modality = (
        "image"
        if meta.get("preview_image_file_id") or meta.get("linked_image_file_id")
        else result.modality
    )
    return SearchResult(
        node_id=result.node_id,
        score=result.score,
        modality=public_modality,
        metadata=meta,
        snippet=_clean_visual_rescue_snippet(result.snippet),
    )


def _clean_visual_rescue_snippet(snippet: str) -> str:
    text = snippet.strip()
    if not text:
        return ""
    judgment = ""
    match = re.search(r"\bJudgment:\s*([^\n]+)", text, re.IGNORECASE)
    if match:
        judgment = f"Judgment: {match.group(1).strip()}"
    if "## Searchable visual fields" in text:
        text = text.split("## Searchable visual fields", 1)[1]
        for end_marker in ("\n## Markdown card", "\n## Markdown decoupage", "\n---\n"):
            if end_marker in text:
                text = text.split(end_marker, 1)[0]
        text = f"## Searchable visual fields\n{text}"
    else:
        for marker in ("# Premium Decoupage", "## Decoupage", "## Visual Analysis"):
            if marker in text:
                text = text.split(marker, 1)[1]
                if marker.startswith("## "):
                    text = f"{marker}\n{text}"
                break
    cleaned_lines: list[str] = []
    blocked_prefixes = (
        "[Dante visual analysis bundle]",
        "[Dante premium decoupage bundle]",
        "Image ID:",
        "Category:",
        "Group:",
        "Image:",
        "Markdown card:",
        "JSON card:",
        "Markdown decoupage:",
        "JSON decoupage:",
        "Card run:",
        "Source run:",
        "Ingest run:",
        "source_sha256:",
        "linked_image_file_id:",
        "preview_image_file_id:",
    )
    file_ref = re.compile(
        r"`?[^`\s]*(?:\.(?:jpe?g|png|webp|gif|mp4|mov|m4v|webm|json|md|txt))`?",
        re.IGNORECASE,
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if any(stripped.startswith(prefix) for prefix in blocked_prefixes):
            continue
        cleaned = file_ref.sub("", line)
        cleaned = re.sub(r"/Users/[^\s)]+", "", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).rstrip()
        if cleaned.strip():
            cleaned_lines.append(cleaned)
    cleaned_text = "\n".join(cleaned_lines).strip()
    parts = [part for part in (judgment, cleaned_text) if part]
    return "\n\n".join(parts)[:3200]
