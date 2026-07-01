from __future__ import annotations

from pathlib import Path

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

    def stats(self) -> dict[str, object]:
        self.calls.append("stats")
        if self.fail:
            raise KbBackendUnavailable("unavailable")
        return {"total": 7, "by_modality": {"image": 3, "text": 4}}

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

    def search_image(self, image_path, **_kwargs):
        self.calls.append(f"search_image:{image_path}")
        if self.fail:
            raise KbBackendUnavailable("unavailable")
        return [
            SearchResult(
                node_id="image-node-a",
                score=0.91,
                modality="image",
                metadata={"id": "image-file-a", "original_name": "Image A", "modality": "image"},
                snippet="visual alpha",
            )
        ]

    def delete_by_file_id(self, file_id: str) -> int:
        self.deleted.append(file_id)
        return 1

    def clear(self) -> None:
        self.cleared = True


class VisualRescueBackend(FakeBackend):
    def search_text(self, query: str, **_kwargs):
        self.calls.append(f"search_text:{query}")
        return [
            SearchResult(
                node_id="dante-shot-a-analysis",
                score=0.84,
                modality="text",
                metadata={
                    "id": "dante-shot-a-analysis",
                    "original_name": "shotdeck-reference-2026-05-053 visual analysis",
                    "artifact_type": "visual_analysis_bundle",
                    "dante_image_id": "shotdeck-reference-2026-05-053",
                    "preview_image_file_id": "dante_visual_img_sha-a",
                    "modality": "text",
                },
                snippet=(
                    "[Dante visual analysis bundle] Image ID: shotdeck-reference-2026-05-053 "
                    "Image: shotdeck-batches/batch-2026-05-01/shotdeck-reference-2026-05-053.jpg "
                    "Card run: visual-gemini-full-auto-20260614-codex "
                    "Judgment: score=95 tier=s-tier recommendation=use_as_reference\n\n"
                    "## Searchable visual fields\n"
                    "- Composition: Strong cinematic silhouette and layered foreground depth.\n\n"
                    "## Markdown card\n"
                    "source_sha256: secret\n"
                    "Original path: /Users/vidigal/private.jpg"
                ),
            ),
            SearchResult(
                node_id="dante-shot-a-decoupage",
                score=0.8,
                modality="text",
                metadata={
                    "id": "dante-shot-a-decoupage",
                    "original_name": "shotdeck-reference-2026-05-053 premium decoupage",
                    "artifact_type": "visual_decoupage_bundle",
                    "dante_image_id": "shotdeck-reference-2026-05-053",
                    "preview_image_file_id": "dante_visual_img_sha-a",
                    "modality": "text",
                },
                snippet="Premium decoupage for the same shot.",
            ),
            SearchResult(
                node_id="dante-shot-b-decoupage",
                score=0.79,
                modality="text",
                metadata={
                    "id": "dante-shot-b-decoupage",
                    "original_name": "aguirre-the-wrath-of-god-1972-061 premium decoupage",
                    "artifact_type": "visual_decoupage_bundle",
                    "dante_image_id": "aguirre-the-wrath-of-god-1972-061",
                    "preview_image_file_id": "dante_visual_img_sha-b",
                    "modality": "text",
                },
                snippet="Premium jungle composition analysis.",
            ),
            SearchResult(
                node_id="plain-text",
                score=0.99,
                modality="text",
                metadata={"id": "plain-text", "original_name": "plain text", "modality": "text"},
                snippet="Not a visual source.",
            ),
        ]


