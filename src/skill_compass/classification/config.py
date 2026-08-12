"""Load and validate declarative role-classification rules.

This configuration layer uses safe YAML and deterministic hashing; it must not
read job data, evaluate role evidence, or execute expressions from config.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError, model_validator

from skill_compass.classification.errors import RoleConfigurationError
from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.classification import RoleRuleSet

# =============================================================================
# Strict rule-set validation
# =============================================================================


APPROVED_ROLE_CODES = (
    "data_analyst",
    "business_analyst",
    "bi_analyst",
    "reporting_analyst",
    "data_scientist",
)
APPROVED_OUTCOME_LABELS = {"other": "Other", "review": "Review"}
ALLOWED_CONTEXT_SECTIONS = frozenset(
    {"summary_text_clean", "bullet_points_clean", "description_text_clean"}
)
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class ValidatedRoleRuleSet(RoleRuleSet):
    """Add governed taxonomy and cross-field checks to the typed rule set."""

    @model_validator(mode="after")
    def validate_rules(self) -> ValidatedRoleRuleSet:
        """Reject invalid taxonomy, thresholds, sections, and term lists."""
        if CODE_PATTERN.fullmatch(self.profile_code) is None:
            raise ValueError("profile_code must use lower-case snake_case")
        actual_codes = tuple(role.role_group_code for role in self.roles)
        if actual_codes != APPROVED_ROLE_CODES:
            raise ValueError(
                "roles must contain the five approved codes in governed order"
            )
        if len({role.sort_order for role in self.roles}) != len(self.roles):
            raise ValueError("role sort_order values must be unique")

        configured_sections = set(self.section_multipliers)
        if configured_sections != ALLOWED_CONTEXT_SECTIONS:
            raise ValueError("section_multipliers must define every context section")
        if any(value <= 0 or value > 1 for value in self.section_multipliers.values()):
            raise ValueError("section multipliers must be greater than 0 and at most 1")

        thresholds = self.thresholds
        if (
            thresholds.meaningful_evidence_score
            >= thresholds.minimum_classification_score
        ):
            raise ValueError("meaningful evidence must be below classification minimum")
        if not (
            thresholds.high_confidence_min
            > thresholds.medium_confidence_min
            >= thresholds.minimum_classification_score
        ):
            raise ValueError("confidence thresholds must descend to the minimum score")

        for role in self.roles:
            if CODE_PATTERN.fullmatch(role.role_group_code) is None:
                raise ValueError("role codes must use lower-case snake_case")
            if not role.strong_title_terms or not role.context_terms:
                raise ValueError("every role needs strong title and context terms")
            groups = (
                role.strong_title_terms,
                role.supporting_title_terms,
                role.context_terms,
                role.source_hint_terms,
                role.conflicting_title_terms,
                role.exclusion_title_terms,
            )
            for terms in groups:
                normalized = [term.casefold().strip() for term in terms]
                if any(not term for term in normalized):
                    raise ValueError("role evidence terms must not be blank")
                if len(normalized) != len(set(normalized)):
                    raise ValueError(
                        "role evidence terms must be unique within a group"
                    )
        return self


# =============================================================================
# Safe YAML loading and deterministic hashing
# =============================================================================


def load_role_rules(path: Path) -> RoleRuleSet:
    """Read, validate, and hash one declarative role-rule document."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise RoleConfigurationError(f"role rules could not be read: {path}") from error
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise RoleConfigurationError(
            "role rules must contain declarative safe YAML only"
        ) from error
    if not isinstance(document, dict):
        raise RoleConfigurationError("role rules root must be a mapping")

    values: dict[str, Any] = dict(document)
    values["role_rules_hash"] = canonical_sha256(document)
    try:
        return ValidatedRoleRuleSet.model_validate(values)
    except ValidationError as error:
        raise RoleConfigurationError(f"invalid role rules: {error}") from error
