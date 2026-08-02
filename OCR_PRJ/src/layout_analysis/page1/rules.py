"""Versioned, append-only field-rule registry for Page-1 extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping
import unicodedata


DEFAULT_REGISTRY_PATH = Path(__file__).with_name("field_rules.json")
SUPPORTED_SCHEMA_VERSION = "1.0"
RULE_STATUSES = frozenset({"active", "disabled"})
RULE_ORIGINS = frozenset({"built_in", "user"})
SCORING_COMPONENTS = (
    "topology",
    "anchor",
    "alias",
    "separator",
    "value_validation",
    "ocr_confidence",
)
RULE_COLLECTIONS = ("aliases", "topology_rules", "anchor_rules", "value_rules")


class FieldRuleRegistryError(ValueError):
    """Raised when a default registry or user overlay is invalid."""


def normalise_rule_text(value: str) -> str:
    """Normalize human-entered labels for deterministic conflict lookup."""

    decomposed = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    plain = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


@dataclass(frozen=True)
class ScoringConfig:
    auto_select_minimum: float
    winner_margin_minimum: float
    weights: Mapping[str, float]


@dataclass(frozen=True)
class AliasRule:
    value: str
    origin: str
    status: str
    created_by: str | None = None
    created_at: str | None = None

    @property
    def normalized_value(self) -> str:
        return normalise_rule_text(self.value)


@dataclass(frozen=True)
class FieldRule:
    canonical_name: str
    aliases: tuple[AliasRule, ...]
    topology_rules: tuple[Mapping[str, Any], ...]
    anchor_rules: tuple[Mapping[str, Any], ...]
    value_rules: tuple[Mapping[str, Any], ...]

    @property
    def active_aliases(self) -> tuple[AliasRule, ...]:
        return tuple(rule for rule in self.aliases if rule.status == "active")


@dataclass(frozen=True)
class FieldRuleRegistry:
    schema_version: str
    scoring: ScoringConfig
    fields: Mapping[str, FieldRule] = field(default_factory=dict)

    def field(self, canonical_name: str) -> FieldRule:
        try:
            return self.fields[canonical_name]
        except KeyError as exc:
            raise FieldRuleRegistryError(f"Unknown canonical field: {canonical_name}") from exc

    def canonical_fields_for_alias(self, alias: str) -> tuple[str, ...]:
        normalized = normalise_rule_text(alias)
        return tuple(
            name
            for name, rules in self.fields.items()
            if any(rule.normalized_value == normalized for rule in rules.active_aliases)
        )


def _read_json(path: Path, *, kind: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise FieldRuleRegistryError(f"Could not read {kind} JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise FieldRuleRegistryError(f"{kind} root must be a JSON object.")
    return payload


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FieldRuleRegistryError(f"{label} must be a number.")
    converted = float(value)
    if not 0 <= converted <= 100:
        raise FieldRuleRegistryError(f"{label} must be between 0 and 100.")
    return converted


def _scoring(payload: Any, *, partial: bool = False) -> dict[str, Any]:
    if payload is None and partial:
        return {}
    if not isinstance(payload, dict):
        raise FieldRuleRegistryError("scoring must be a JSON object.")
    allowed = {"auto_select_minimum", "winner_margin_minimum", "weights"}
    unknown = set(payload) - allowed
    if unknown:
        raise FieldRuleRegistryError(f"Unknown scoring keys: {sorted(unknown)}")
    result: dict[str, Any] = {}
    for key in ("auto_select_minimum", "winner_margin_minimum"):
        if key in payload:
            result[key] = _number(payload[key], f"scoring.{key}")
        elif not partial:
            raise FieldRuleRegistryError(f"scoring.{key} is required.")
    if "weights" in payload:
        weights = payload["weights"]
        if not isinstance(weights, dict) or set(weights) != set(SCORING_COMPONENTS):
            raise FieldRuleRegistryError(
                f"scoring.weights must contain exactly: {', '.join(SCORING_COMPONENTS)}"
            )
        converted = {name: _number(weights[name], f"scoring.weights.{name}") for name in SCORING_COMPONENTS}
        if abs(sum(converted.values()) - 100.0) > 1e-6:
            raise FieldRuleRegistryError("scoring.weights must sum to 100.")
        result["weights"] = converted
    elif not partial:
        raise FieldRuleRegistryError("scoring.weights is required.")
    return result


def _rule_metadata(rule: dict[str, Any], *, context: str, overlay: bool) -> dict[str, Any]:
    origin = rule.get("origin")
    status = rule.get("status", "active")
    if origin not in RULE_ORIGINS:
        raise FieldRuleRegistryError(f"{context}.origin must be built_in or user.")
    if overlay and origin != "user":
        raise FieldRuleRegistryError(f"{context} from an overlay must have origin=user.")
    if status not in RULE_STATUSES:
        raise FieldRuleRegistryError(f"{context}.status must be active or disabled.")
    created_by = rule.get("created_by")
    if origin == "user" and (not isinstance(created_by, str) or not created_by.strip()):
        raise FieldRuleRegistryError(f"{context}.created_by is required for user rules.")
    return {**rule, "origin": origin, "status": status}


def _validate_alias(rule: Any, *, context: str, overlay: bool) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise FieldRuleRegistryError(f"{context} must be a JSON object.")
    allowed = {"value", "origin", "status", "created_by", "created_at"}
    unknown = set(rule) - allowed
    if unknown:
        raise FieldRuleRegistryError(f"Unknown keys in {context}: {sorted(unknown)}")
    result = _rule_metadata(rule, context=context, overlay=overlay)
    value = result.get("value")
    if not isinstance(value, str) or not normalise_rule_text(value):
        raise FieldRuleRegistryError(f"{context}.value must contain a field label.")
    return result


def _validate_generic_rule(rule: Any, *, context: str, overlay: bool) -> dict[str, Any]:
    if not isinstance(rule, dict):
        raise FieldRuleRegistryError(f"{context} must be a JSON object.")
    result = _rule_metadata(rule, context=context, overlay=overlay)
    rule_type = result.get("type")
    if not isinstance(rule_type, str) or not rule_type.strip():
        raise FieldRuleRegistryError(f"{context}.type is required.")
    required = result.get("required")
    if required is not None and not isinstance(required, bool):
        raise FieldRuleRegistryError(f"{context}.required must be boolean when supplied.")
    return result


def _validate_fields(payload: Any, *, overlay: bool, known_fields: set[str] | None = None) -> dict[str, dict[str, list[dict[str, Any]]]]:
    if not isinstance(payload, dict) or (not payload and not overlay):
        raise FieldRuleRegistryError("fields must be a non-empty JSON object.")
    result: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for field_name, field_payload in payload.items():
        if not isinstance(field_name, str) or not re.fullmatch(r"[a-z][a-z0-9_]*", field_name):
            raise FieldRuleRegistryError(f"Invalid canonical field name: {field_name!r}")
        if known_fields is not None and field_name not in known_fields:
            raise FieldRuleRegistryError(f"Overlay cannot create unknown canonical field: {field_name}")
        if not isinstance(field_payload, dict):
            raise FieldRuleRegistryError(f"fields.{field_name} must be a JSON object.")
        unknown = set(field_payload) - set(RULE_COLLECTIONS)
        if unknown:
            raise FieldRuleRegistryError(f"Unknown keys in fields.{field_name}: {sorted(unknown)}")
        if not overlay and set(field_payload) != set(RULE_COLLECTIONS):
            raise FieldRuleRegistryError(f"fields.{field_name} must declare every rule collection.")
        collections: dict[str, list[dict[str, Any]]] = {}
        for collection in RULE_COLLECTIONS:
            values = field_payload.get(collection, [])
            if not isinstance(values, list):
                raise FieldRuleRegistryError(f"fields.{field_name}.{collection} must be a list.")
            validator = _validate_alias if collection == "aliases" else _validate_generic_rule
            collections[collection] = [
                validator(value, context=f"fields.{field_name}.{collection}[{index}]", overlay=overlay)
                for index, value in enumerate(values)
            ]
        result[field_name] = collections
    return result


def _validate_registry(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict[str, list[dict[str, Any]]]]]:
    allowed = {"schema_version", "scoring", "fields"}
    unknown = set(payload) - allowed
    if unknown:
        raise FieldRuleRegistryError(f"Unknown registry keys: {sorted(unknown)}")
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise FieldRuleRegistryError(f"Unsupported field-rule schema_version: {payload.get('schema_version')!r}")
    return _scoring(payload.get("scoring")), _validate_fields(payload.get("fields"), overlay=False)


def _validate_overlay(payload: dict[str, Any], known_fields: set[str]) -> tuple[dict[str, Any], dict[str, dict[str, list[dict[str, Any]]]]]:
    allowed = {"schema_version", "scoring", "fields"}
    unknown = set(payload) - allowed
    if unknown:
        raise FieldRuleRegistryError(f"Unknown overlay keys: {sorted(unknown)}")
    if payload.get("schema_version") != SUPPORTED_SCHEMA_VERSION:
        raise FieldRuleRegistryError(f"Unsupported overlay schema_version: {payload.get('schema_version')!r}")
    return (
        _scoring(payload.get("scoring"), partial=True),
        _validate_fields(payload.get("fields", {}), overlay=True, known_fields=known_fields),
    )


def _freeze_rule(rule: dict[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(rule))


def load_field_rule_registry(
    default_path: Path | str = DEFAULT_REGISTRY_PATH,
    *,
    overlay_path: Path | str | None = None,
) -> FieldRuleRegistry:
    """Load defaults and append a validated human-maintained overlay.

    Overlay field collections are append-only. They cannot create canonical
    fields, remove defaults, replace collections, or claim built-in origin.
    Scoring thresholds may be overridden explicitly because they are intended
    to be tuned later from ground-truth metrics.
    """

    default_payload = _read_json(Path(default_path), kind="field-rule registry")
    scoring_payload, field_payload = _validate_registry(default_payload)
    if overlay_path is not None:
        overlay_payload = _read_json(Path(overlay_path), kind="field-rule overlay")
        scoring_overlay, field_overlay = _validate_overlay(overlay_payload, set(field_payload))
        scoring_payload = {
            **scoring_payload,
            **{key: value for key, value in scoring_overlay.items() if key != "weights"},
            **({"weights": scoring_overlay["weights"]} if "weights" in scoring_overlay else {}),
        }
        for field_name, collections in field_overlay.items():
            for collection, rules in collections.items():
                field_payload[field_name][collection].extend(rules)

    scoring = ScoringConfig(
        auto_select_minimum=scoring_payload["auto_select_minimum"],
        winner_margin_minimum=scoring_payload["winner_margin_minimum"],
        weights=MappingProxyType(dict(scoring_payload["weights"])),
    )
    fields = {}
    for field_name, collections in field_payload.items():
        fields[field_name] = FieldRule(
            canonical_name=field_name,
            aliases=tuple(AliasRule(**rule) for rule in collections["aliases"]),
            topology_rules=tuple(_freeze_rule(rule) for rule in collections["topology_rules"]),
            anchor_rules=tuple(_freeze_rule(rule) for rule in collections["anchor_rules"]),
            value_rules=tuple(_freeze_rule(rule) for rule in collections["value_rules"]),
        )
    return FieldRuleRegistry(
        schema_version=SUPPORTED_SCHEMA_VERSION,
        scoring=scoring,
        fields=MappingProxyType(fields),
    )