class FakeKnowledgeHubClient:
    def __init__(self) -> None:
        self.image_queries: list[tuple[str, int]] = []
        self.stats_calls = 0

    def dantedash_search_packages(self, _payload):
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "node_id": "kh-a",
                        "title": "A",
                        "excerpt": "alpha",
                        "score": 0.9,
                        "metadata": {"id": "kh-a", "source_sha256": "sha-a", "file_path": "/Users/a/secret"},
                    },
                    {"id": "kh-b", "title": "B", "snippet": "beta", "score": 0.8},
                    {"id": "kh-c", "title": "C", "snippet": "gamma", "score": 0.7},
                ]
            },
        }

    def dantedash_search_packages_by_image(self, image_path, *, top_k=5):
        self.image_queries.append((str(image_path), top_k))
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "node_id": "kh-image-a",
                        "title": "Image A",
                        "excerpt": "visual alpha",
                        "score": 0.91,
                        "metadata": {
                            "id": "kh-image-a",
                            "source_sha256": "sha-image-a",
                            "modality": "image",
                            "file_path": "/Users/vidigal/private-image.jpg",
                        },
                    },
                    {
                        "node_id": "kh-text-a",
                        "title": "Text A",
                        "excerpt": "text alpha",
                        "score": 0.7,
                        "metadata": {"id": "kh-text-a", "modality": "text"},
                    },
                ]
            },
        }

    def dantedash_package_stats(self):
        self.stats_calls += 1
        return {"ok": True, "data": {"total": 3, "by_modality": {"image": 1, "text": 2}}}

    def dantedash_package_items(self, *, limit=None, offset=0):
        del limit, offset
        return {"ok": True, "data": {"items": [{"file_id": "kh-a", "original_name": "A"}], "total": 1}}

    def dantedash_package_item(self, item_id, *, include_private=False):
        metadata = {"id": item_id, "source_sha256": "sha-a", "modality": "image", "original_name": "A"}
        if include_private:
            metadata["file_path"] = "/Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/source-assets/a.jpg"
        return {
            "ok": True,
            "data": {
                "file_id": item_id,
                "original_name": "A",
                "modality": "image",
                "upload_time": "",
                "node_ids": [item_id],
                "metadata": metadata,
                "nodes": [{"node_id": item_id, "metadata": metadata, "snippet": "alpha"}],
            },
        }


class FakeChatRuntime:
    claude_premium_repair_cap = 1
    claude_opus_chat_client = object()
    claude_sonnet_chief_client = object()
    claude_haiku_worker_client = object()
    claude_opus_judge_client = object()

    def __init__(self) -> None:
        self.requests: list[str] = []

    def chat_client_for_model(self, chat_model):
        self.requests.append(str(chat_model))
        return object()


class FailingImageQueryKnowledgeHubClient(FakeKnowledgeHubClient):
    def dantedash_search_packages_by_image(self, image_path, *, top_k=5):
        del image_path, top_k
        return {"ok": False, "error": "service_unavailable"}


class UnavailableStatusKnowledgeHubClient(FakeKnowledgeHubClient):
    def dantedash_search_packages(self, _payload):
        return {"ok": True, "data": {"status": "unavailable", "items": []}}

    def dantedash_search_packages_by_image(self, image_path, *, top_k=5):
        del image_path, top_k
        return {
            "ok": True,
            "data": {
                "status": "unavailable",
                "items": [],
                "visual_retrieval": {"status": "embedder_unavailable"},
            },
        }


class FlakyImageQueryKnowledgeHubClient(FakeKnowledgeHubClient):
    def __init__(self) -> None:
        super().__init__()
        self._failed_once = False

    def dantedash_search_packages_by_image(self, image_path, *, top_k=5):
        if not self._failed_once:
            self._failed_once = True
            self.image_queries.append((str(image_path), top_k))
            return {
                "ok": True,
                "data": {
                    "status": "unavailable",
                    "items": [],
                    "visual_retrieval": {"status": "embed_image_query_failed"},
                },
            }
        return super().dantedash_search_packages_by_image(image_path, top_k=top_k)


