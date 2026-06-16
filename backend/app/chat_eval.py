"""Deterministic quality/reliability scoring for DanteDash chat evals."""
from __future__ import annotations

from dataclasses import dataclass

from .citations import CitationValidation, validate_citations

QUALITY_GATE = 0.78


@dataclass(frozen=True)
class EvalScores:
    grounding_score: float
    citation_validity_score: float
    insufficiency_calibration_score: float
    source_panel_consistency_score: float
    provider_isolation_score: float
    worker_contract_score: float
    latency_reliability_score: float
    citation_validation: CitationValidation

    @property
    def total(self) -> float:
        return round(
            0.25 * self.grounding_score
            + 0.20 * self.citation_validity_score
            + 0.15 * self.insufficiency_calibration_score
            + 0.15 * self.source_panel_consistency_score
            + 0.10 * self.provider_isolation_score
            + 0.10 * self.worker_contract_score
            + 0.05 * self.latency_reliability_score,
            4,
        )

    @property
    def passes_gate(self) -> bool:
        hard_guards_pass = (
            self.citation_validity_score > 0
            and self.provider_isolation_score > 0
            and self.worker_contract_score > 0
        )
        return hard_guards_pass and self.total >= QUALITY_GATE

    def to_payload(self) -> dict[str, object]:
        return {
            "score": self.total,
            "passes_gate": self.passes_gate,
            "grounding_score": self.grounding_score,
            "citation_validity_score": self.citation_validity_score,
            "insufficiency_calibration_score": self.insufficiency_calibration_score,
            "source_panel_consistency_score": self.source_panel_consistency_score,
            "provider_isolation_score": self.provider_isolation_score,
            "worker_contract_score": self.worker_contract_score,
            "latency_reliability_score": self.latency_reliability_score,
            "citation_validation": self.citation_validation.to_payload(),
        }


@dataclass(frozen=True)
class ModelComparison:
    model_a: str
    model_b: str
    score_a: float
    score_b: float
    winner: str
    delta: float

    def to_payload(self) -> dict[str, object]:
        return {
            "model_a": self.model_a,
            "model_b": self.model_b,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "winner": self.winner,
            "delta": self.delta,
        }


def score_answer(
    *,
    answer: str,
    source_count: int,
    source_panel_count: int,
    expected_insufficient: bool = False,
    provider_isolated: bool = True,
    worker_contract_ok: bool = True,
    latency_ok: bool = True,
) -> EvalScores:
    citation_validation = validate_citations(
        answer,
        source_count=source_count,
        require_citations=not expected_insufficient,
    )
    citation_score = 1.0 if citation_validation.ok else 0.0
    grounding_score = 1.0 if citation_validation.citations and citation_validation.ok else 0.35
    if expected_insufficient:
        lowered = answer.lower()
        insufficiency_score = 1.0 if "not enough" in lowered or "does not cover" in lowered else 0.0
        grounding_score = max(grounding_score, 0.75)
    else:
        insufficiency_score = 1.0

    return EvalScores(
        grounding_score=grounding_score,
        citation_validity_score=citation_score,
        insufficiency_calibration_score=insufficiency_score,
        source_panel_consistency_score=1.0 if source_panel_count == source_count else 0.0,
        provider_isolation_score=1.0 if provider_isolated else 0.0,
        worker_contract_score=1.0 if worker_contract_ok else 0.0,
        latency_reliability_score=1.0 if latency_ok else 0.0,
        citation_validation=citation_validation,
    )


def compare_model_scores(
    *,
    model_a: str,
    score_a: float,
    model_b: str,
    score_b: float,
    tie_epsilon: float = 0.001,
) -> ModelComparison:
    """Compare two model scores for deterministic A/B reporting."""
    delta = round(score_b - score_a, 4)
    if abs(delta) <= tie_epsilon:
        winner = "tie"
    elif delta > 0:
        winner = model_b
    else:
        winner = model_a
    return ModelComparison(
        model_a=model_a,
        model_b=model_b,
        score_a=score_a,
        score_b=score_b,
        winner=winner,
        delta=delta,
    )
