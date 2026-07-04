from __future__ import annotations

from app.curatorial_rerank import curatorial_rerank, detect_curatorial_intent


def package_item(
    *,
    item_id: str,
    title: str,
    score: float | str | bool,
    artifact_type: str = "visual_analysis_bundle",
    group: str = "mixed",
    dante_image_id: str | None = None,
    preview: bool = True,
    tier: str | None = None,
    editorial_score: float | None = None,
    snippet: str = "",
) -> dict:
    metadata = {
        "id": item_id,
        "title": title,
        "original_name": title,
        "artifact_type": artifact_type,
        "group": group,
        "modality": "text" if artifact_type else "image",
    }
    if dante_image_id:
        metadata["dante_image_id"] = dante_image_id
    if preview:
        metadata["preview_image_file_id"] = f"preview-{item_id}"
        metadata["linked_image_file_id"] = f"image-{item_id}"
    if tier:
        metadata["editorial_tier"] = tier
    if editorial_score is not None:
        metadata["editorial_score"] = editorial_score
    return {
        "node_id": item_id,
        "title": title,
        "score": score,
        "excerpt": snippet,
        "metadata": metadata,
    }


def test_detect_curatorial_intent_is_bilingual() -> None:
    assert detect_curatorial_intent("me mostre shots incriveis s-tier") == "quality"
    assert detect_curatorial_intent("enquadramentos inusitados cinematograficos") == "quality"
    assert detect_curatorial_intent("Blade Runner 2049 frame 026") == "exact"
    assert detect_curatorial_intent("wide angle lighting composition") == "visual_craft"
    assert detect_curatorial_intent("craft based lighting references") == "visual_craft"
    assert detect_curatorial_intent("limelight archive notes") == "generic"


def test_quality_query_promotes_premium_candidates_over_generic_boards() -> None:
    items = [
        package_item(
            item_id="generic-board",
            title="dooh spectacle board",
            score=0.92,
            artifact_type="",
            preview=False,
            snippet="Generic brand board without film-frame analysis.",
        ),
        package_item(
            item_id="premium-still",
            title="barry-lyndon-1975-042 premium decoupage",
            score=0.61,
            artifact_type="visual_decoupage_bundle",
            group="barry-lyndon-1975",
            dante_image_id="barry-lyndon-1975-042",
            tier="premium_s_tier",
            editorial_score=97,
            snippet="S-tier candlelit composition with strong art-direction evidence.",
        ),
    ]

    outcome = curatorial_rerank("me mostre shots incriveis s-tier", items)

    assert outcome.intent == "quality"
    assert [item["node_id"] for item in outcome.items] == ["premium-still", "generic-board"]
    assert outcome.items[0]["metadata"]["curatorial_reason"] == "quality-signal"
    assert outcome.items[0]["metadata"]["curatorial_quality_score"] == 1.0
    assert "curatorial_insufficient_evidence" not in outcome.items[0]["metadata"]
    assert "curatorial_score" not in items[0]["metadata"]


def test_exact_query_promotes_title_year_and_frame_match() -> None:
    items = [
        package_item(
            item_id="blade-1982",
            title="blade-runner-1982-026 premium decoupage",
            score=0.91,
            artifact_type="visual_decoupage_bundle",
            group="blade-runner-1982",
            dante_image_id="blade-runner-1982-026",
        ),
        package_item(
            item_id="blade-2049",
            title="blade-runner-2049-2017-026 premium decoupage",
            score=0.62,
            artifact_type="visual_decoupage_bundle",
            group="blade-runner-2049-2017",
            dante_image_id="blade-runner-2049-2017-026",
        ),
    ]

    outcome = curatorial_rerank("Blade Runner 2049 frame 026 eye", items)

    assert outcome.intent == "exact"
    assert [item["node_id"] for item in outcome.items] == ["blade-2049", "blade-1982"]
    assert outcome.items[0]["metadata"]["curatorial_exact_score"] > 0.7
    assert outcome.items[1]["metadata"]["curatorial_exact_score"] < 0.42


def test_exact_query_does_not_treat_year_alone_as_title_match() -> None:
    items = [
        package_item(
            item_id="wrong-same-year",
            title="moonlight-2016-026 premium decoupage",
            score=0.98,
            artifact_type="visual_decoupage_bundle",
            group="moonlight-2016",
            dante_image_id="moonlight-2016-026",
        ),
        package_item(
            item_id="right-title",
            title="arrival-2016-011 premium decoupage",
            score=0.55,
            artifact_type="visual_decoupage_bundle",
            group="arrival-2016",
            dante_image_id="arrival-2016-011",
        ),
    ]

    outcome = curatorial_rerank("Arrival 2016", items)

    assert [item["node_id"] for item in outcome.items] == ["right-title", "wrong-same-year"]
    assert (
        outcome.items[0]["metadata"]["curatorial_exact_score"]
        > outcome.items[1]["metadata"]["curatorial_exact_score"]
    )