class ImageItemWithLegacyPreviewIdKnowledgeHubClient(FakeKnowledgeHubClient):
    def dantedash_package_item(self, item_id, *, include_private=False):
        if item_id == "akira-1988-088":
            return {"ok": False, "status_code": 404, "error": "not_found"}
        metadata = {
            "id": item_id,
            "source_sha256": "sha-a",
            "modality": "image",
            "original_name": "Akira frame",
            "preview_image_file_id": "akira-1988-088",
        }
        if include_private:
            metadata["file_path"] = (
                "/Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/"
                "source-assets/film-stills/akira-1988/akira-1988-088.jpg"
            )
        return {
            "ok": True,
            "data": {
                "file_id": item_id,
                "original_name": "Akira frame",
                "modality": "image",
                "upload_time": "",
                "node_ids": [item_id],
                "metadata": metadata,
                "nodes": [{"node_id": item_id, "metadata": metadata, "snippet": "alpha"}],
            },
        }


class GenericMultimodalKnowledgeHubClient(FakeKnowledgeHubClient):
    def dantedash_package_item(self, item_id, *, include_private=False):
        if str(item_id).startswith(("pirata-", "khpkg:pirata-kb:")):
            return {"ok": False, "status_code": 404, "error": "not_found"}
        return super().dantedash_package_item(item_id, include_private=include_private)

    def multimodal_package_stats(self, corpus_slug):
        assert corpus_slug == "pirata-kb"
        return {
            "ok": True,
            "data": {
                "status": "certified",
                "summary": {
                    "asset_count": 2,
                    "source_map_count": 1,
                    "derived_file_count": 1,
                },
            },
        }

    def multimodal_search_packages(self, corpus_slug, payload):
        assert corpus_slug == "pirata-kb"
        assert payload["query"]
        return {
            "ok": True,
            "data": {
                "status": "certified",
                "items": [
                    {
                        "package_id": "khpkg:pirata-kb:frame:hash-a",
                        "asset_id": "pirata-frame-a",
                        "asset_identity": "pirata-kb:frames:aftersun-2022:001",
                        "content_hash": "hash-a",
                        "display_label": "Aftersun frame 001",
                        "citation_label": "frame 001 from Aftersun",
                        "media_type": "image",
                        "score": 0.96,
                        "frame_index": 1,
                        "layer_count": 3,
                    }
                ],
            },
        }

    def multimodal_search_packages_by_image(self, corpus_slug, image_path, *, top_k=5):
        assert corpus_slug == "pirata-kb"
        assert top_k == 1
        return {
            "ok": True,
            "data": {
                "status": "certified",
                "items": [
                    {
                        "package_id": "khpkg:pirata-kb:frame:hash-image",
                        "asset_id": "pirata-frame-image",
                        "display_label": "Pirata image match",
                        "media_type": "image",
                        "score": 0.99,
                    }
                ],
            },
        }

    def multimodal_package_item(self, corpus_slug, item_id, *, include_private=False):
        assert corpus_slug == "pirata-kb"
        if item_id not in {"pirata-frame-a", "khpkg:pirata-kb:frame:hash-a"}:
            return {"ok": False, "status_code": 404, "error": "not_found"}
        item = {
            "package_id": "khpkg:pirata-kb:frame:hash-a",
            "asset_id": "pirata-frame-a",
            "display_label": "Aftersun frame 001",
            "citation_label": "frame 001 from Aftersun",
            "media_type": "image",
        }
        if include_private:
            item["private"] = {
                "asset_path": (
                    "/Users/vidigal/knowledge-base/09-knowledge-base/"
                    "pirata-kb/03-assets/aftersun-2022/frames/frame_001.jpg"
                )
            }
        return {"ok": True, "data": {"status": "certified", "item": item}}


