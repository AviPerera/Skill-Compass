"""Load and validate declarative profile-relevance rules.

This configuration layer belongs to classification and must not read job data,
score evidence, infer profile policy, or execute expressions from YAML.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError, model_validator

from skill_compass.classification.errors import RelevanceConfigurationError
from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.classification import RelevanceRuleSet

# =============================================================================
# Strict governed configuration validation
# =============================================================================


CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")
TERM_FIELDS = (
    "strongly_included_title_terms",
    "generally_included_title_terms",
    "adjacent_title_terms",
    "generic_title_terms",
    "strongly_excluded_title_terms",
    "positive_responsibility_terms",
    "negative_responsibility_terms",
    "positive_source_terms",
    "negative_source_terms",
)


class ValidatedRelevanceRuleSet(RelevanceRuleSet):
    """Add cross-field, code, threshold, and vocabulary validation."""

    @model_validator(mode="after")
    def validate_rules(self) -> ValidatedRelevanceRuleSet:
        """Reject ambiguous thresholds, duplicate terms, and invalid codes."""
        if CODE_PATTERN.fullmatch(self.profile_code) is None:
            raise ValueError("profile_code must use lower-case snake_case")
        code_groups = (
            self.approved_role_codes,
            self.positive_requirement_categories,
            self.strong_requirement_codes,
        )
        for codes in code_groups:
            if not codes or any(CODE_PATTERN.fullmatch(code) is None for code in codes):
                raise ValueError("relevance codes must be non-empty snake_case values")
            if len(codes) != len(set(codes)):
                raise ValueError("relevance codes must be unique within each group")

        thresholds = self.thresholds
        if thresholds.exclusion_score >= thresholds.inclusion_score:
            raise ValueError("exclusion_score must be below inclusion_score")
        if thresholds.weak_positive_ceiling >= thresholds.fallback_positive_strength:
            raise ValueError(
                "weak_positive_ceiling must be below fallback_positive_strength"
            )
        if thresholds.conflict_margin >= thresholds.conflict_strength:
            raise ValueError("conflict_margin must be below conflict_strength")
        expected_sections = {
            "summary_text_clean",
            "bullet_points_clean",
            "description_text_clean",
        }
        if set(self.responsibility_section_multipliers) != expected_sections:
            raise ValueError(
                "responsibility_section_multipliers must define every text section"
            )
        if any(
            value <= 0 or value > 1
            for value in self.responsibility_section_multipliers.values()
        ):
            raise ValueError("responsibility section multipliers must be in (0, 1]")

        for field_name in TERM_FIELDS:
            terms = getattr(self, field_name)
            if not terms:
                raise ValueError(f"{field_name} must not be empty")
            normalized = [" ".join(term.casefold().split()) for term in terms]
            if any(not term for term in normalized):
                raise ValueError("relevance evidence terms must not be blank")
            if len(normalized) != len(set(normalized)):
                raise ValueError(f"{field_name} contains duplicate terms")
        return self


# =============================================================================
# Safe YAML loading and deterministic hashing
# =============================================================================


def load_relevance_rules(path: Path) -> RelevanceRuleSet:
    """Read, validate, and hash one declarative relevance-rule document."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RelevanceConfigurationError(
            f"relevance rules could not be read: {path}"
        ) from error
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise RelevanceConfigurationError(
            "relevance rules must contain declarative safe YAML only"
        ) from error
    if not isinstance(document, dict):
        raise RelevanceConfigurationError("relevance rules root must be a mapping")

    values: dict[str, Any] = dict(document)
    values["relevance_rules_hash"] = canonical_sha256(document)
    try:
        return ValidatedRelevanceRuleSet.model_validate(values)
    except ValidationError as error:
        raise RelevanceConfigurationError(
            f"invalid relevance rules: {error}"
        ) from error
