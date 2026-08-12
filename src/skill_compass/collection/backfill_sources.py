"""Validate existing Apify backfill references against configured search scopes.

This collection-layer module reads only the private scope-to-storage CSV. It
must not invoke Apify, duplicate scope metadata, fetch records, or process jobs.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skill_compass.collection.search_scopes import SearchScope

# =============================================================================
# Strict source-reference contracts
# =============================================================================


_RESOURCE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_REQUIRED_COLUMNS = ("scope_id", "run_id", "dataset_id")


class BackfillSourceManifestError(RuntimeError):
    """Report a fatal structural or scope-reference manifest problem."""


class BackfillSourceReference(BaseModel):
    """Connect one configured scope to an existing run or dataset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str = Field(pattern=r"^[a-z0-9_]+$")
    run_id: str | None = None
    dataset_id: str | None = None

    @model_validator(mode="after")
    def validate_existing_identifier(self) -> BackfillSourceReference:
        """Require at least one safe Apify resource ID without preferring a run."""
        if self.run_id is None and self.dataset_id is None:
            raise ValueError("run_id or dataset_id is required")
        for label, value in (("run_id", self.run_id), ("dataset_id", self.dataset_id)):
            if value is not None and not _RESOURCE_ID_PATTERN.fullmatch(value):
                raise ValueError(f"{label} contains unsupported characters")
        return self


@dataclass(frozen=True, slots=True)
class BackfillSourceManifest:
    """Return configured-order references and explicitly missing scopes."""

    path: Path
    references: tuple[BackfillSourceReference, ...]
    missing_scope_ids: tuple[str, ...]
    expected_scope_count: int

    @property
    def is_ready(self) -> bool:
        """Return whether every configured scope has an existing source reference."""
        return not self.missing_scope_ids


# =============================================================================
# Safe CSV loading and authoritative scope validation
# =============================================================================


def _optional_resource_id(value: str | None) -> str | None:
    """Normalize an optional CSV identifier without inventing a value."""
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def load_backfill_source_manifest(
    path: Path, *, configured_scopes: tuple[SearchScope, ...]
) -> BackfillSourceManifest:
    """Validate references and order them by authoritative configured scopes."""
    configured_by_id = {scope.scope_id: scope for scope in configured_scopes}
    references_by_id: dict[str, BackfillSourceReference] = {}
    try:
        with path.open(encoding="utf-8-sig", newline="") as input_file:
            reader = csv.DictReader(input_file)
            if reader.fieldnames is None:
                raise BackfillSourceManifestError("source manifest has no header")
            missing_columns = set(_REQUIRED_COLUMNS).difference(reader.fieldnames)
            if missing_columns:
                missing = ", ".join(sorted(missing_columns))
                raise BackfillSourceManifestError(
                    f"source manifest is missing required columns: {missing}"
                )

            for row_number, row in enumerate(reader, start=2):
                scope_id = (row.get("scope_id") or "").strip()
                if scope_id not in configured_by_id:
                    raise BackfillSourceManifestError(
                        f"row {row_number} has unknown scope_id: {scope_id or '[blank]'}"
                    )
                if scope_id in references_by_id:
                    raise BackfillSourceManifestError(
                        f"row {row_number} duplicates scope_id: {scope_id}"
                    )
                try:
                    reference = BackfillSourceReference(
                        scope_id=scope_id,
                        run_id=_optional_resource_id(row.get("run_id")),
                        dataset_id=_optional_resource_id(row.get("dataset_id")),
                    )
                except ValueError as error:
                    raise BackfillSourceManifestError(
                        f"row {row_number} is invalid for {scope_id}: {error}"
                    ) from error
                references_by_id[scope_id] = reference
    except (OSError, csv.Error) as error:
        raise BackfillSourceManifestError(
            f"source manifest could not be read: {path}"
        ) from error

    ordered_references = tuple(
        references_by_id[scope.scope_id]
        for scope in configured_scopes
        if scope.scope_id in references_by_id
    )
    missing_scope_ids = tuple(
        scope.scope_id
        for scope in configured_scopes
        if scope.scope_id not in references_by_id
    )
    return BackfillSourceManifest(
        path=path,
        references=ordered_references,
        missing_scope_ids=missing_scope_ids,
        expected_scope_count=len(configured_scopes),
    )