class LegacyTextAndVisualPackageKnowledgeHubClient(FakeKnowledgeHubClient):
    def dantedash_search_packages(self, _payload):
        self.last_text_payload = dict(_payload)
        return {
            "ok": True,
            "data": {
                "items": [
                    {
                        "id": "legacy-birdman-text",
                        "title": "birdman 2014 1080p bluray ddp5 1 x265 10bit frame 002",
                        "snippet": "Legacy text layer for the Birdman frame.",
                        "score": 0.99,
                        "metadata": {"id": "legacy-birdman-text", "modality": "text"},
                    },
                    {
                        "id": "legacy-aftersun-text",
                        "title": "aftersun 2022 frame 004 visual analysis",
                        "snippet": "Legacy text layer for the Aftersun frame.",
                        "score": 0.98,
                        "metadata": {"id": "legacy-aftersun-text", "modality": "text"},
                    },
                ]
            },
        }

    def multimodal_search_packages(self, corpus_slug, payload):
        assert corpus_slug == "pirata-kb"
        assert payload["query"]
        self.last_multimodal_payload = dict(payload)
        return {
            "ok": True,
            "data": {
                "status": "certified",
                "items": [
                    {
                        "package_id": "khpkg:pirata-kb:frame:birdman-hash",
                        "asset_id": "birdman-image",
                        "display_label": "Birdman 2014 frame 002",
                        "media_type": "image",
                        "score": 0.81,
                    },
                    {
                        "package_id": "khpkg:pirata-kb:frame:aftersun-hash",
                        "asset_id": "aftersun-image",
                        "display_label": "Aftersun 2022 frame 004",
                        "media_type": "image",
                        "score": 0.8,
                    },
                ],
            },
        }


class LayeredMultimodalKnowledgeHubClient(FakeKnowledgeHubClient):
    def __init__(self, kb_root: Path) -> None:
        super().__init__()
        self.kb_root = kb_root

    def dantedash_search_packages(self, _payload):
        return {"ok": True, "data": {"items": []}}

    def multimodal_search_packages(self, corpus_slug, payload):
        assert corpus_slug == "pirata-kb"
        assert payload["query"]
        return {
            "ok": True,
            "data": {
                "status": "certified",
                "items": [
                    {
                        "package_id": "khpkg:pirata-kb:frame:hash-a",
                        "asset_id": "pirata-frame-a",
                        "display_label": "Aftersun 2022 frame 001",
                        "media_type": "image",
                        "score": 0.91,
                        "frame_index": 1,
                    }
                ],
            },
        }

    def multimodal_package_item(self, corpus_slug, item_id, *, include_private=False):
        assert corpus_slug == "pirata-kb"
        assert item_id in {"pirata-frame-a", "khpkg:pirata-kb:frame:hash-a"}
        item = {
            "package_id": "khpkg:pirata-kb:frame:hash-a",
            "asset_id": "pirata-frame-a",
            "display_label": "Aftersun 2022 frame 001",
            "media_type": "image",
            "frame_index": 1,
            "layers": [
                {
                    "layer_type": "visual_asset",
                    "relative_path": "03-assets/aftersun-2022/frames/frame_001.jpg",
                },
                {
                    "layer_type": "source_map",
                    "relative_path": "02-sources/aftersun-2022-visual-source-map.md",
                },
                {
                    "layer_type": "derived_analysis",
                    "relative_path": "04-derived/per-movie/aftersun-2022.md",
                },
            ],
        }
        if include_private:
            item["private"] = {
                "asset_path": str(self.kb_root / "03-assets/aftersun-2022/frames/frame_001.jpg"),
                "source_path": str(self.kb_root / "02-sources/aftersun-2022-visual-source-map.md"),
            }
        return {"ok": True, "data": {"status": "certified", "item": item}}


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


def test_knowledge_hub_mode_serves_text_from_kh_without_chroma() -> None:
    chroma = FakeBackend()
    kh = FakeBackend()
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=True,
    )

    assert gateway.search_text("barry lyndon")[0].metadata["id"] == "file-a"
    assert kh.calls == ["search_text:barry lyndon"]
    assert chroma.calls == []


def test_knowledge_hub_strict_mode_disables_chroma_rescue_for_generic_visual_queries() -> None:
    chroma = VisualRescueBackend()
    kh = FakeBackend()
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=False,
    )

    results = gateway.search_text("me mostre 5 shots incriveis s-tier", top_k=2)

    assert [result.node_id for result in results] == ["node-a"]
    assert kh.calls == ["search_text:me mostre 5 shots incriveis s-tier"]
    assert chroma.calls == []


