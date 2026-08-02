"""Registry-driven alias, separator and value validation for Page-1 fields."""

from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Any, Mapping, Sequence
import unicodedata

from ..pagination import PAGE_REFERENCE_PATTERN, TICKET_PATTERN
from .rules import AliasRule, FieldRuleRegistry, normalise_rule_text
from .scoring import FieldCandidate, HardConstraint


SUPPORTED_VALUE_RULES = frozenset({
    "unit_suffix",
    "endswith",
    "startswith",
    "regex",
    "enum",
    "numeric",
    "numeric_range",
    "version",
    "ticket_number",
    # Existing default-registry rules retained for compatibility.
    "year",
    "page_reference",
})
_RULE_METADATA = {"type", "required", "origin", "status", "created_by", "created_at"}
_NUMBER_PATTERN = re.compile(r"[+-]?\d+(?:[.,]\d+)?")
_VERSION_PATTERN = re.compile(r"[vV]?\d+(?:\.\d+){1,5}(?:[-+][A-Za-z0-9.-]+)?")


class ValueRuleConfigurationError(ValueError):
    """Raised before runtime when a configured value rule is malformed."""


@dataclass(frozen=True)
class SeparatorSplit:
    label_text: str
    value_text: str
    separator_present: bool
    separator: str | None

    def as_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class AliasValueCandidate:
    candidate_id: str
    canonical_field: str
    alias: str
    alias_origin: str
    matched_text: str
    label_text: str
    value_text: str
    separator_present: bool
    separator: str | None
    start: int
    end: int
    source_block_indices: tuple[int, ...]
    alias_score: float = 1.0

    @property
    def separator_score(self) -> float:
        return 1.0 if self.separator_present else 0.0

    def to_field_candidate(
        self,
        validation: "ValueValidationResult",
        *,
        component_scores: Mapping[str, float] | None = None,
    ) -> FieldCandidate:
        if validation.canonical_field != self.canonical_field:
            raise ValueError("Alias candidate and value validation must use the same canonical field.")
        scores = dict(component_scores or {})
        scores.update({
            "alias": self.alias_score,
            "separator": self.separator_score,
            "value_validation": validation.score,
        })
        return FieldCandidate(
            candidate_id=self.candidate_id,
            canonical_field=self.canonical_field,
            value=self.value_text,
            component_scores=scores,
            hard_constraints=validation.hard_constraints,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            **vars(self),
            "source_block_indices": list(self.source_block_indices),
            "separator_score": self.separator_score,
        }


@dataclass(frozen=True)
class RuleValidation:
    rule_type: str
    required: bool
    status: str
    reason: str
    normalized_value: str
    origin: str

    def as_dict(self) -> dict[str, Any]:
        return vars(self).copy()


@dataclass(frozen=True)
class ValueValidationResult:
    canonical_field: str
    value: str
    normalized_value: str
    status: str
    score: float
    rules: tuple[RuleValidation, ...]
    hard_constraints: tuple[HardConstraint, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "canonical_field": self.canonical_field,
            "value": self.value,
            "normalized_value": self.normalized_value,
            "status": self.status,
            "score": self.score,
            "rules": [item.as_dict() for item in self.rules],
            "hard_constraints": [
                {"reason": item.reason, "max_confidence_level": int(item.max_confidence_level)}
                for item in self.hard_constraints
            ],
        }


def split_label_value(text: str) -> SeparatorSplit:
    """Split once on ASCII or full-width colon while preserving original text."""

    positions = [(text.find(separator), separator) for separator in (":", "：") if text.find(separator) >= 0]
    if not positions:
        return SeparatorSplit(text.strip(), "", False, None)
    position, separator = min(positions, key=lambda item: item[0])
    return SeparatorSplit(text[:position].strip(), text[position + 1:].strip(), True, separator)


