"""Production integration for Page-1 registry-driven field resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .relationships import RelationshipPolicy, SpatialCandidate, TopologyAnchorResolver
from .rules import FieldRuleRegistry, normalise_rule_text
from .schema import COVER_TABLE_FIELD_NAMES
from .scoring import CandidateScoringEngine, FieldCandidate, HardConstraint
from .value_resolution import AliasSeparatorResolver, AliasValueCandidate, ConfigurableValueValidator


@dataclass(frozen=True)
class _ResolutionCandidate:
    candidate_id: str
    canonical_field: str
    value: str
    bbox: tuple[float, float, float, float]
    source_cell: str | None
    source_block_ids: tuple[str, ...]
    source_bboxes: tuple[tuple[float, float, float, float], ...]
    confidence: float | None
    resolution_method: str
    matched_alias: AliasValueCandidate | None
    matched_label: str | None


class Page1FieldResolutionEngine:
    """Add scoring evidence and safe alias supplements to a Page-1 payload.

    Existing field values are immutable inputs to this layer. Registry aliases
    may populate only a currently-null field and only after the scoring engine
    returns ``auto_selected``. This keeps the company's structure-first table
    ownership authoritative while making every decision auditable.
    """

    def __init__(
        self,
        registry: FieldRuleRegistry,
        relationship_policy: RelationshipPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.aliases = AliasSeparatorResolver(registry)
        self.validators = ConfigurableValueValidator(registry)
        self.relationships = TopologyAnchorResolver(registry, relationship_policy)
        self.scoring = CandidateScoringEngine(registry)

    def integrate(
        self,
        payload: dict[str, Any],
        source_blocks: Sequence[Mapping[str, Any]],
        table_grid: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return additive evidence and safely supplement null payload fields."""

        fields = payload.get("fields")
        source_labels = payload.get("source_labels")
        if not isinstance(fields, dict) or not isinstance(source_labels, dict):
            raise ValueError("Page-1 payload must contain fields and source_labels objects.")

        blocks = tuple(_normalise_block(index, block) for index, block in enumerate(source_blocks))
        block_lookup = {block["block_id"]: block for block in blocks}
        page_width, page_height = _page_dimensions(blocks, table_grid)
        alias_candidates = self._alias_candidates(blocks, fields, source_labels)

        by_field: dict[str, list[_ResolutionCandidate]] = {
            name: [] for name in self.registry.fields
        }
        for field_name in self.registry.fields:
            field = fields.get(field_name)
            if isinstance(field, dict) and isinstance(field.get("text"), str) and field["text"].strip():
                production = self._production_candidate(
                    field_name, field, source_labels.get(field_name), block_lookup
                )
                if production is not None:
                    by_field[field_name].append(production)
            for candidate in alias_candidates.get(field_name, ()):
                if not _duplicates_existing(candidate, by_field[field_name]):
                    by_field[field_name].append(candidate)

        spatial_by_id: dict[str, SpatialCandidate] = {}
        for candidates in by_field.values():
            for candidate in candidates:
                spatial_by_id[candidate.candidate_id] = SpatialCandidate(
                    candidate_id=candidate.candidate_id,
                    bbox=candidate.bbox,
                    page_width=page_width,
                    page_height=page_height,
                    value=candidate.value,
                    source_cell=candidate.source_cell,
                )
        anchors = {
            field_name: tuple(spatial_by_id[item.candidate_id] for item in candidates)
            for field_name, candidates in by_field.items()
            if candidates
        }

        evidence: dict[str, Any] = {}
        applied_source_ids: set[str] = set()
        for field_name in fields:
            if field_name not in self.registry.fields:
                evidence[field_name] = _not_configured_evidence(field_name, fields[field_name])
                continue
            candidates = by_field[field_name]
            if not candidates:
                evidence[field_name] = self._no_candidate_evidence(field_name)
                continue
            decision_candidates: list[FieldCandidate] = []
            details: dict[str, dict[str, Any]] = {}
            for candidate in candidates:
                spatial = self.relationships.resolve(
                    field_name,
                    spatial_by_id[candidate.candidate_id],
                    anchors,
                )
                validation = self.validators.validate(field_name, candidate.value)
                topology_score, topology_items = self._topology_signal(
                    field_name, candidate, spatial.as_dict()["topology"]
                )
                anchor_score = self._anchor_signal(field_name, spatial.anchor_score)
                value_score = self._value_signal(field_name, validation.score)
                alias_score = self._alias_signal(field_name, candidate.matched_alias)
                component_scores = {
                    "topology": topology_score,
                    "anchor": anchor_score,
                    "alias": alias_score,
                    "separator": candidate.matched_alias.separator_score if candidate.matched_alias else 0.0,
                    "value_validation": value_score,
                    "ocr_confidence": _confidence_signal(candidate.confidence),
                }
                constraints = _merge_constraints(spatial.hard_constraints, validation.hard_constraints)
                decision_candidates.append(FieldCandidate(
                    candidate_id=candidate.candidate_id,
                    canonical_field=field_name,
                    value=candidate.value,
                    component_scores=component_scores,
                    hard_constraints=constraints,
                ))
                spatial_dict = spatial.as_dict()
                spatial_dict["topology"] = topology_items
                spatial_dict["topology_score"] = topology_score
                details[candidate.candidate_id] = {
                    "candidate": candidate,
                    "spatial": spatial_dict,
                    "validation": validation.as_dict(),
                    "matched_rule": _matched_rule(candidate, topology_items),
                    "anchor": _matched_anchor(spatial_dict["anchors"]),
                }

            decision = self.scoring.decide(decision_candidates)
            selected_id = decision.selected_candidate_id
            existing = fields.get(field_name)
            applied = False
            structure_owned_null = (
                existing is None
                and field_name in COVER_TABLE_FIELD_NAMES
                and payload.get("layout_strategy", {}).get("cover_fields") == "table_structure"
            )
            selected_details = details.get(selected_id) if selected_id is not None else None
            topology_owns_candidate = bool(selected_details and any(
                item.get("rule_type") == "cover_slot" and item.get("status") == "matched"
                for item in selected_details["spatial"]["topology"]
            ))
            anchor_owns_candidate = bool(selected_details and selected_details["anchor"])
            cover_ownership_unconfirmed = (
                existing is None
                and selected_id is not None
                and field_name in COVER_TABLE_FIELD_NAMES
                and not structure_owned_null
                and not topology_owns_candidate
                and not anchor_owns_candidate
            )
            if (
                existing is None
                and selected_id is not None
                and not structure_owned_null
                and not cover_ownership_unconfirmed
            ):
                selected = details[selected_id]["candidate"]
                fields[field_name] = _field_from_candidate(selected, payload.get("page_number", 1))
                source_labels[field_name] = _source_label_from_candidate(
                    selected, payload.get("page_number", 1)
                )
                applied = True
                applied_source_ids.update(selected.source_block_ids)
                warnings = payload.get("warnings")
                if isinstance(warnings, list):
                    blocked = {
                        f"missing_required_field:{field_name}",
                        f"empty_required_field:{field_name}",
                    }
                    warnings[:] = [warning for warning in warnings if warning not in blocked]

            leading_id = decision.leading_candidate_id
            leading = details[leading_id] if leading_id is not None else None
            decision_dict = decision.as_dict()
            evidence_status = decision.status
            if structure_owned_null or cover_ownership_unconfirmed:
                evidence_status = "review_required"
                decision_dict["status"] = "review_required"
                decision_dict["selected_candidate_id"] = None
                decision_dict["reasons"] = [
                    *decision_dict["reasons"],
                    (
                        "structure_owned_null_not_overridden"
                        if structure_owned_null
                        else "cover_ownership_evidence_required"
                    ),
                ]
            leading_scored = next(
                (item for item in decision_dict["candidates"] if item["candidate_id"] == leading_id),
                None,
            )
            evidence[field_name] = {
                "canonical_field": field_name,
                "resolution_method": (
                    "registry_alias_auto_select"
                    if applied
                    else "table_structure_null_preserved"
                    if structure_owned_null
                    else "cover_ownership_unconfirmed"
                    if cover_ownership_unconfirmed
                    else leading["candidate"].resolution_method if leading else "no_candidate"
                ),
                "status": evidence_status,
                "preserved_existing_value": existing is not None,
                "applied_to_null_field": applied,
                "matched_rule": leading["matched_rule"] if leading else None,
                "anchor": leading["anchor"] if leading else None,
                "topology": leading["spatial"]["topology"] if leading else [],
                "value_validation": leading["validation"] if leading else None,
                "score_breakdown": leading_scored["breakdown"] if leading_scored else None,
                "raw_score": leading_scored["raw_score"] if leading_scored else None,
                "effective_score": leading_scored["score"] if leading_scored else None,
                "confidence": leading_scored["confidence"] if leading_scored else None,
                "winner_margin": decision.winner_margin,
                "decision": decision_dict,
            }
        if applied_source_ids and isinstance(payload.get("unassigned_blocks"), list):
            payload["unassigned_blocks"] = [
                block for block in payload["unassigned_blocks"]
                if str(block.get("block_id")) not in applied_source_ids
            ]
            summary = payload.get("summary")
            if isinstance(summary, dict):
                summary["unassigned_blocks"] = len(payload["unassigned_blocks"])
        return evidence

    def _production_candidate(
        self,
        field_name: str,
        field: Mapping[str, Any],
        source_label: Any,
        block_lookup: Mapping[str, Mapping[str, Any]],
    ) -> _ResolutionCandidate | None:
        bboxes = _field_bboxes(field)
        if not bboxes:
            return None
        identifiers = tuple(str(item) for item in field.get("source_block_ids", ()))
        label_ids = (
            tuple(str(item) for item in source_label.get("source_block_ids", ()))
            if isinstance(source_label, Mapping) else ()
        )
        ordered_ids = tuple(dict.fromkeys((*label_ids, *identifiers)))
        texts = [str(block_lookup[item]["text"]) for item in ordered_ids if item in block_lookup]
        label_text = (
            str(source_label.get("text"))
            if isinstance(source_label, Mapping) and source_label.get("text")
            else str(field.get("source_label") or field.get("matched_label") or "") or None
        )
        matched_alias = self._best_alias(field_name, texts, label_text)
        return _ResolutionCandidate(
            candidate_id=f"production:{field_name}",
            canonical_field=field_name,
            value=str(field["text"]).strip(),
            bbox=_union_bbox(bboxes),
            source_cell=str(field["source_cell"]) if field.get("source_cell") else None,
            source_block_ids=identifiers,
            source_bboxes=bboxes,
            confidence=_number_or_none(field.get("confidence")),
            resolution_method=_resolution_method(field_name, field),
            matched_alias=matched_alias,
            matched_label=label_text,
        )

    def _alias_candidates(
        self,
        blocks: Sequence[Mapping[str, Any]],
        fields: Mapping[str, Any],
        source_labels: Mapping[str, Any],
    ) -> dict[str, tuple[_ResolutionCandidate, ...]]:
        found: dict[str, list[_ResolutionCandidate]] = {name: [] for name in self.registry.fields}
        for index, block in enumerate(blocks):
            matches = self.aliases.resolve_text(str(block["text"]))
            for match in matches:
                value = match.value_text
                members = [block]
                if not value:
                    adjacent = _adjacent_value_block(index, blocks, self.aliases)
                    if adjacent is None:
                        continue
                    value = str(adjacent["text"]).strip()
                    members.append(adjacent)
                if not value:
                    continue
                identifiers = tuple(str(member["block_id"]) for member in members)
                bboxes = tuple(tuple(float(item) for item in member["bbox_pixel"]) for member in members)
                source_cell = _source_cell_for_alias(match.canonical_field, identifiers, fields, source_labels)
                confidences = [_number_or_none(member.get("recognition_score")) for member in members]
                numeric_confidences = [item for item in confidences if item is not None]
                found[match.canonical_field].append(_ResolutionCandidate(
                    candidate_id=(
                        f"registry-alias:{match.canonical_field}:{block['block_id']}:"
                        f"{match.start}:{match.end}"
                    ),
                    canonical_field=match.canonical_field,
                    value=value,
                    bbox=_union_bbox(bboxes),
                    source_cell=source_cell,
                    source_block_ids=identifiers,
                    source_bboxes=bboxes,
                    confidence=(sum(numeric_confidences) / len(numeric_confidences)) if numeric_confidences else None,
                    resolution_method="registry_alias_candidate",
                    matched_alias=match,
                    matched_label=match.matched_text,
                ))
        return {
            name: tuple(sorted(items, key=lambda item: item.candidate_id))
            for name, items in found.items()
        }

    def _best_alias(
        self,
        field_name: str,
        texts: Sequence[str],
        label_text: str | None,
    ) -> AliasValueCandidate | None:
        matches = self.aliases.resolve_blocks(texts) if texts else ()
        eligible = [item for item in matches if item.canonical_field == field_name]
        if not eligible and label_text:
            eligible = [
                item for item in self.aliases.resolve_text(label_text)
                if item.canonical_field == field_name
            ]
        return max(
            eligible,
            key=lambda item: (len(normalise_rule_text(item.alias)), item.separator_present),
            default=None,
        )

    def _topology_signal(
        self,
        field_name: str,
        candidate: _ResolutionCandidate,
        topology: list[dict[str, Any]],
    ) -> tuple[float, list[dict[str, Any]]]:
        rules = [
            rule for rule in self.registry.field(field_name).topology_rules
            if rule.get("status", "active") == "active"
        ]
        if not rules:
            return 1.0, []
        output = list(topology)
        source_rules = [rule for rule in rules if rule.get("type") == "source_policy"]
        if source_rules:
            matched = bool(candidate.value and (candidate.matched_alias or candidate.resolution_method != "registry_alias_candidate"))
            output = [item for item in output if item.get("rule_type") != "source_policy"]
            output.extend({
                "rule_type": "source_policy",
                "status": "matched" if matched else "mismatched",
                "score": 1.0 if matched else 0.0,
                "expected": str(rule.get("value", "")),
                "actual": "inline_or_adjacent" if matched else None,
                "reason": "source_policy_matched" if matched else "source_policy_mismatch",
            } for rule in source_rules)
        evaluated = [float(item["score"]) for item in output if item.get("status") != "not_evaluated"]
        return (min(evaluated) if evaluated else 0.0), output

    def _anchor_signal(self, field_name: str, score: float) -> float:
        rules = [
            rule for rule in self.registry.field(field_name).anchor_rules
            if rule.get("status", "active") == "active"
        ]
        return score if rules else 1.0

    def _value_signal(self, field_name: str, score: float) -> float:
        rules = [
            rule for rule in self.registry.field(field_name).value_rules
            if rule.get("status", "active") == "active"
        ]
        return score if rules else 1.0

    def _alias_signal(self, field_name: str, alias: AliasValueCandidate | None) -> float:
        rules = self.registry.field(field_name).active_aliases
        return (1.0 if alias is not None else 0.0) if rules else 1.0

    def _no_candidate_evidence(self, field_name: str) -> dict[str, Any]:
        decision = self.scoring.decide([]).as_dict()
        decision["canonical_field"] = field_name
        return {
            "canonical_field": field_name,
            "resolution_method": "no_candidate",
            "status": "review_required",
            "preserved_existing_value": False,
            "applied_to_null_field": False,
            "matched_rule": None,
            "anchor": None,
            "topology": [],
            "value_validation": None,
            "score_breakdown": None,
            "raw_score": None,
            "effective_score": None,
            "confidence": None,
            "winner_margin": None,
            "decision": decision,
        }