def test_knowledge_hub_non_strict_mode_can_use_explicit_chroma_visual_rescue() -> None:
    chroma = VisualRescueBackend()
    kh = FakeBackend()
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=False,
        chroma_visual_rescue_enabled=True,
        strict_no_chroma=False,
    )

    results = gateway.search_text("me mostre 5 shots incriveis s-tier", top_k=2)

    assert [result.node_id for result in results] == ["dante-shot-a-analysis", "dante-shot-b-decoupage"]
    assert "Strong cinematic silhouette" in results[0].snippet
    assert "shotdeck-reference-2026-05-053.jpg" not in results[0].snippet
    assert "Card run:" not in results[0].snippet
    assert "Markdown card" not in results[0].snippet
    assert "Original path" not in results[0].snippet
    assert results[0].modality == "image"
    assert results[0].metadata["modality"] == "text"
    assert results[0].metadata["retrieval_source"] == "chroma_visual_rescue"
    assert all(result.metadata["dante_image_id"] != "" for result in results)
    assert kh.calls == []
    assert chroma.calls == ["search_text:me mostre 5 shots incriveis s-tier"]


def test_knowledge_hub_mode_keeps_explicit_pirata_query_on_knowledge_hub() -> None:
    chroma = VisualRescueBackend()
    kh = FakeBackend()
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=False,
    )

    assert gateway.search_text("me mostre shots do pirata-kb", top_k=2)[0].node_id == "node-a"
    assert kh.calls == ["search_text:me mostre shots do pirata-kb"]
    assert chroma.calls == []


def test_knowledge_hub_mode_serves_image_query_from_kh_without_chroma() -> None:
    chroma = FakeBackend()
    client = FakeKnowledgeHubClient()
    kh = KnowledgeHubKbBackend(client)
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=False,
    )

    assert gateway.search_image("/tmp/query.jpg")[0].node_id == "kh-image-a"
    assert client.image_queries == [("/tmp/query.jpg", 5)]
    assert chroma.calls == []


def test_knowledge_hub_image_query_retries_transient_unavailable_status() -> None:
    client = FlakyImageQueryKnowledgeHubClient()
    kh = KnowledgeHubKbBackend(client)

    assert kh.search_image("/tmp/query.jpg")[0].node_id == "kh-image-a"
    assert client.image_queries == [("/tmp/query.jpg", 5), ("/tmp/query.jpg", 5)]


def test_knowledge_hub_mode_falls_back_to_chroma_for_image_query_when_enabled() -> None:
    chroma = FakeBackend()
    kh = KnowledgeHubKbBackend(FailingImageQueryKnowledgeHubClient())
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=True,
        strict_no_chroma=False,
    )

    assert gateway.search_image("/tmp/query.jpg")[0].node_id == "image-node-a"
    assert chroma.calls == ["search_image:/tmp/query.jpg"]


def test_knowledge_hub_mode_falls_back_when_kh_returns_unavailable_status() -> None:
    chroma = FakeBackend()
    kh = KnowledgeHubKbBackend(UnavailableStatusKnowledgeHubClient())
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma,
        knowledge_hub=kh,
        chroma_fallback_enabled=True,
        strict_no_chroma=False,
    )

    assert gateway.search_text("aftersun")[0].node_id == "node-a"
    assert gateway.search_image("/tmp/query.jpg")[0].node_id == "image-node-a"
    assert chroma.calls == ["search_text:aftersun", "search_image:/tmp/query.jpg"]


def test_knowledge_hub_mode_raises_when_unavailable_status_and_fallback_disabled() -> None:
    kh = KnowledgeHubKbBackend(UnavailableStatusKnowledgeHubClient())
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=FakeBackend(),
        knowledge_hub=kh,
        chroma_fallback_enabled=False,
    )

    with pytest.raises(KbBackendUnavailable):
        gateway.search_text("aftersun")
    with pytest.raises(KbBackendUnavailable):
        gateway.search_image("/tmp/query.jpg")


