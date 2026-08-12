"""Load and expand the configured national SEEK collection search scopes.

This collection-layer module validates profile search configuration and builds
source inputs. It must not invoke Apify, persist raw records, or process jobs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

# =============================================================================
# Typed search-scope configuration
# =============================================================================


DEFAULT_SEARCH_SCOPES_PATH = Path("profiles/data_analytics/search_scopes.yaml")


class SearchScopeConfigurationError(RuntimeError):
    """Report invalid or unreadable national search-scope configuration."""


class StrictFrozenModel(BaseModel):
    """Provide strict immutable behavior for collection configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ClassificationDefinition(StrictFrozenModel):
    """Bind one approved SEEK classification name to its stable source ID."""

    classification_id: str = Field(pattern=r"^\d+$")
    classification_name: str = Field(min_length=1)


class SearchScopeConfig(StrictFrozenModel):
    """Describe one versioned national full-history partition strategy."""

    profile_code: str = Field(min_length=1)
    collection_strategy_version: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    country: str = Field(min_length=1)
    country_name: str = Field(min_length=1)
    cap_warning_threshold: int = Field(gt=0)
    fetch_descriptions: bool
    full_scope_max_items: int = Field(ge=0)
    locations: dict[str, str]
    simple_state_scopes: tuple[str, ...]
    partitioned_states: tuple[str, ...]
    classifications: tuple[ClassificationDefinition, ...]

    @model_validator(mode="after")
    def validate_partition_strategy(self) -> SearchScopeConfig:
        """Reject ambiguous, incomplete, or duplicate configured partitions."""
        state_codes = set(self.locations)
        simple_codes = set(self.simple_state_scopes)
        partitioned_codes = set(self.partitioned_states)
        referenced_codes = simple_codes | partitioned_codes
        if simple_codes & partitioned_codes:
            raise ValueError("simple and partitioned state scopes must not overlap")
        if referenced_codes != state_codes:
            raise ValueError(
                "every configured location must belong to one scope strategy"
            )
        if len(simple_codes) != len(self.simple_state_scopes):
            raise ValueError("simple state codes must be unique")
        if len(partitioned_codes) != len(self.partitioned_states):
            raise ValueError("partitioned state codes must be unique")
        if any(not location.strip() for location in self.locations.values()):
            raise ValueError("source location values must not be empty")

        classification_ids = [item.classification_id for item in self.classifications]
        classification_names = [
            item.classification_name for item in self.classifications
        ]
        if len(set(classification_ids)) != len(classification_ids):
            raise ValueError("classification IDs must be unique")
        if len(set(classification_names)) != len(classification_names):
            raise ValueError("classification names must be unique")
        if not self.classifications:
            raise ValueError("at least one classification is required")
        return self

    @property
    def expected_scope_count(self) -> int:
        """Derive the run count from simple and partitioned configuration."""
        return len(self.simple_state_scopes) + (
            len(self.classifications) * len(self.partitioned_states)
        )


class SearchScope(StrictFrozenModel):
    """Represent one deterministic state or state/classification Actor scope."""

    scope_id: str = Field(pattern=r"^[a-z0-9_]+$")
    state_code: str
    location: str
    classification_id: str | None = None
    classification_name: str | None = None

    @model_validator(mode="after")
    def validate_classification_pair(self) -> SearchScope:
        """Require classification ID and name together or neither."""
        if (self.classification_id is None) != (self.classification_name is None):
            raise ValueError("classification ID and name must be present together")
        return self


# =============================================================================
# Safe loading and deterministic expansion
# =============================================================================


def load_search_scope_config(path: Path) -> SearchScopeConfig:
    """Load declarative YAML into the strict national scope contract."""
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise SearchScopeConfigurationError(
            f"search-scope configuration could not be read: {path}"
        ) from error
    if not isinstance(document, dict):
        raise SearchScopeConfigurationError(
            "search-scope configuration root must be a mapping"
        )
    try:
        return SearchScopeConfig.model_validate(document)
    except ValidationError as error:
        raise SearchScopeConfigurationError(
            f"invalid search-scope configuration: {error}"
        ) from error


def _scope_slug(value: str) -> str:
    """Convert a stable configured name to a filename-safe snake-case slug."""
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if not slug:
        raise SearchScopeConfigurationError("scope name cannot produce an empty ID")
    return slug


def build_search_scopes(config: SearchScopeConfig) -> tuple[SearchScope, ...]:
    """Expand states and classifications in deterministic configured order."""
    scopes: list[SearchScope] = []
    for state_code in config.simple_state_scopes:
        scopes.append(
            SearchScope(
                scope_id=f"{state_code.casefold()}_state",
                state_code=state_code,
                location=config.locations[state_code],
            )
        )

    for state_code in config.partitioned_states:
        for classification in config.classifications:
            scopes.append(
                SearchScope(
                    scope_id=(
                        f"{state_code.casefold()}_"
                        f"{_scope_slug(classification.classification_name)}"
                    ),
                    state_code=state_code,
                    location=config.locations[state_code],
                    classification_id=classification.classification_id,
                    classification_name=classification.classification_name,
                )
            )

    scope_ids = [scope.scope_id for scope in scopes]
    if len(set(scope_ids)) != len(scope_ids):
        raise SearchScopeConfigurationError("generated scope IDs must be unique")
    if len(scopes) != config.expected_scope_count:
        raise SearchScopeConfigurationError(
            "generated scope count does not match the derived configuration formula"
        )
    return tuple(scopes)


# =============================================================================
# Verified SEEK Actor input construction
# =============================================================================


def build_full_scope_actor_input(
    *, config: SearchScopeConfig, scope: SearchScope
) -> dict[str, Any]:
    """Build only Actor fields established by the Feature 4A integration."""
    actor_input: dict[str, Any] = {
        "alertOnNewJob": False,
        "country": config.country,
        "diagnose": False,
        "fetchDescriptions": config.fetch_descriptions,
        "keywords": config.keyword,
        "location": scope.location,
        "maxItems": config.full_scope_max_items,
        "monitorMode": False,
    }
    if scope.classification_id is not None:
        actor_input["classification"] = scope.classification_id
    return actor_input