def _normalise_block(index: int, block: Mapping[str, Any]) -> dict[str, Any]:
    bbox = block.get("bbox_pixel")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        polygon = block.get("polygon")
        if not isinstance(polygon, (list, tuple)) or len(polygon) < 3:
            raise ValueError("Page-1 resolution blocks require bbox_pixel or polygon geometry.")
        xs = [float(point[0]) for point in polygon]
        ys = [float(point[1]) for point in polygon]
        bbox = [min(xs), min(ys), max(xs), max(ys)]
    return {
        **block,
        "block_id": str(block.get("block_id", f"ocr_{index}")),
        "text": " ".join(str(block.get("text", "")).split()),
        "bbox_pixel": [float(item) for item in bbox],
    }


def _page_dimensions(
    blocks: Sequence[Mapping[str, Any]],
    table_grid: Mapping[str, Any],
) -> tuple[float, float]:
    width = _number_or_none(table_grid.get("image_width"))
    height = _number_or_none(table_grid.get("image_height"))
    maximum_x = max((float(block["bbox_pixel"][2]) for block in blocks), default=1.0)
    maximum_y = max((float(block["bbox_pixel"][3]) for block in blocks), default=1.0)
    return max(width or 0.0, maximum_x, 1.0), max(height or 0.0, maximum_y, 1.0)