def test_knowledge_hub_mode_raises_for_image_query_when_fallback_disabled() -> None:
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=FakeBackend(),
        knowledge_hub=KnowledgeHubKbBackend(FailingImageQueryKnowledgeHubClient()),
        chroma_fallback_enabled=False,
    )

    with pytest.raises(KbBackendUnavailable):
        gateway.search_image("/tmp/query.jpg")


def test_knowledge_hub_mode_does_not_construct_chroma_until_needed() -> None:
    calls: list[str] = []

    def chroma_factory():
        calls.append("constructed")
        return FakeBackend()

    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma_factory,
        knowledge_hub=KnowledgeHubKbBackend(FakeKnowledgeHubClient()),
        chroma_fallback_enabled=False,
    )

    assert gateway.count() == 3
    assert gateway.search_text("barry")[0].node_id == "kh-a"
    assert calls == []


def test_knowledge_hub_chat_runtime_does_not_construct_chroma() -> None:
    calls: list[str] = []
    chat_runtime = FakeChatRuntime()

    def chroma_factory():
        calls.append("constructed")
        return FakeBackend()

    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=chroma_factory,
        knowledge_hub=KnowledgeHubKbBackend(FakeKnowledgeHubClient()),
        chroma_fallback_enabled=False,
        chat_runtime=chat_runtime,
    )

    assert gateway.chat_client_for_model("deepseek-v4-pro") is not None
    assert gateway.claude_premium_repair_cap == 1
    assert gateway.claude_opus_chat_client is chat_runtime.claude_opus_chat_client
    assert calls == []


def test_gateway_status_is_public_safe_for_knowledge_hub_primary() -> None:
    gateway = KbGateway(
        mode="knowledge_hub",
        chroma=FakeBackend(),
        knowledge_hub=FakeBackend(),
        chroma_fallback_enabled=True,
        strict_no_chroma=False,
    )

    status = gateway.status()

    assert status == {
        "mode": "knowledge_hub",
        "primary_backend": "knowledge_hub",
        "shadow_backend": None,
        "chroma_fallback_enabled": True,
        "chroma_available_as_fallback": True,
        "chroma_visual_rescue_enabled": False,
        "strict_no_chroma": False,
        "writes_enabled": False,
        "surfaces": {
            "text_search": "knowledge_hub",
            "chat_sources": "knowledge_hub",
            "stats": "knowledge_hub",
            "library": "knowledge_hub",
            "preview": "knowledge_hub",
            "image_query_search": "knowledge_hub",
            "visual_text_rescue": "disabled",
        },
    }


@pytest.mark.parametrize(
    ("mode", "fallback_enabled", "expected"),
    [
        (
            "chroma",
            True,
            {
                "primary_backend": "chroma",
                "shadow_backend": None,
                "chroma_available_as_fallback": False,
                "writes_enabled": True,
                "image_query_search": "chroma",
            },
        ),
        (
            "dual",
            True,
            {
                "primary_backend": "chroma",
                "shadow_backend": "knowledge_hub",
                "chroma_available_as_fallback": False,
                "writes_enabled": True,
                "image_query_search": "chroma",
            },
        ),
        (
            "knowledge_hub",
            False,
            {
                "primary_backend": "knowledge_hub",
                "shadow_backend": None,
                "chroma_available_as_fallback": False,
                "writes_enabled": False,
                "image_query_search": "knowledge_hub",
            },
        ),
    ],
)
def test_gateway_status_modes(mode: str, fallback_enabled: bool, expected: dict[str, object]) -> None:
    gateway = KbGateway(
        mode=mode,
        chroma=FakeBackend(),
        knowledge_hub=FakeBackend(),
        chroma_fallback_enabled=fallback_enabled,
    )

    status = gateway.status()

    assert status["mode"] == mode
    assert status["primary_backend"] == expected["primary_backend"]
    assert status["shadow_backend"] == expected["shadow_backend"]
    assert status["chroma_available_as_fallback"] is expected["chroma_available_as_fallback"]
    assert status["writes_enabled"] is expected["writes_enabled"]
    assert status["surfaces"]["image_query_search"] == expected["image_query_search"]


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
    assert results[0].metadata["source_sha256"] == "sha-a"

    image_results = backend.search_image("/tmp/query.jpg", top_k=1)
    assert [result.node_id for result in image_results] == ["kh-image-a"]
    assert "file_path" not in image_results[0].metadata
    assert image_results[0].metadata["source_sha256"] == "sha-image-a"

    filtered_results = backend.search_image("/tmp/query.jpg", top_k=2, modality_filter=["image"])
    assert [result.node_id for result in filtered_results] == ["kh-image-a"]


