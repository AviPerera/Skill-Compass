"""Define typed application contracts for external collection results.

These collection-layer models describe run evidence and cap assessment. They
must not introduce database objects or source-specific payload fields.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# =============================================================================
# Collection and completeness contracts
# =============================================================================


class CapStatus(StrEnum):
    """Describe how confidently a collection scope appears complete."""

    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    CAP_RISK = "CAP_RISK"
    CONFIRMED_TRUNCATED = "CONFIRMED_TRUNCATED"
    UNKNOWN = "UNKNOWN"


class CompletenessEvidence(BaseModel):
    """Normalize only verified source evidence about result completeness."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    total_available_count: int | None = Field(default=None, ge=0)
    explicitly_truncated: bool | None = None
    evidence_source: str | None = None


class CapAssessment(BaseModel):
    """Return a status and concise evidence-based explanation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CapStatus
    reason: str


class CollectionResult(BaseModel):
    """Describe one source-scope collection without persisting it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scope_id: str
    run_id: str
    dataset_id: str
    returned_item_count: int = Field(ge=0)
    unique_job_id_count: int | None = Field(default=None, ge=0)
    duplicate_job_id_count: int | None = Field(default=None, ge=0)
    cap_warning_threshold: int = Field(gt=0)
    cap_status: CapStatus
    cap_reason: str
    started_at: datetime
    finished_at: datetime | None
    status: str

    @model_validator(mode="after")
    def validate_result(self) -> CollectionResult:
        """Require aware timestamps and internally consistent identity counts."""
        if self.started_at.tzinfo is None:
            raise ValueError("started_at must be timezone-aware")
        if self.finished_at is not None and self.finished_at.tzinfo is None:
            raise ValueError("finished_at must be timezone-aware")
        if (self.unique_job_id_count is None) != (self.duplicate_job_id_count is None):
            raise ValueError("job identity counts must be present or absent together")
        if self.unique_job_id_count is not None:
            identified_count = (
                self.unique_job_id_count + self.duplicate_job_id_count  # type: ignore[operator]
            )
            if identified_count != self.returned_item_count:
                raise ValueError("job identity counts must reconcile to returned items")
        return self


class FetchManifest(BaseModel):
    """Record one existing-dataset fetch and its local raw output evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fetched_at: datetime
    run_id: str | None = None
    dataset_id: str
    returned_item_count: int = Field(ge=0)
    unique_source_job_id_count: int | None = Field(default=None, ge=0)
    duplicate_source_job_id_count: int | None = Field(default=None, ge=0)
    cap_warning_threshold: int = Field(gt=0)
    cap_status: CapStatus
    cap_reason: str
    source_actor_id: str | None = None
    raw_output_path: Path
    status: str
    actor_invocation: Literal[False] = False

    @model_validator(mode="after")
    def validate_manifest(self) -> FetchManifest:
        """Require UTC-aware time and internally consistent identity counts."""
        if self.fetched_at.tzinfo is None:
            raise ValueError("fetched_at must be timezone-aware")
        if (self.unique_source_job_id_count is None) != (
            self.duplicate_source_job_id_count is None
        ):
            raise ValueError("source job ID counts must be present or absent together")
        unique_count = self.unique_source_job_id_count
        duplicate_count = self.duplicate_source_job_id_count
        if unique_count is not None and duplicate_count is not None:
            identified_count = unique_count + duplicate_count
            if identified_count != self.returned_item_count:
                raise ValueError(
                    "source job ID counts must reconcile to returned items"
                )
        return self
