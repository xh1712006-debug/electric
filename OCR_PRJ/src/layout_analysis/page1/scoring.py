"""Config-driven scoring and selection for Page-1 field candidates.

This module deliberately has no dependency on the current extractor. Later
resolvers can translate topology, anchor, alias, separator, validator and OCR
evidence into normalized component signals and use this engine unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .rules import FieldRuleRegistry, SCORING_COMPONENTS


class ConfidenceLevel(IntEnum):
    """Five ordered confidence levels used by candidate resolution."""

    VERY_LOW = 1
    LOW = 2
    MEDIUM = 3
    HIGH = 4
    VERY_HIGH = 5

    @property
    def label(self) -> str:
        return self.name.lower()


CONFIDENCE_LEVEL_MINIMUMS: Mapping[ConfidenceLevel, float] = MappingProxyType({
    ConfidenceLevel.VERY_LOW: 0.0,
    ConfidenceLevel.LOW: 20.0,
    ConfidenceLevel.MEDIUM: 40.0,
    ConfidenceLevel.HIGH: 60.0,
    ConfidenceLevel.VERY_HIGH: 80.0,
})

# Caps remain just below the following band's inclusive lower bound. Scores are
# persisted to four decimals, so these values remain in the intended band.
CONFIDENCE_LEVEL_CEILINGS: Mapping[ConfidenceLevel, float] = MappingProxyType({
    ConfidenceLevel.VERY_LOW: 19.9999,
    ConfidenceLevel.LOW: 39.9999,
    ConfidenceLevel.MEDIUM: 59.9999,
    ConfidenceLevel.HIGH: 79.9999,
    ConfidenceLevel.VERY_HIGH: 100.0,
})


def confidence_level_for_score(score: float) -> ConfidenceLevel:
    """Map a 0..100 score into one of five stable, inclusive-lower bands."""

    numeric = _bounded_number(score, "score", upper=100.0)
    if numeric >= 80.0:
        return ConfidenceLevel.VERY_HIGH
    if numeric >= 60.0:
        return ConfidenceLevel.HIGH
    if numeric >= 40.0:
        return ConfidenceLevel.MEDIUM
    if numeric >= 20.0:
        return ConfidenceLevel.LOW
    return ConfidenceLevel.VERY_LOW


@dataclass(frozen=True)
class HardConstraint:
    """A failed rule that limits confidence even when soft evidence is strong."""

    reason: str
    max_confidence_level: ConfidenceLevel = ConfidenceLevel.LOW

    def __post_init__(self) -> None:
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("HardConstraint.reason must be non-empty.")
        try:
            level = ConfidenceLevel(self.max_confidence_level)
        except (TypeError, ValueError) as exc:
            raise ValueError("HardConstraint.max_confidence_level must be between 1 and 5.") from exc
        object.__setattr__(self, "max_confidence_level", level)

    @classmethod
    def value_validation_failure(cls, reason: str = "hard_value_validation_failed") -> "HardConstraint":
        """Build the approved hard-value failure cap at confidence level 2."""

        return cls(reason=reason, max_confidence_level=ConfidenceLevel.LOW)


@dataclass(frozen=True)
class FieldCandidate:
    """A resolver candidate with normalized 0..1 evidence signals."""

    candidate_id: str
    canonical_field: str
    value: str | None
    component_scores: Mapping[str, float]
    hard_constraints: tuple[HardConstraint, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("FieldCandidate.candidate_id must be non-empty.")
        if not isinstance(self.canonical_field, str) or not self.canonical_field.strip():
            raise ValueError("FieldCandidate.canonical_field must be non-empty.")
        if self.value is not None and not isinstance(self.value, str):
            raise ValueError("FieldCandidate.value must be a string or None.")
        unknown = set(self.component_scores) - set(SCORING_COMPONENTS)
        if unknown:
            raise ValueError(f"Unknown scoring components: {sorted(unknown)}")
        normalized = {
            component: _bounded_number(value, f"component_scores.{component}", upper=1.0)
            for component, value in self.component_scores.items()
        }
        if any(not isinstance(constraint, HardConstraint) for constraint in self.hard_constraints):
            raise ValueError("FieldCandidate.hard_constraints must contain HardConstraint values.")
        object.__setattr__(self, "component_scores", MappingProxyType(normalized))
        object.__setattr__(self, "hard_constraints", tuple(self.hard_constraints))


@dataclass(frozen=True)
class ComponentScore:
    signal: float
    weight: float
    points: float

    def as_dict(self) -> dict[str, float]:
        return {"signal": self.signal, "weight": self.weight, "points": self.points}


@dataclass(frozen=True)
class ScoredCandidate:
    candidate: FieldCandidate
    breakdown: Mapping[str, ComponentScore]
    raw_score: float
    score: float
    uncapped_confidence_level: ConfidenceLevel
    confidence_level: ConfidenceLevel
    hard_cap_level: ConfidenceLevel | None

    @property
    def has_hard_constraints(self) -> bool:
        return bool(self.candidate.hard_constraints)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "canonical_field": self.candidate.canonical_field,
            "value": self.candidate.value,
            "breakdown": {name: item.as_dict() for name, item in self.breakdown.items()},
            "raw_score": self.raw_score,
            "score": self.score,
            "uncapped_confidence": {
                "level": int(self.uncapped_confidence_level),
                "label": self.uncapped_confidence_level.label,
            },
            "confidence": {
                "level": int(self.confidence_level),
                "label": self.confidence_level.label,
            },
            "hard_cap_level": int(self.hard_cap_level) if self.hard_cap_level is not None else None,
            "hard_constraints": [
                {"reason": constraint.reason, "max_confidence_level": int(constraint.max_confidence_level)}
                for constraint in self.candidate.hard_constraints
            ],
        }


@dataclass(frozen=True)
class ScoringDecision:
    canonical_field: str | None
    status: str
    selected_candidate_id: str | None
    leading_candidate_id: str | None
    runner_up_candidate_id: str | None
    winner_margin: float | None
    auto_select_minimum: float
    winner_margin_minimum: float
    reasons: tuple[str, ...]
    candidates: tuple[ScoredCandidate, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_field": self.canonical_field,
            "status": self.status,
            "selected_candidate_id": self.selected_candidate_id,
            "leading_candidate_id": self.leading_candidate_id,
            "runner_up_candidate_id": self.runner_up_candidate_id,
            "winner_margin": self.winner_margin,
            "auto_select_minimum": self.auto_select_minimum,
            "winner_margin_minimum": self.winner_margin_minimum,
            "reasons": list(self.reasons),
            "candidates": [candidate.as_dict() for candidate in self.candidates],
        }


class CandidateScoringEngine:
    """Score candidates and make a deterministic, explainable decision."""

    def __init__(self, registry: FieldRuleRegistry):
        self.registry = registry

    def score_candidate(self, candidate: FieldCandidate) -> ScoredCandidate:
        # Also makes an unknown canonical field a clear configuration error.
        self.registry.field(candidate.canonical_field)
        breakdown: dict[str, ComponentScore] = {}
        for component in SCORING_COMPONENTS:
            signal = candidate.component_scores.get(component, 0.0)
            weight = float(self.registry.scoring.weights[component])
            breakdown[component] = ComponentScore(
                signal=signal,
                weight=weight,
                points=round(signal * weight, 4),
            )
        raw_score = round(sum(item.points for item in breakdown.values()), 4)
        uncapped_level = confidence_level_for_score(raw_score)
        hard_cap = min(
            (constraint.max_confidence_level for constraint in candidate.hard_constraints),
            default=None,
        )
        score = raw_score
        if hard_cap is not None:
            score = min(score, CONFIDENCE_LEVEL_CEILINGS[hard_cap])
        score = round(score, 4)
        return ScoredCandidate(
            candidate=candidate,
            breakdown=MappingProxyType(breakdown),
            raw_score=raw_score,
            score=score,
            uncapped_confidence_level=uncapped_level,
            confidence_level=confidence_level_for_score(score),
            hard_cap_level=hard_cap,
        )

    def decide(self, candidates: Sequence[FieldCandidate]) -> ScoringDecision:
        if not candidates:
            return ScoringDecision(
                canonical_field=None,
                status="review_required",
                selected_candidate_id=None,
                leading_candidate_id=None,
                runner_up_candidate_id=None,
                winner_margin=None,
                auto_select_minimum=self.registry.scoring.auto_select_minimum,
                winner_margin_minimum=self.registry.scoring.winner_margin_minimum,
                reasons=("no_candidates",),
                candidates=(),
            )
        fields = {candidate.canonical_field for candidate in candidates}
        if len(fields) != 1:
            raise ValueError("CandidateScoringEngine.decide accepts candidates for exactly one canonical field.")
        scored = tuple(sorted(
            (self.score_candidate(candidate) for candidate in candidates),
            key=lambda item: (-item.score, item.candidate.candidate_id),
        ))
        leader = scored[0]
        runner_up = scored[1] if len(scored) > 1 else None
        margin = round(leader.score - runner_up.score, 4) if runner_up is not None else None
        reasons: list[str] = []
        if leader.has_hard_constraints:
            reasons.append("leading_candidate_has_hard_constraints")
        if leader.score < self.registry.scoring.auto_select_minimum:
            reasons.append("below_auto_select_minimum")
        if runner_up is not None and margin is not None and margin < self.registry.scoring.winner_margin_minimum:
            reasons.append("winner_margin_below_minimum")
        auto_selected = not reasons
        if auto_selected:
            reasons.append("auto_select_conditions_satisfied")
        return ScoringDecision(
            canonical_field=next(iter(fields)),
            status="auto_selected" if auto_selected else "review_required",
            selected_candidate_id=leader.candidate.candidate_id if auto_selected else None,
            leading_candidate_id=leader.candidate.candidate_id,
            runner_up_candidate_id=runner_up.candidate.candidate_id if runner_up is not None else None,
            winner_margin=margin,
            auto_select_minimum=self.registry.scoring.auto_select_minimum,
            winner_margin_minimum=self.registry.scoring.winner_margin_minimum,
            reasons=tuple(reasons),
            candidates=scored,
        )


def _bounded_number(value: Any, label: str, *, upper: float) -> float:
    if isinstance(value, bool):
        return float(value)
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError(f"{label} must be a finite number.")
    numeric = float(value)
    if not 0.0 <= numeric <= upper:
        raise ValueError(f"{label} must be between 0 and {upper:g}.")
    return numeric