def test_knowledge_hub_backend_serves_official_stats_and_listing() -> None:
    client = FakeKnowledgeHubClient()
    backend = KnowledgeHubKbBackend(client)

    assert backend.count() == 3
    assert backend.count_by_modality() == {"image": 1, "text": 2}
    items, total = backend.list_items()

    assert total == 1
    assert items[0]["file_id"] == "kh-a"
    assert backend.get_item(file_id="kh-a")["metadata"]["source_sha256"] == "sha-a"


def test_knowledge_hub_backend_stats_uses_single_kh_call() -> None:
    client = FakeKnowledgeHubClient()
    backend = KnowledgeHubKbBackend(client)

    assert backend.stats() == {"total": 3, "by_modality": {"image": 1, "text": 2}}
    assert client.stats_calls == 1


def test_knowledge_hub_backend_serves_image_preview_from_current_item_when_preview_id_is_legacy() -> None:
    backend = KnowledgeHubKbBackend(ImageItemWithLegacyPreviewIdKnowledgeHubClient())

    lookup = backend.lookup_preview("dante_visual_img_sha-a")

    assert lookup.path == Path(
        "/Users/vidigal/Obsidian_Dante_AI_RAG_DATA/visual-reference-assets/"
        "source-assets/film-stills/akira-1988/akira-1988-088.jpg"
    )
    assert lookup.metadata["id"] == "dante_visual_img_sha-a"
    assert lookup.metadata["modality"] == "image"
    assert lookup.metadata["preview_image_file_id"] == "akira-1988-088"


def test_knowledge_hub_backend_includes_generic_multimodal_corpus_and_preview() -> None:
    client = GenericMultimodalKnowledgeHubClient()
    backend = KnowledgeHubKbBackend(client, multimodal_corpora=("pirata-kb",))

    assert backend.stats() == {"total": 3, "by_modality": {"image": 1, "text": 2}}

    text_results = backend.search_text("aftersun frame", top_k=2)
    assert [result.node_id for result in text_results] == ["kh-a", "kh-b"]

    image_results = backend.search_image("/tmp/query.jpg", top_k=1)
    assert image_results[0].node_id == "kh-image-a"

    explicit_text_results = backend.search_text("aftersun frame no pirata-kb", top_k=2)
    assert explicit_text_results[0].node_id == "khpkg:pirata-kb:frame:hash-a"
    assert explicit_text_results[0].metadata["package_id"] == "khpkg:pirata-kb:frame:hash-a"
    assert explicit_text_results[0].metadata["asset_identity"] == "pirata-kb:frames:aftersun-2022:001"
    assert explicit_text_results[0].metadata["original_name"] == "Aftersun frame 001"
    assert explicit_text_results[0].metadata["modality"] == "image"
    assert "private" not in explicit_text_results[0].metadata

    lookup = backend.lookup_preview("pirata-frame-a")
    assert lookup.path == Path(
        "/Users/vidigal/knowledge-base/09-knowledge-base/pirata-kb/03-assets/"
        "aftersun-2022/frames/frame_001.jpg"
    )
    assert lookup.metadata["id"] == "pirata-frame-a"
    assert lookup.metadata["modality"] == "image"


