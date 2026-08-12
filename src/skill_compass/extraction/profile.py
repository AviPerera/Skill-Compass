"""Load and validate declarative requirement-extraction profiles.

This configuration layer accepts safe YAML and must not execute expressions,
read job data, perform requirement matching, or render output files.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError, model_validator

from skill_compass.extraction.errors import ExtractionConfigurationError
from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.extraction import ExtractionProfile

# =============================================================================
# Strict profile contract
# =============================================================================


ALLOWED_SECTION_NAMES = frozenset(
    {
        "title_clean",
        "summary_text_clean",
        "bullet_points_clean",
        "description_text_clean",
    }
)
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


class ValidatedExtractionProfile(ExtractionProfile):
    """Add cross-field validation to the immutable profile contract."""

    @model_validator(mode="after")
    def validate_profile(self) -> ValidatedExtractionProfile:
        """Reject invalid codes, sections, thresholds, and inactive profiles."""
        if CODE_PATTERN.fullmatch(self.profile_code) is None:
            raise ValueError("profile_code must use lower-case snake_case")
        if not self.supported_requirement_types:
            raise ValueError("supported_requirement_types must not be empty")
        if any(
            CODE_PATTERN.fullmatch(value) is None
            for value in self.supported_requirement_types
        ):
            raise ValueError("supported requirement types must use snake_case")

        configured_sections = set(self.section_weights)
        unknown_sections = configured_sections.difference(ALLOWED_SECTION_NAMES)
        missing_sections = ALLOWED_SECTION_NAMES.difference(configured_sections)
        if unknown_sections:
            names = ", ".join(sorted(unknown_sections))
            raise ValueError(f"unknown extraction sections: {names}")
        if missing_sections:
            names = ", ".join(sorted(missing_sections))
            raise ValueError(f"missing extraction sections: {names}")
        if any(weight < 0 or weight > 1 for weight in self.section_weights.values()):
            raise ValueError("section weights must be between 0 and 1")

        thresholds = self.confidence_thresholds
        if not (thresholds.high_min > thresholds.medium_min > thresholds.low_min):
            raise ValueError(
                "confidence thresholds must descend from high to medium to low"
            )
        if not self.active:
            raise ValueError("extraction profile must be active")
        return self


# =============================================================================
# Safe YAML loading and deterministic hashing
# =============================================================================


def load_profile_document(path: Path) -> dict[str, Any]:
    """Read one safe YAML mapping or raise a controlled configuration error."""
    try:
        profile_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise ExtractionConfigurationError(
            f"extraction profile could not be read: {path}"
        ) from error
    try:
        document = yaml.safe_load(profile_text)
    except yaml.YAMLError as error:
        raise ExtractionConfigurationError(
            "extraction profile must contain declarative safe YAML only"
        ) from error
    if not isinstance(document, dict):
        raise ExtractionConfigurationError("extraction profile root must be a mapping")
    return document


def load_extraction_profile(path: Path) -> ExtractionProfile:
    """Load, validate, and attach a canonical SHA-256 profile hash."""
    document = load_profile_document(path)
    values = dict(document)
    values["profile_hash"] = canonical_sha256(document)
    try:
        return ValidatedExtractionProfile.model_validate(values)
    except ValidationError as error:
        raise ExtractionConfigurationError(
            f"invalid extraction profile: {error}"
        ) from error