def test_exact_query_prioritizes_requested_frame_with_same_title() -> None:
    items = [
        package_item(
            item_id="right-title-wrong-frame",
            title="blade-runner-2049-2017-021 premium decoupage",
            score=0.98,
            artifact_type="visual_decoupage_bundle",
            group="blade-runner-2049-2017",
            dante_image_id="blade-runner-2049-2017-021",
        ),
        package_item(
            item_id="right-title-right-frame",
            title="blade-runner-2049-2017-026 premium decoupage",
            score=0.55,
            artifact_type="visual_decoupage_bundle",
            group="blade-runner-2049-2017",
            dante_image_id="blade-runner-2049-2017-026",
        ),
    ]

    outcome = curatorial_rerank("Blade Runner 2049 frame 026", items)

    assert [item["node_id"] for item in outcome.items] == ["right-title-right-frame", "right-title-wrong-frame"]
    assert (
        outcome.items[0]["metadata"]["curatorial_exact_score"]
        > outcome.items[1]["metadata"]["curatorial_exact_score"]
    )


def test_exact_query_marks_insufficient_when_identity_is_missing() -> None:
    items = [
        package_item(
            item_id="wrong-same-year",
            title="moonlight-2016-026 premium decoupage",
            score=0.98,
            artifact_type="visual_decoupage_bundle",
            group="moonlight-2016",
            dante_image_id="moonlight-2016-026",
        ),
    ]

    outcome = curatorial_rerank("Arrival 2016", items)

    assert outcome.insufficient is True
    assert outcome.items[0]["metadata"]["curatorial_insufficient_evidence"] is True


def test_generic_query_stays_vector_led() -> None:
    items = [
        package_item(
            item_id="low-vector",
            title="production archive note",
            score=0.25,
            artifact_type="",
            preview=False,
        ),
        package_item(
            item_id="high-vector",
            title="archive note digest",
            score=0.78,
            artifact_type="",
            preview=False,
        ),
    ]

    outcome = curatorial_rerank("archive notes", items)

    assert outcome.intent == "generic"
    assert [item["node_id"] for item in outcome.items] == ["high-vector", "low-vector"]


def test_broad_query_prefers_family_diversity_before_overflow() -> None:
    items = [
        package_item(
            item_id=f"akira-{index}",
            title=f"akira-1988-{index:03d} premium decoupage",
            score=0.90 - index / 100,
            group="akira-1988",
        )
        for index in range(4)
    ]
    items.extend(
        [
            package_item(
                item_id="aftersun-001",
                title="aftersun-2022-001 premium decoupage",
                score=0.78,
                group="aftersun-2022",
            ),
            package_item(
                item_id="barry-001",
                title="barry-lyndon-1975-001 premium decoupage",
                score=0.77,
                group="barry-lyndon-1975",
            ),
        ]
    )

    outcome = curatorial_rerank("me mostre shots com composicao e luz", items)
    first_four_groups = [item["metadata"]["group"] for item in outcome.items[:4]]

    assert first_four_groups.count("akira-1988") == 2
    assert "aftersun-2022" in first_four_groups
    assert "barry-lyndon-1975" in first_four_groups


def test_missing_metadata_and_bad_scores_do_not_raise() -> None:
    items = [
        {"node_id": "bare", "score": "bad-score", "title": "bare text"},
        {"node_id": "image", "score": "45", "metadata": {"modality": "image", "title": "visual reference"}},
    ]

    outcome = curatorial_rerank("visual composition", items)

    assert [item["node_id"] for item in outcome.items] == ["image", "bare"]
    assert outcome.items[0]["metadata"]["curatorial_preview_score"] == 1.0


def test_non_finite_and_boolean_scores_do_not_become_perfect_vector_evidence() -> None:
    items = [
        package_item(item_id="nan-score", title="archive note nan", score="NaN", artifact_type="", preview=False),
        package_item(
            item_id="infinite-score",
            title="archive note infinite",
            score="Infinity",
            artifact_type="",
            preview=False,
        ),
        package_item(item_id="bool-score", title="archive note bool", score=True, artifact_type="", preview=False),
        package_item(item_id="finite-score", title="archive note finite", score=0.5, artifact_type="", preview=False),
    ]

    outcome = curatorial_rerank("archive notes", items)
    vector_scores = {item["node_id"]: item["metadata"]["curatorial_vector_score"] for item in outcome.items}

    assert outcome.items[0]["node_id"] == "finite-score"
    assert vector_scores["finite-score"] == 0.5
    assert vector_scores["nan-score"] == 0.0
    assert vector_scores["infinite-score"] == 0.0
    assert vector_scores["bool-score"] == 0.0