def test_knowledge_hub_backend_prefers_visual_package_over_duplicate_legacy_text() -> None:
    client = LegacyTextAndVisualPackageKnowledgeHubClient()
    backend = KnowledgeHubKbBackend(client, multimodal_corpora=("pirata-kb",))

    results = backend.search_text("me mostre 5 shots com lentes grande-angulares no pirata-kb", top_k=2)

    assert client.last_text_payload["top_k"] >= 24
    assert client.last_multimodal_payload["top_k"] >= 24
    assert [result.node_id for result in results] == [
        "khpkg:pirata-kb:frame:birdman-hash",
        "khpkg:pirata-kb:frame:aftersun-hash",
    ]
    assert [result.modality for result in results] == ["image", "image"]
    assert results[0].metadata["visual_asset_key"] == "visual:birdman-2014:frame:002"
    assert results[1].metadata["visual_asset_key"] == "visual:aftersun-2022:frame:004"


def test_knowledge_hub_backend_attaches_multimodal_analysis_layers(tmp_path: Path) -> None:
    kb_root = tmp_path / "09-knowledge-base" / "pirata-kb"
    (kb_root / "02-sources").mkdir(parents=True)
    (kb_root / "03-assets/aftersun-2022/frames").mkdir(parents=True)
    (kb_root / "04-derived/per-movie").mkdir(parents=True)
    (kb_root / "03-assets/aftersun-2022/frames/frame_001.jpg").write_bytes(b"fake")
    (kb_root / "02-sources/aftersun-2022-visual-source-map.md").write_text(
        "# Aftersun visual source map\n\n"
        "## Film context\nGeneral context.\n\n"
        "### Frame 001 - `aftersun-2022_frame_001.jpg`\n"
        "A poolside composition uses negative space, hazy summer light, and off-center blocking "
        "to make the father-daughter distance emotionally legible.\n\n"
        "### Frame 002 - aftersun frame\nOther frame.\n",
        encoding="utf-8",
    )
    (kb_root / "04-derived/per-movie/aftersun-2022.md").write_text(
        "---\ntitle: Aftersun\n---\n\n"
        "# Aftersun\n"
        "filename: aftersun-2022_frame_001.jpg\n"
        "The derived analysis reads the film as restrained, memory-shaped realism.",
        encoding="utf-8",
    )
    client = LayeredMultimodalKnowledgeHubClient(kb_root)
    backend = KnowledgeHubKbBackend(client, multimodal_corpora=("pirata-kb",))

    results = backend.search_text("me mostre shots incriveis no pirata-kb", top_k=1)

    assert results[0].modality == "image"
    assert "poolside composition uses negative space" in results[0].snippet
    assert "memory-shaped realism" in results[0].snippet
    assert "aftersun-2022_frame_001.jpg" not in results[0].snippet
    assert "filename:" not in results[0].snippet
    assert str(tmp_path) not in results[0].snippet
    assert results[0].metadata["analysis_context_available"] is True


def test_knowledge_hub_backend_redacts_local_paths_from_multimodal_layer_text(tmp_path: Path) -> None:
    kb_root = tmp_path / "09-knowledge-base" / "pirata-kb"
    (kb_root / "02-sources").mkdir(parents=True)
    (kb_root / "03-assets/aftersun-2022/frames").mkdir(parents=True)
    (kb_root / "03-assets/aftersun-2022/frames/frame_001.jpg").write_bytes(b"fake")
    (kb_root / "02-sources/aftersun-2022-visual-source-map.md").write_text(
        "### Frame 001\n"
        "Use the reference at /tmp/private/source.jpg and /Volumes/archive/secret.mov "
        "only for private operator tracing.\n",
        encoding="utf-8",
    )
    client = LayeredMultimodalKnowledgeHubClient(kb_root)
    backend = KnowledgeHubKbBackend(client, multimodal_corpora=("pirata-kb",))

    results = backend.search_text("me mostre shots incriveis no pirata-kb", top_k=1)

    assert "/tmp/private/source.jpg" not in results[0].snippet
    assert "/Volumes/archive/secret.mov" not in results[0].snippet
    assert "[redacted-local-path]" in results[0].snippet