class AliasSeparatorResolver:
    """Resolve every active registry alias using longest/specific matching."""

    def __init__(self, registry: FieldRuleRegistry):
        self.registry = registry
        aliases: list[tuple[str, AliasRule]] = []
        for canonical_field, field in registry.fields.items():
            aliases.extend((canonical_field, alias) for alias in field.active_aliases)
        self.aliases = tuple(aliases)

    def resolve_text(self, text: str) -> tuple[AliasValueCandidate, ...]:
        return self.resolve_blocks([text])

    def resolve_blocks(self, blocks: Sequence[str]) -> tuple[AliasValueCandidate, ...]:
        if any(not isinstance(block, str) for block in blocks):
            raise ValueError("AliasSeparatorResolver blocks must be strings.")
        joined, offsets = _join_blocks(blocks)
        normalized, positions = _normalise_with_positions(joined)
        raw: list[dict[str, Any]] = []
        seen: set[tuple[str, str, int, int]] = set()
        for canonical_field, alias in self.aliases:
            normalized_alias = alias.normalized_value
            if not normalized_alias:
                continue
            pattern = re.compile(rf"(?<![a-z0-9]){re.escape(normalized_alias)}(?![a-z0-9])")
            for match in pattern.finditer(normalized):
                start = positions[match.start()]
                end = positions[match.end() - 1] + 1
                key = (canonical_field, normalized_alias, start, end)
                if (
                    key in seen
                    or not _alias_position_is_safe(joined, start, end)
                    or not _short_alias_is_safe(joined, end, normalized_alias)
                ):
                    continue
                seen.add(key)
                raw.append({
                    "canonical_field": canonical_field,
                    "alias": alias,
                    "normalized_alias": normalized_alias,
                    "start": start,
                    "end": end,
                })

        # At one label position, retain only the most specific wording. Equal
        # aliases across canonical fields are all preserved for later scoring.
        longest: list[dict[str, Any]] = []
        for start in sorted({item["start"] for item in raw}):
            group = [item for item in raw if item["start"] == start]
            maximum = max((len(item["normalized_alias"].split()), len(item["normalized_alias"])) for item in group)
            longest.extend(
                item for item in group
                if (len(item["normalized_alias"].split()), len(item["normalized_alias"])) == maximum
            )
        longest.sort(key=lambda item: (item["start"], item["canonical_field"], item["alias"].value))

        candidates: list[AliasValueCandidate] = []
        distinct_starts = sorted({item["start"] for item in longest})
        for item in longest:
            separator_position, separator = _separator_after(joined, item["end"])
            value_start = separator_position + 1 if separator_position is not None else item["end"]
            next_start = next((start for start in distinct_starts if start > item["start"]), len(joined))
            value = joined[value_start:next_start].strip()
            span_end = max(item["end"], next_start if value else item["end"])
            source_blocks = _source_blocks(offsets, item["start"], span_end)
            candidates.append(AliasValueCandidate(
                candidate_id=f"alias:{item['canonical_field']}:{item['start']}:{item['end']}",
                canonical_field=item["canonical_field"],
                alias=item["alias"].value,
                alias_origin=item["alias"].origin,
                matched_text=joined[item["start"]:item["end"]],
                label_text=joined[item["start"]:item["end"]].strip(),
                value_text=value,
                separator_present=separator is not None,
                separator=separator,
                start=item["start"],
                end=item["end"],
                source_block_indices=source_blocks,
            ))
        return tuple(candidates)


class ConfigurableValueValidator:
    """Validate values with active rules and produce scoring-ready evidence."""

    def __init__(self, registry: FieldRuleRegistry):
        self.registry = registry
        for canonical_field, field in registry.fields.items():
            for index, rule in enumerate(field.value_rules):
                if rule.get("status", "active") == "active":
                    _validate_rule_config(rule, f"{canonical_field}.value_rules[{index}]")

    def validate(self, canonical_field: str, value: str) -> ValueValidationResult:
        field = self.registry.field(canonical_field)
        rules = tuple(rule for rule in field.value_rules if rule.get("status", "active") == "active")
        return self.validate_rules(canonical_field, value, rules)

    @staticmethod
    def validate_rules(
        canonical_field: str,
        value: str,
        rules: Sequence[Mapping[str, Any]],
    ) -> ValueValidationResult:
        if not isinstance(value, str):
            raise ValueError("Value validation input must be a string.")
        evidence: list[RuleValidation] = []
        for index, rule in enumerate(rules):
            _validate_rule_config(rule, f"{canonical_field}.value_rules[{index}]")
            if rule.get("status", "active") != "active":
                continue
            evidence.append(_evaluate_rule(value, rule))
        evaluated = [item for item in evidence if item.status != "not_evaluated"]
        passed = [item for item in evaluated if item.status == "passed"]
        failed_required = [item for item in evidence if item.required and item.status == "failed"]
        hard_constraints = tuple(
            HardConstraint.value_validation_failure(f"value_validation_failed:{item.rule_type}")
            for item in failed_required
        )
        if failed_required:
            status = "failed"
        elif evaluated and len(passed) == len(evaluated):
            status = "passed"
        elif evaluated:
            status = "partial"
        else:
            status = "not_evaluated"
        normalized = next((item.normalized_value for item in evidence if item.normalized_value), value.strip())
        score = round(len(passed) / len(evaluated), 4) if evaluated else 0.0
        return ValueValidationResult(
            canonical_field=canonical_field,
            value=value,
            normalized_value=normalized,
            status=status,
            score=score,
            rules=tuple(evidence),
            hard_constraints=hard_constraints,
        )


