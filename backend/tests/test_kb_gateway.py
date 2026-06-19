from __future__ import annotations

import pytest

from app.kb import SearchResult
from app.kb_backends import KbBackendUnavailable, KbWriteDisabled, KnowledgeHubKbBackend
from app.kb_gateway import KbGateway


class FakeBackend:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.deleted: list[str] = []
        self.cleared = False
        self.calls: list[str] = []
        self.kb = object()

    def count(self) -> int:
        self.calls.append("count")
        if self.fail:
            raise KbBackendUnavailable("unavailable")
        return 7

    def count_by_modality(self) -> dict[str, int]:
        self.calls.append("count_by_modality")
        if self.fail:
            raise KbBackendUnavailable("unavailable")
        return {"image": 3, "text": 4}

    def search_text(self, query: str, **_kwargs):
        self.calls.append(f"search_text:{query}")
        if self.fail:
            raise KbBackendUnavailable("unavailable")
        return [
            SearchResult(
                node_id="node-a",
                score=0.9,
                modality="text",
                metadata={"id": "file-a", "original_name": "A", "modality": "text"},
                snippet="alpha",
            )
        ]

    def delete_by_file_id(self, file_id: str) -> int:
        self.deleted.append(file_id)
        return 1

    def clear(self) -> None:
        self.cleared = True


class FakeKnowledgeHubClient:
    def retrieve(self, _payload):
        return {
            "ok": True,
            "data": {
                "items": [
                    {"id": "kh-a", "title": "A", "snippet": "alpha", "score": 0.9, "file_path": "/Users/a/secret"},
                    {"id": "kh-b", "title": "B", "snippet": "beta", "score": 0.8},
                    {"id": "kh-c", "title": "C", "snippet": "gamma", "score": 0.7},
                ]
            },
        }


def test_invalid_gateway_mode_fails_closed() -> None:
    with pytest.raises(ValueError, match="Invalid DANTEDASH_KB_BACKEND"):
        KbGateway(mode="typo", chroma=FakeBackend(), knowledge_hub=FakeBackend())


def test_chroma_mode_uses_chroma_backend() -> None:
    chroma = FakeBackend()
    kh = FakeBackend(fail=True)
    gateway = KbGateway(mode="chroma", chroma=chroma, knowledge_hub=kh)

    assert gateway.count() == 7
    assert gateway.count_by_modality() == {"image": 3, "text": 4}
    assert gateway.search_text("corridor")[0].node_id == "node-a"
    assert kh.calls == []


def test_dual_mode_serves_chroma_and_shadows_kh() -> None:
    chroma = FakeBackend()
    kh = FakeBackend(fail=True)
    gateway = KbGateway(mode="dual", chroma=chroma, knowledge_hub=kh)

    assert gateway.search_text("aftersun")[0].metadata["id"] == "file-a"
    assert chroma.calls == ["search_text:aftersun"]
    assert kh.calls == ["search_text:aftersun"]


def test_knowledge_hub_mode_falls_back_to_chroma_when_enabled() -> None:
    chroma = FakeBackend()
    kh = FakeBackend(fail=True)
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=True,
    )

    assert gateway.count() == 7
    assert chroma.calls == ["count"]
    assert kh.calls == ["count"]


def test_knowledge_hub_mode_raises_when_fallback_disabled() -> None:
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=FakeBackend(),
        knowledge_hub=FakeBackend(fail=True),
        chroma_fallback_enabled=False,
    )

    with pytest.raises(KbBackendUnavailable):
        gateway.count()


def test_knowledge_hub_mode_disables_writes() -> None:
    chroma = FakeBackend()
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=FakeBackend(),
    )

    with pytest.raises(KbWriteDisabled):
        gateway.delete_by_file_id("file-a")
    with pytest.raises(KbWriteDisabled):
        gateway.clear()
    assert chroma.deleted == []
    assert chroma.cleared is False


def test_knowledge_hub_backend_bounds_search_results_to_top_k() -> None:
    backend = KnowledgeHubKbBackend(FakeKnowledgeHubClient())

    results = backend.search_text("corridor", top_k=2)

    assert [result.node_id for result in results] == ["kh-a", "kh-b"]
    assert "file_path" not in results[0].metadata
