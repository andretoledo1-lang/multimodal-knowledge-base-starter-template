"""Backend-neutral KB gateway for Chroma/KH parity work."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

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
        chroma: ChromaKbBackend,
        knowledge_hub: KnowledgeHubKbBackend,
        chroma_fallback_enabled: bool = True,
    ) -> None:
        if mode not in VALID_BACKEND_MODES:
            raise ValueError(f"Invalid DANTEDASH_KB_BACKEND={mode!r}")
        self.mode = mode
        self.chroma = chroma
        self.knowledge_hub = knowledge_hub
        self.chroma_fallback_enabled = chroma_fallback_enabled

    @property
    def chroma_kb(self) -> KnowledgeBase:
        return self.chroma.kb

    @property
    def claude_premium_repair_cap(self) -> int:
        return self.chroma.kb.claude_premium_repair_cap

    @property
    def claude_opus_chat_client(self) -> Any:
        return self.chroma.kb.claude_opus_chat_client

    @property
    def claude_sonnet_chief_client(self) -> Any:
        return self.chroma.kb.claude_sonnet_chief_client

    @property
    def claude_haiku_worker_client(self) -> Any:
        return self.chroma.kb.claude_haiku_worker_client

    @property
    def claude_opus_judge_client(self) -> Any:
        return self.chroma.kb.claude_opus_judge_client

    def chat_client_for_model(self, chat_model: str) -> Any:
        return self.chroma.kb.chat_client_for_model(chat_model)

    def count(self) -> int:
        return self._read("count")

    def count_by_modality(self) -> dict[str, int]:
        return self._read("count_by_modality")

    def search_text(
        self,
        query: str,
        *,
        top_k: int = 5,
        modality_filter: list[str] | None = None,
        on_progress: ProgressCallback = _noop,
    ) -> list[SearchResult]:
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