def _evaluate_rule(value: str, rule: Mapping[str, Any]) -> RuleValidation:
    rule_type = str(rule["type"])
    required = bool(rule.get("required", False))
    origin = str(rule.get("origin", "user"))
    stripped = value.strip()
    if not stripped:
        return RuleValidation(
            rule_type, required, "failed" if required else "not_evaluated",
            "required_value_missing" if required else "optional_value_missing", "", origin,
        )

    normalized = stripped
    passed = False
    reason = "rule_mismatch"
    if rule_type == "unit_suffix":
        normalized = re.sub(r"\s+", "", stripped)
        values = _configured_values(rule)
        passed = any(normalized.casefold().endswith(item.casefold()) and len(normalized) > len(item) for item in values)
        reason = "unit_suffix_matched" if passed else "unit_suffix_mismatch"
    elif rule_type in {"endswith", "startswith"}:
        normalized = " ".join(stripped.split())
        haystack = normalise_rule_text(normalized)
        values = tuple(normalise_rule_text(item) for item in _configured_values(rule))
        passed = any(haystack.endswith(item) for item in values) if rule_type == "endswith" else any(haystack.startswith(item) for item in values)
        reason = f"{rule_type}_matched" if passed else f"{rule_type}_mismatch"
    elif rule_type == "regex":
        passed = re.fullmatch(str(rule["pattern"]), stripped, flags=re.IGNORECASE) is not None
        reason = "regex_fullmatch" if passed else "regex_mismatch"
    elif rule_type == "enum":
        normalized = normalise_rule_text(stripped)
        passed = normalized in {normalise_rule_text(item) for item in _configured_values(rule)}
        reason = "enum_matched" if passed else "enum_mismatch"
    elif rule_type == "numeric":
        number = _parse_number(stripped)
        passed = number is not None
        normalized = _number_text(number) if number is not None else stripped
        reason = "numeric_matched" if passed else "numeric_mismatch"
    elif rule_type == "numeric_range":
        number = _parse_number(stripped)
        minimum, maximum = _range_bounds(rule)
        passed = number is not None and minimum <= number <= maximum
        normalized = _number_text(number) if number is not None else stripped
        reason = "numeric_range_matched" if passed else "numeric_range_mismatch"
    elif rule_type == "version":
        passed = _VERSION_PATTERN.fullmatch(stripped) is not None
        reason = "version_matched" if passed else "version_mismatch"
    elif rule_type == "ticket_number":
        passed = TICKET_PATTERN.fullmatch(stripped) is not None
        reason = "ticket_number_matched" if passed else "ticket_number_mismatch"
    elif rule_type == "year":
        passed = re.fullmatch(r"(?:19|20)\d{2}", stripped) is not None
        reason = "year_matched" if passed else "year_mismatch"
    elif rule_type == "page_reference":
        match = PAGE_REFERENCE_PATTERN.fullmatch(stripped)
        passed = bool(match and int(match.group(1)) >= 1 and int(match.group(2)) >= int(match.group(1)))
        normalized = re.sub(r"\s+", "", stripped)
        reason = "page_reference_matched" if passed else "page_reference_mismatch"
    return RuleValidation(rule_type, required, "passed" if passed else "failed", reason, normalized, origin)


def _validate_rule_config(rule: Mapping[str, Any], context: str) -> None:
    rule_type = rule.get("type")
    if rule_type not in SUPPORTED_VALUE_RULES:
        raise ValueRuleConfigurationError(f"{context}.type is not supported: {rule_type!r}")
    allowed = set(_RULE_METADATA)
    if rule_type in {"unit_suffix", "endswith", "startswith", "enum"}:
        allowed.update({"value", "values"})
        _configured_values(rule, context)
    elif rule_type == "regex":
        allowed.add("pattern")
        pattern = rule.get("pattern")
        if not isinstance(pattern, str) or not pattern or len(pattern) > 500:
            raise ValueRuleConfigurationError(f"{context}.pattern must be a non-empty string up to 500 characters.")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ValueRuleConfigurationError(f"{context}.pattern is invalid: {exc}") from exc
    elif rule_type == "numeric_range":
        allowed.update({"minimum", "maximum", "min", "max"})
        minimum, maximum = _range_bounds(rule, context)
        if minimum > maximum:
            raise ValueRuleConfigurationError(f"{context} minimum cannot exceed maximum.")
    unknown = set(rule) - allowed
    if unknown:
        raise ValueRuleConfigurationError(f"Unknown keys in {context}: {sorted(unknown)}")
    if "required" in rule and not isinstance(rule["required"], bool):
        raise ValueRuleConfigurationError(f"{context}.required must be boolean.")


