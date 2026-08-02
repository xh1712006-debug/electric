"""Template-aware production layout analysis for relay-form page 1."""

from .extractor import extract_page1
from .field_resolution import Page1FieldResolutionEngine
from .rules import FieldRuleRegistry, FieldRuleRegistryError, load_field_rule_registry
from .relationships import (
    RelationshipPolicy,
    SpatialCandidate,
    SpatialRelation,
    SpatialResolution,
    TopologyAnchorResolver,
)
from .scoring import (
    CandidateScoringEngine,
    ConfidenceLevel,
    FieldCandidate,
    HardConstraint,
    ScoringDecision,
    confidence_level_for_score,
)
from .service import Page1LayoutAnalysisService, Page1LayoutResult
from .value_resolution import (
    AliasSeparatorResolver,
    AliasValueCandidate,
    ConfigurableValueValidator,
    SeparatorSplit,
    ValueRuleConfigurationError,
    ValueValidationResult,
    split_label_value,
)

__all__ = [
    "extract_page1",
    "Page1FieldResolutionEngine",
    "FieldRuleRegistry",
    "FieldRuleRegistryError",
    "load_field_rule_registry",
    "RelationshipPolicy",
    "SpatialCandidate",
    "SpatialRelation",
    "SpatialResolution",
    "TopologyAnchorResolver",
    "CandidateScoringEngine",
    "ConfidenceLevel",
    "FieldCandidate",
    "HardConstraint",
    "ScoringDecision",
    "confidence_level_for_score",
    "Page1LayoutAnalysisService",
    "Page1LayoutResult",
    "AliasSeparatorResolver",
    "AliasValueCandidate",
    "ConfigurableValueValidator",
    "SeparatorSplit",
    "ValueRuleConfigurationError",
    "ValueValidationResult",
    "split_label_value",
]