def _field_bboxes(field: Mapping[str, Any]) -> tuple[tuple[float, float, float, float], ...]:
    raw = field.get("source_bboxes", ())
    return tuple(
        tuple(float(item) for item in bbox)
        for bbox in raw
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4 and float(bbox[2]) > float(bbox[0]) and float(bbox[3]) > float(bbox[1])
    )


def _union_bbox(bboxes: Sequence[Sequence[float]]) -> tuple[float, float, float, float]:
    return (
        min(float(item[0]) for item in bboxes),
        min(float(item[1]) for item in bboxes),
        max(float(item[2]) for item in bboxes),
        max(float(item[3]) for item in bboxes),
    )


def _number_or_none(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _confidence_signal(value: float | None) -> float:
    if value is None:
        return 0.0
    numeric = value / 100.0 if value > 1.0 else value
    return max(0.0, min(1.0, numeric))


def _duplicates_existing(candidate: _ResolutionCandidate, existing: Sequence[_ResolutionCandidate]) -> bool:
    normalized = normalise_rule_text(candidate.value)
    return any(
        normalise_rule_text(item.value) == normalized
        and bool(set(item.source_block_ids) & set(candidate.source_block_ids))
        for item in existing
    )


def _adjacent_value_block(
    index: int,
    blocks: Sequence[Mapping[str, Any]],
    aliases: AliasSeparatorResolver,
) -> Mapping[str, Any] | None:
    label = blocks[index]
    x1, y1, x2, y2 = (float(item) for item in label["bbox_pixel"])
    height = max(1.0, y2 - y1)
    candidates: list[tuple[int, float, Mapping[str, Any]]] = []
    for other in blocks:
        if other is label or not str(other["text"]).strip():
            continue
        if aliases.resolve_text(str(other["text"])):
            continue
        ox1, oy1, ox2, oy2 = (float(item) for item in other["bbox_pixel"])
        other_height = max(1.0, oy2 - oy1)
        row_error = abs((oy1 + oy2) / 2 - (y1 + y2) / 2) / max(height, other_height)
        if ox1 >= x1 and row_error <= 1.25:
            candidates.append((0, max(0.0, ox1 - x2) + row_error, other))
            continue
        vertical_gap = oy1 - y2
        horizontal_alignment = abs(ox1 - x1)
        if 0 <= vertical_gap <= height * 3 and horizontal_alignment <= max(100.0, (x2 - x1) * 0.6):
            candidates.append((1, vertical_gap + horizontal_alignment / max(1.0, x2 - x1), other))
    return min(candidates, key=lambda item: (item[0], item[1], str(item[2]["block_id"])))[2] if candidates else None


def _source_cell_for_alias(
    field_name: str,
    identifiers: Sequence[str],
    fields: Mapping[str, Any],
    source_labels: Mapping[str, Any],
) -> str | None:
    for evidence in (fields.get(field_name), source_labels.get(field_name)):
        if not isinstance(evidence, Mapping) or not evidence.get("source_cell"):
            continue
        source_ids = {str(item) for item in evidence.get("source_block_ids", ())}
        if not source_ids or source_ids.intersection(identifiers):
            return str(evidence["source_cell"])
    return None


def _resolution_method(field_name: str, field: Mapping[str, Any]) -> str:
    if field.get("extraction_method"):
        return str(field["extraction_method"])
    if field_name == "ticket_number":
        return "ticket_number_pattern"
    if field_name in {"page_reference", "page_number", "total_pages"}:
        return "pagination_pattern"
    if field.get("source_cell") and "cover_row_" in str(field["source_cell"]):
        return "table_structure"
    return "legacy_label_extractor"


def _merge_constraints(
    first: Sequence[HardConstraint],
    second: Sequence[HardConstraint],
) -> tuple[HardConstraint, ...]:
    unique: dict[tuple[str, int], HardConstraint] = {}
    for item in (*first, *second):
        unique[(item.reason, int(item.max_confidence_level))] = item
    return tuple(unique[key] for key in sorted(unique))


def _matched_rule(
    candidate: _ResolutionCandidate,
    topology: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if candidate.matched_alias is not None:
        return {
            "type": "alias",
            "value": candidate.matched_alias.alias,
            "origin": candidate.matched_alias.alias_origin,
            "matched_text": candidate.matched_alias.matched_text,
            "separator_present": candidate.matched_alias.separator_present,
        }
    matched_topology = next((item for item in topology if item.get("status") == "matched"), None)
    if matched_topology:
        return {
            "type": str(matched_topology.get("rule_type")),
            "expected": matched_topology.get("expected"),
            "origin": "built_in",
        }
    if candidate.matched_label:
        return {"type": "legacy_label", "value": candidate.matched_label, "origin": "built_in"}
    return None


def _matched_anchor(anchors: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    return next((dict(item) for item in anchors if item.get("reason") == "anchor_matched"), None)


def _field_from_candidate(candidate: _ResolutionCandidate, page_number: Any) -> dict[str, Any]:
    return {
        "text": candidate.value,
        "matched_label": candidate.matched_label,
        "source_label": candidate.matched_label,
        "extraction_method": "registry_alias_auto_select",
        "source_page": int(page_number),
        "source_cell": candidate.source_cell,
        "source_block_ids": list(candidate.source_block_ids),
        "source_bboxes": [list(item) for item in candidate.source_bboxes],
        "confidence": round(candidate.confidence, 4) if candidate.confidence is not None else None,
    }


def _source_label_from_candidate(candidate: _ResolutionCandidate, page_number: Any) -> dict[str, Any]:
    label_bbox = list(candidate.source_bboxes[0]) if candidate.source_bboxes else None
    return {
        "text": candidate.matched_label,
        "canonical_field": candidate.canonical_field,
        "source_page": int(page_number),
        "source_cell": candidate.source_cell,
        "source_block_ids": [candidate.source_block_ids[0]] if candidate.source_block_ids else [],
        "source_bboxes": [label_bbox] if label_bbox else [],
        "confidence": round(candidate.confidence, 4) if candidate.confidence is not None else None,
    }


def _not_configured_evidence(field_name: str, field: Any) -> dict[str, Any]:
    return {
        "canonical_field": field_name,
        "resolution_method": "derived_or_unconfigured",
        "status": "not_configured",
        "preserved_existing_value": field is not None,
        "applied_to_null_field": False,
        "matched_rule": None,
        "anchor": None,
        "topology": [],
        "value_validation": None,
        "score_breakdown": None,
        "raw_score": None,
        "effective_score": None,
        "confidence": None,
        "winner_margin": None,
        "decision": None,
    }
