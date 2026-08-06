"""Load and validate versioned source-specific mapping configuration.

This mapping-layer module accepts declarative YAML only and must never execute
expressions, open source CSV data, or apply cleaning transformations.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.mapping.transformers import ALLOWED_TRANSFORMERS
from skill_compass.schemas.jobs import MappedJob

# =============================================================================
# Immutable mapping configuration contracts
# =============================================================================


class ImmutableConfigModel(BaseModel):
    """Provide strict immutable behaviour for mapping configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CsvInputFormat(ImmutableConfigModel):
    """Define the explicit source CSV format accepted by the adapter."""

    encoding: str
    delimiter: str = Field(min_length=1, max_length=1)
    quotechar: str = Field(min_length=1, max_length=1)
    doublequote: bool


class FieldMapping(ImmutableConfigModel):
    """Define ordered source fields and an allowlisted transformer."""

    preferred: tuple[str, ...]
    fallbacks: tuple[str, ...] = ()
    required: bool = False
    transformer: str = "text"
    note: str | None = None

    @model_validator(mode="after")
    def validate_field_mapping(self) -> FieldMapping:
        """Reject empty paths and transformer names outside the allowlist."""
        if not self.preferred:
            raise ValueError("at least one preferred source field is required")
        if any(not field.strip() for field in (*self.preferred, *self.fallbacks)):
            raise ValueError("source field paths must not be empty")
        if self.transformer not in ALLOWED_TRANSFORMERS:
            raise ValueError(f"unknown transformer: {self.transformer}")
        return self


class SourceMappingConfig(ImmutableConfigModel):
    """Represent one validated, hashed source mapping contract."""

    source_code: str
    mapping_name: str
    mapping_version: str
    canonical_schema_version: str
    input_format: CsvInputFormat
    fields: dict[str, FieldMapping]
    excluded_fields: tuple[str, ...] = ()
    excluded_field_patterns: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    mapping_config_hash: str

    @model_validator(mode="after")
    def validate_mapping_contract(self) -> SourceMappingConfig:
        """Validate required canonical mappings and exclusion patterns."""
        required_fields = {"source_job_id", "title_raw", "job_url"}
        missing_fields = required_fields.difference(self.fields)
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ValueError(f"required canonical mappings are missing: {missing}")

        incorrectly_optional = {
            name for name in required_fields if not self.fields[name].required
        }
        if incorrectly_optional:
            optional = ", ".join(sorted(incorrectly_optional))
            raise ValueError(f"required canonical mappings are optional: {optional}")

        allowed_fields = set(MappedJob.model_fields)
        unknown_fields = set(self.fields).difference(allowed_fields)
        if unknown_fields:
            unknown = ", ".join(sorted(unknown_fields))
            raise ValueError(f"unknown canonical mapped fields: {unknown}")

        for pattern in self.excluded_field_patterns:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(
                    f"invalid excluded field pattern: {pattern}"
                ) from error

        return self


# =============================================================================
# Safe YAML loading and deterministic hashing
# =============================================================================


def canonical_config_hash(document: dict[str, Any]) -> str:
    """Hash a canonical JSON serialization of the declarative YAML document."""
    canonical_bytes = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def load_mapping_config(path: Path) -> SourceMappingConfig:
    """Load safe YAML, validate its structure, and attach its stable SHA-256 hash."""
    try:
        yaml_text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise MappingConfigurationError(
            f"mapping configuration could not be read: {path}"
        ) from error

    try:
        document = yaml.safe_load(yaml_text)
    except yaml.YAMLError as error:
        raise MappingConfigurationError(
            "mapping configuration must contain declarative safe YAML only"
        ) from error

    if not isinstance(document, dict):
        raise MappingConfigurationError("mapping configuration root must be a mapping")

    document_with_hash = dict(document)
    document_with_hash["mapping_config_hash"] = canonical_config_hash(document)

    try:
        return SourceMappingConfig.model_validate(document_with_hash)
    except ValidationError as error:
        raise MappingConfigurationError(
            f"invalid mapping configuration: {error}"
        ) from error
