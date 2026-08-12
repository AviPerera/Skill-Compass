"""Load and validate declarative seniority-classification rules.

This configuration layer uses safe YAML and deterministic hashing; it must not
read job data, evaluate seniority evidence, or execute configured expressions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError, model_validator

from skill_compass.classification.errors import SeniorityConfigurationError
from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.classification import SeniorityRuleSet

# =============================================================================
# Strict governed-taxonomy validation
# =============================================================================


APPROVED_SENIORITY_CODES = (
    "entry_level",
    "junior",
    "mid_level",
    "senior",
)
APPROVED_SENIORITY_LABELS = {
    "entry_level": "Entry-level",
    "junior": "Junior",
    "mid_level": "Mid-level",
    "senior": "Senior",
}
APPROVED_SAFETY_LABELS = {"unknown": "Unknown", "review": "Review"}
ALLOWED_CONTEXT_SECTIONS = frozenset(
    {"summary_text_clean", "bullet_points_clean", "description_text_clean"}
)
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class ValidatedSeniorityRuleSet(SeniorityRuleSet):
    """Add taxonomy, thresholds, sections, and experience-band validation."""

    @model_validator(mode="after")
    def validate_rules(self) -> ValidatedSeniorityRuleSet:
        """Reject unsafe, incomplete, overlapping, or unordered rule documents."""
        if CODE_PATTERN.fullmatch(self.profile_code) is None:
            raise ValueError("profile_code must use lower-case snake_case")
        actual_codes = tuple(level.seniority_code for level in self.levels)
        if actual_codes != APPROVED_SENIORITY_CODES:
            raise ValueError(
                "levels must contain the four approved seniority codes in order"
            )
        if tuple(level.rank_order for level in self.levels) != (1, 2, 3, 4):
            raise ValueError("seniority rank_order must be the sequence 1, 2, 3, 4")
        for level in self.levels:
            if level.seniority_label != APPROVED_SENIORITY_LABELS[level.seniority_code]:
                raise ValueError("seniority labels must match the approved taxonomy")
        graduate_flags = {
            level.seniority_code: level.graduate_level_flag for level in self.levels
        }
        if graduate_flags != {
            "entry_level": True,
            "junior": True,
            "mid_level": False,
            "senior": False,
        }:
            raise ValueError("graduate flags must include Entry-level and Junior only")

        if set(self.section_multipliers) != ALLOWED_CONTEXT_SECTIONS:
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

        bands_by_code = {band.seniority_code: band for band in self.experience_bands}
        if tuple(bands_by_code) != APPROVED_SENIORITY_CODES:
            raise ValueError("experience bands must define each seniority code once")
        previous_maximum = -1
        for code in APPROVED_SENIORITY_CODES:
            band = bands_by_code[code]
            if band.minimum_years != previous_maximum + 1:
                raise ValueError("experience bands must be contiguous and ordered")
            if band.maximum_years is None:
                if code != "senior":
                    raise ValueError(
                        "only the Senior experience band may be open-ended"
                    )
                previous_maximum = 50
            else:
                if band.maximum_years < band.minimum_years:
                    raise ValueError("experience band maximum must not precede minimum")
                previous_maximum = band.maximum_years
        if bands_by_code["senior"].maximum_years is not None:
            raise ValueError("the Senior experience band must be open-ended")

        for level in self.levels:
            groups = (
                level.strong_title_terms,
                level.supporting_title_terms,
                level.context_terms,
                level.employment_type_hints,
                level.conflicting_title_terms,
            )
            if not level.strong_title_terms:
                raise ValueError("every seniority level needs a strong title term")
            for terms in groups:
                normalized = [term.casefold().strip() for term in terms]
                if any(not term for term in normalized):
                    raise ValueError("seniority evidence terms must not be blank")
                if len(normalized) != len(set(normalized)):
                    raise ValueError(
                        "seniority evidence terms must be unique within a group"
                    )
        return self


# =============================================================================
# Safe YAML loading and deterministic hashing
# =============================================================================


def load_seniority_rules(path: Path) -> SeniorityRuleSet:
    """Read, validate, and hash one declarative seniority-rule document."""
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise SeniorityConfigurationError(
            f"seniority rules could not be read: {path}"
        ) from error
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError as error:
        raise SeniorityConfigurationError(
            "seniority rules must contain declarative safe YAML only"
        ) from error
    if not isinstance(document, dict):
        raise SeniorityConfigurationError("seniority rules root must be a mapping")

    values: dict[str, Any] = dict(document)
    values["seniority_rules_hash"] = canonical_sha256(document)
    try:
        return ValidatedSeniorityRuleSet.model_validate(values)
    except ValidationError as error:
        raise SeniorityConfigurationError(
            f"invalid seniority rules: {error}"
        ) from error
