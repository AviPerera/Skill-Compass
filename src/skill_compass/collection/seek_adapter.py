"""Load SEEK Actor configuration and interpret SEEK source identities.

This source-adapter module may know Apify SEEK input and payload paths. It must
not map canonical jobs, clean descriptions, classify roles, or run analytics.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# =============================================================================
# Validated source-specific configuration
# =============================================================================

MAX_CONNECTION_TEST_ITEMS = 5


class SeekCollectionConfigurationError(RuntimeError):
    """Report invalid or unreadable SEEK Actor configuration."""


class ConnectionTestConfig(BaseModel):
    """Define the deliberately bounded live connection test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str
    max_items: int = Field(gt=0, le=MAX_CONNECTION_TEST_ITEMS)
    actor_input: dict[str, Any]

    @model_validator(mode="after")
    def validate_actor_limit(self) -> ConnectionTestConfig:
        """Require the Actor-level input limit to match the safety limit."""
        if self.actor_input.get("maxItems") != self.max_items:
            raise ValueError("actor_input.maxItems must match max_items")
        return self


class SeekCollectionConfig(BaseModel):
    """Represent the approved SEEK Actor and source-specific settings."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_code: str
    actor_id: str
    cap_warning_threshold: int = Field(gt=0)
    connection_test: ConnectionTestConfig
    source_job_id_paths: tuple[str, ...]
    classifications: dict[str, str]

    @model_validator(mode="after")
    def validate_source_contract(self) -> SeekCollectionConfig:
        """Reject missing identities, duplicate codes, and unknown test codes."""
        if not self.actor_id.strip():
            raise ValueError("actor_id must not be empty")
        if not self.source_job_id_paths:
            raise ValueError("at least one source job ID path is required")
        classification_codes = tuple(self.classifications.values())
        if len(set(classification_codes)) != len(classification_codes):
            raise ValueError("classification IDs must be unique")
        test_code = str(self.connection_test.actor_input.get("classification", ""))
        if test_code not in classification_codes:
            raise ValueError("connection test classification is not configured")
        return self


def load_seek_collection_config(path: Path) -> SeekCollectionConfig:
    """Load one safe YAML source contract without executing expressions."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SeekCollectionConfigurationError(
            f"SEEK collection configuration could not be read: {path}"
        ) from error
    if not isinstance(document, dict):
        raise SeekCollectionConfigurationError(
            "SEEK collection configuration root must be a mapping"
        )
    try:
        return SeekCollectionConfig.model_validate(document)
    except ValidationError as error:
        raise SeekCollectionConfigurationError(
            f"invalid SEEK collection configuration: {error}"
        ) from error


# =============================================================================
# Source identity evidence
# =============================================================================


def _nested_value(item: Mapping[str, Any], path: str) -> Any:
    """Read one slash-separated path from a nested source item."""
    value: Any = item
    for part in path.split("/"):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def count_source_job_ids(
    items: tuple[dict[str, Any], ...], paths: tuple[str, ...]
) -> tuple[int | None, int | None]:
    """Count unique and duplicate IDs only when every item has a stable ID."""
    identities: list[str] = []
    for item in items:
        identity = next(
            (
                str(value).strip()
                for path in paths
                if (value := _nested_value(item, path)) is not None
                and str(value).strip()
            ),
            None,
        )
        if identity is None:
            return None, None
        identities.append(identity)

    unique_count = len(set(identities))
    return unique_count, len(identities) - unique_count