def _configured_values(rule: Mapping[str, Any], context: str = "value rule") -> tuple[str, ...]:
    if "values" in rule and "value" in rule:
        raise ValueRuleConfigurationError(f"{context} must use value or values, not both.")
    raw = rule.get("values", [rule.get("value")] if "value" in rule else None)
    if not isinstance(raw, (list, tuple)) or not raw or any(not isinstance(item, str) or not item.strip() for item in raw):
        raise ValueRuleConfigurationError(f"{context}.values must be a non-empty string list.")
    return tuple(item.strip() for item in raw)


def _range_bounds(rule: Mapping[str, Any], context: str = "numeric_range") -> tuple[float, float]:
    if ("minimum" in rule or "maximum" in rule) and ("min" in rule or "max" in rule):
        raise ValueRuleConfigurationError(f"{context} cannot mix minimum/maximum with min/max.")
    minimum = rule.get("minimum", rule.get("min"))
    maximum = rule.get("maximum", rule.get("max"))
    if isinstance(minimum, bool) or isinstance(maximum, bool) or not isinstance(minimum, (int, float)) or not isinstance(maximum, (int, float)):
        raise ValueRuleConfigurationError(f"{context} requires numeric minimum and maximum.")
    if not math.isfinite(float(minimum)) or not math.isfinite(float(maximum)):
        raise ValueRuleConfigurationError(f"{context} range bounds must be finite.")
    return float(minimum), float(maximum)


def _parse_number(value: str) -> float | None:
    compact = value.strip().replace(",", ".")
    if _NUMBER_PATTERN.fullmatch(compact) is None:
        return None
    return float(compact)


def _number_text(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _short_alias_is_safe(text: str, end: int, normalized_alias: str) -> bool:
    if len(normalized_alias.split()) > 1 or len(normalized_alias) > 3:
        return True
    tail = text[end:].lstrip()
    if not tail or tail.startswith((":", "：")):
        return True
    first_token = re.sub(r"[^\w./-]+", "", tail.split()[0], flags=re.UNICODE)
    return any(character.isdigit() for character in first_token) or (
        len(first_token) >= 2 and first_token.isupper()
    )


def _alias_position_is_safe(text: str, start: int, end: int) -> bool:
    """Reject field-name phrases embedded naturally inside a value block."""

    block_start = text.rfind("\n", 0, start) + 1
    prefix = text[block_start:start].strip()
    separator_position, _separator = _separator_after(text, end)
    return not prefix or separator_position is not None


def _normalise_with_positions(text: str) -> tuple[str, list[int]]:
    characters: list[str] = []
    positions: list[int] = []
    for index, original in enumerate(text):
        folded = original.casefold().replace("đ", "d")
        decomposed = unicodedata.normalize("NFD", folded)
        emitted = [
            character for character in decomposed
            if unicodedata.category(character) != "Mn" and character.isascii() and character.isalnum()
        ]
        if emitted:
            for character in emitted:
                characters.append(character)
                positions.append(index)
        elif characters and characters[-1] != " ":
            characters.append(" ")
            positions.append(index)
    while characters and characters[-1] == " ":
        characters.pop()
        positions.pop()
    return "".join(characters), positions


def _separator_after(text: str, end: int) -> tuple[int | None, str | None]:
    position = end
    while position < len(text) and text[position].isspace():
        position += 1
    if position < len(text) and text[position] in (":", "："):
        return position, text[position]
    return None, None


def _join_blocks(blocks: Sequence[str]) -> tuple[str, tuple[tuple[int, int], ...]]:
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for index, block in enumerate(blocks):
        if index:
            parts.append("\n")
            cursor += 1
        start = cursor
        parts.append(block)
        cursor += len(block)
        offsets.append((start, cursor))
    return "".join(parts), tuple(offsets)


def _source_blocks(offsets: Sequence[tuple[int, int]], start: int, end: int) -> tuple[int, ...]:
    return tuple(
        index for index, (block_start, block_end) in enumerate(offsets)
        if block_end > start and block_start < end
    )
