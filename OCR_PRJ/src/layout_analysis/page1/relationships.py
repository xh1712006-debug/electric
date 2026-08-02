"""DPI-independent topology and anchor relationships for Page-1 candidates."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import re
from typing import Any, Mapping, Sequence

from .rules import FieldRuleRegistry
from .scoring import ConfidenceLevel, FieldCandidate, HardConstraint


class SpatialRelation(str, Enum):
    ABOVE = "above"
    BELOW = "below"
    LEFT = "left"
    RIGHT = "right"
    SAME_ROW = "same_row"
    SAME_COLUMN = "same_column"
    SAME_ROW_RIGHT = "same_row_right"


@dataclass(frozen=True)
class RelationshipPolicy:
    """Tunable limits expressed in text heights rather than pixels."""

    same_row_tolerance: float = 0.75
    same_column_tolerance: float = 2.0
    direction_max_distance: float = 8.0
    same_axis_max_distance: float = 12.0
    minimum_orthogonal_overlap: float = 0.20

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
                raise ValueError(f"RelationshipPolicy.{name} must be a finite non-negative number.")


@dataclass(frozen=True)
class SpatialCandidate:
    """A field or OCR candidate with explicit page and topology evidence."""

    candidate_id: str
    bbox: tuple[float, float, float, float]
    page_width: float
    page_height: float
    value: str | None = None
    source_cell: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id.strip():
            raise ValueError("SpatialCandidate.candidate_id must be non-empty.")
        if len(self.bbox) != 4:
            raise ValueError("SpatialCandidate.bbox must contain x1, y1, x2, y2.")
        box = tuple(float(value) for value in self.bbox)
        if not all(math.isfinite(value) for value in box) or box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("SpatialCandidate.bbox must have finite positive width and height.")
        if self.page_width <= 0 or self.page_height <= 0:
            raise ValueError("SpatialCandidate page dimensions must be positive.")
        if box[0] < 0 or box[1] < 0 or box[2] > self.page_width or box[3] > self.page_height:
            raise ValueError("SpatialCandidate.bbox must stay inside its page dimensions.")
        object.__setattr__(self, "bbox", box)
        object.__setattr__(self, "page_width", float(self.page_width))
        object.__setattr__(self, "page_height", float(self.page_height))

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    @property
    def center(self) -> tuple[float, float]:
        return ((self.bbox[0] + self.bbox[2]) / 2, (self.bbox[1] + self.bbox[3]) / 2)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "bbox": list(self.bbox),
            "page_width": self.page_width,
            "page_height": self.page_height,
            "value": self.value,
            "source_cell": self.source_cell,
        }


@dataclass(frozen=True)
class RelationEvidence:
    relation: SpatialRelation
    matched: bool
    normalized_distance: float
    alignment_error: float
    orthogonal_overlap: float
    score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "relation": self.relation.value,
            "matched": self.matched,
            "normalized_distance": self.normalized_distance,
            "alignment_error": self.alignment_error,
            "orthogonal_overlap": self.orthogonal_overlap,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TopologyEvidence:
    rule_type: str
    status: str
    score: float
    expected: str
    actual: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class AnchorEvidence:
    anchor_field: str
    anchor_candidate_id: str | None
    relation: SpatialRelation
    relation_evidence: RelationEvidence | None
    score: float
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "anchor_field": self.anchor_field,
            "anchor_candidate_id": self.anchor_candidate_id,
            "relation": self.relation.value,
            "relation_evidence": self.relation_evidence.as_dict() if self.relation_evidence else None,
            "score": self.score,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SpatialResolution:
    canonical_field: str
    candidate: SpatialCandidate
    topology: tuple[TopologyEvidence, ...]
    anchors: tuple[AnchorEvidence, ...]
    topology_score: float
    anchor_score: float
    hard_constraints: tuple[HardConstraint, ...]
    eligible: bool

    def to_field_candidate(
        self,
        *,
        component_scores: Mapping[str, float] | None = None,
    ) -> FieldCandidate:
        scores = dict(component_scores or {})
        scores["topology"] = self.topology_score
        scores["anchor"] = self.anchor_score
        return FieldCandidate(
            candidate_id=self.candidate.candidate_id,
            canonical_field=self.canonical_field,
            value=self.candidate.value,
            component_scores=scores,
            hard_constraints=self.hard_constraints,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_field": self.canonical_field,
            "candidate": self.candidate.as_dict(),
            "topology": [item.as_dict() for item in self.topology],
            "anchors": [item.as_dict() for item in self.anchors],
            "topology_score": self.topology_score,
            "anchor_score": self.anchor_score,
            "hard_constraints": [
                {"reason": item.reason, "max_confidence_level": int(item.max_confidence_level)}
                for item in self.hard_constraints
            ],
            "eligible": self.eligible,
        }


class TopologyAnchorResolver:
    """Resolve registry topology and anchor rules without extractor coupling."""

    def __init__(self, registry: FieldRuleRegistry, policy: RelationshipPolicy | None = None):
        self.registry = registry
        self.policy = policy or RelationshipPolicy()

    def relate(
        self,
        candidate: SpatialCandidate,
        anchor: SpatialCandidate,
        relation: SpatialRelation | str,
    ) -> RelationEvidence:
        relation = SpatialRelation(relation)
        _same_page_space(candidate, anchor)
        scale = max(1.0, (candidate.height + anchor.height) / 2)
        cx, cy = candidate.center
        ax, ay = anchor.center
        horizontal_overlap = _overlap(candidate.bbox[0:3:2], anchor.bbox[0:3:2])
        vertical_overlap = _overlap(candidate.bbox[1:4:2], anchor.bbox[1:4:2])
        row_error = abs(cy - ay) / scale
        column_error = min(
            abs(candidate.bbox[0] - anchor.bbox[0]),
            abs(cx - ax),
            abs(candidate.bbox[2] - anchor.bbox[2]),
        ) / scale
        horizontal_gap = max(0.0, max(candidate.bbox[0], anchor.bbox[0]) - min(candidate.bbox[2], anchor.bbox[2])) / scale
        vertical_gap = max(0.0, max(candidate.bbox[1], anchor.bbox[1]) - min(candidate.bbox[3], anchor.bbox[3])) / scale

        direction_ok = True
        alignment_ok = True
        limit = self.policy.direction_max_distance
        distance = vertical_gap
        alignment = column_error
        overlap = horizontal_overlap
        if relation == SpatialRelation.ABOVE:
            direction_ok = cy < ay
            alignment_ok = overlap >= self.policy.minimum_orthogonal_overlap or column_error <= self.policy.same_column_tolerance
        elif relation == SpatialRelation.BELOW:
            direction_ok = cy > ay
            alignment_ok = overlap >= self.policy.minimum_orthogonal_overlap or column_error <= self.policy.same_column_tolerance
        elif relation == SpatialRelation.LEFT:
            direction_ok = cx < ax
            alignment_ok = vertical_overlap >= self.policy.minimum_orthogonal_overlap or row_error <= self.policy.same_row_tolerance
            distance, alignment, overlap = horizontal_gap, row_error, vertical_overlap
        elif relation == SpatialRelation.RIGHT:
            direction_ok = cx > ax
            alignment_ok = vertical_overlap >= self.policy.minimum_orthogonal_overlap or row_error <= self.policy.same_row_tolerance
            distance, alignment, overlap = horizontal_gap, row_error, vertical_overlap
        elif relation == SpatialRelation.SAME_ROW:
            alignment_ok = row_error <= self.policy.same_row_tolerance
            distance, alignment, overlap = horizontal_gap, row_error, vertical_overlap
            limit = self.policy.same_axis_max_distance
        elif relation == SpatialRelation.SAME_COLUMN:
            alignment_ok = horizontal_overlap >= self.policy.minimum_orthogonal_overlap or column_error <= self.policy.same_column_tolerance
            distance, alignment, overlap = vertical_gap, column_error, horizontal_overlap
            limit = self.policy.same_axis_max_distance
        elif relation == SpatialRelation.SAME_ROW_RIGHT:
            direction_ok = cx > ax
            alignment_ok = row_error <= self.policy.same_row_tolerance
            distance, alignment, overlap = horizontal_gap, row_error, vertical_overlap
            limit = self.policy.same_axis_max_distance

        distance_ok = distance <= limit
        matched = direction_ok and alignment_ok and distance_ok
        if not direction_ok:
            reason = "direction_mismatch"
        elif not alignment_ok:
            reason = "axis_alignment_mismatch"
        elif not distance_ok:
            reason = "normalized_distance_exceeded"
        else:
            reason = "relation_matched"
        score = max(0.0, 1.0 - distance / max(1.0, limit)) if matched else 0.0
        return RelationEvidence(
            relation=relation,
            matched=matched,
            normalized_distance=round(distance, 4),
            alignment_error=round(alignment, 4),
            orthogonal_overlap=round(overlap, 4),
            score=round(score, 4),
            reason=reason,
        )

    def resolve(
        self,
        canonical_field: str,
        candidate: SpatialCandidate,
        anchors: Mapping[str, Sequence[SpatialCandidate]] | None = None,
    ) -> SpatialResolution:
        field = self.registry.field(canonical_field)
        topology = tuple(
            self._topology(candidate, rule)
            for rule in field.topology_rules
            if rule.get("status", "active") == "active"
        )
        anchor_results = tuple(
            self._anchor(candidate, rule, anchors or {})
            for rule in field.anchor_rules
            if rule.get("status", "active") == "active" and rule.get("type") == "field_relation"
        )
        mismatches = [item for item in topology if item.status == "mismatched"]
        hard_constraints = tuple(
            HardConstraint(
                reason=f"topology_mismatch:{item.expected}",
                max_confidence_level=ConfidenceLevel.LOW,
            )
            for item in mismatches
        )
        evaluated_topology = [item.score for item in topology if item.status != "not_evaluated"]
        topology_score = min(evaluated_topology) if evaluated_topology else 0.0
        anchor_score = max((item.score for item in anchor_results), default=0.0)
        return SpatialResolution(
            canonical_field=canonical_field,
            candidate=candidate,
            topology=topology,
            anchors=anchor_results,
            topology_score=round(topology_score, 4),
            anchor_score=round(anchor_score, 4),
            hard_constraints=hard_constraints,
            eligible=not hard_constraints,
        )

    def _anchor(
        self,
        candidate: SpatialCandidate,
        rule: Mapping[str, Any],
        anchors: Mapping[str, Sequence[SpatialCandidate]],
    ) -> AnchorEvidence:
        anchor_field = str(rule.get("field", ""))
        relation = SpatialRelation(str(rule.get("relation", "")))
        available = tuple(anchors.get(anchor_field, ()))
        if not available:
            return AnchorEvidence(anchor_field, None, relation, None, 0.0, "anchor_unavailable")
        evaluated = [(anchor, self.relate(candidate, anchor, relation)) for anchor in available]
        matched = [(anchor, evidence) for anchor, evidence in evaluated if evidence.matched]
        if not matched:
            anchor, evidence = min(evaluated, key=lambda item: item[1].normalized_distance)
            return AnchorEvidence(anchor_field, anchor.candidate_id, relation, evidence, 0.0, evidence.reason)
        anchor, evidence = max(matched, key=lambda item: (item[1].score, item[0].candidate_id))
        return AnchorEvidence(anchor_field, anchor.candidate_id, relation, evidence, evidence.score, "anchor_matched")

    def _topology(self, candidate: SpatialCandidate, rule: Mapping[str, Any]) -> TopologyEvidence:
        rule_type = str(rule.get("type", ""))
        if rule_type == "page_region":
            expected = str(rule.get("region", ""))
            if expected != "top_right_header":
                return TopologyEvidence(rule_type, "not_evaluated", 0.0, expected, None, "unsupported_page_region")
            cx, cy = candidate.center
            matched = cx >= candidate.page_width * 0.50 and cy <= candidate.page_height * 0.22
            return TopologyEvidence(
                rule_type, "matched" if matched else "mismatched", 1.0 if matched else 0.0,
                expected, _page_region(candidate), "page_region_matched" if matched else "page_region_mismatch",
            )
        if rule_type == "cover_slot":
            row = int(rule.get("row", -1))
            slot = str(rule.get("slot", ""))
            expected = f"cover_row_{row}:{slot}"
            actual = _cover_cell(candidate.source_cell)
            if actual is None:
                return TopologyEvidence(rule_type, "not_evaluated", 0.0, expected, None, "source_cell_unavailable")
            matched = actual == expected
            return TopologyEvidence(
                rule_type, "matched" if matched else "mismatched", 1.0 if matched else 0.0,
                expected, actual, "cover_slot_matched" if matched else "cover_slot_mismatch",
            )
        return TopologyEvidence(rule_type, "not_evaluated", 0.0, rule_type, None, "topology_rule_not_spatial")


def _same_page_space(first: SpatialCandidate, second: SpatialCandidate) -> None:
    if not math.isclose(first.page_width, second.page_width) or not math.isclose(first.page_height, second.page_height):
        raise ValueError("Spatial relationships require candidates in the same page coordinate space.")


def _overlap(first: tuple[float, float], second: tuple[float, float]) -> float:
    intersection = max(0.0, min(first[1], second[1]) - max(first[0], second[0]))
    shortest = max(1.0, min(first[1] - first[0], second[1] - second[0]))
    return intersection / shortest


def _cover_cell(source_cell: str | None) -> str | None:
    if not source_cell:
        return None
    match = re.search(r"(?:^|:)cover_row_(\d+):(left|right|right_primary|right_secondary)(?::|$)", source_cell)
    return f"cover_row_{match.group(1)}:{match.group(2)}" if match else None


def _page_region(candidate: SpatialCandidate) -> str:
    cx, cy = candidate.center
    vertical = "header" if cy <= candidate.page_height * 0.22 else "body"
    horizontal = "right" if cx >= candidate.page_width * 0.50 else "left"
    return f"{horizontal}_{vertical}"
