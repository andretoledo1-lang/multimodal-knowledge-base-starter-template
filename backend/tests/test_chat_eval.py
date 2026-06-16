from __future__ import annotations

from app.chat_eval import QUALITY_GATE, compare_model_scores, score_answer


def test_score_answer_passes_quality_gate_for_grounded_answer() -> None:
    scores = score_answer(
        answer="DanteDash uses retrieved cards as grounded evidence [1].",
        source_count=1,
        source_panel_count=1,
    )
    assert scores.total >= QUALITY_GATE
    assert scores.passes_gate


def test_score_answer_fails_missing_citation() -> None:
    scores = score_answer(
        answer="DanteDash uses retrieved cards as grounded evidence.",
        source_count=1,
        source_panel_count=1,
    )
    assert scores.citation_validity_score == 0.0
    assert not scores.passes_gate


def test_score_answer_fails_cross_provider_path() -> None:
    scores = score_answer(
        answer="The answer is grounded [1].",
        source_count=1,
        source_panel_count=1,
        provider_isolated=False,
    )
    assert scores.provider_isolation_score == 0.0
    assert not scores.passes_gate


def test_compare_model_scores_reports_tie_and_winner() -> None:
    tie = compare_model_scores(
        model_a="deepseek-v4-pro",
        score_a=0.9,
        model_b="codex-gpt-5.5-oauth",
        score_b=0.9004,
    )
    assert tie.winner == "tie"

    winner = compare_model_scores(
        model_a="deepseek-v4-pro",
        score_a=0.8,
        model_b="codex-gpt-5.5-oauth",
        score_b=0.9,
    )
    assert winner.winner == "codex-gpt-5.5-oauth"
    assert winner.delta == 0.1
