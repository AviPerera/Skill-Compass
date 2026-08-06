"""Deduplicate structurally valid mapped jobs within one source file.

This mapping-layer module owns first-row survivor policy and must not perform
cross-run change detection, clean jobs, or read and write files.
"""

from __future__ import annotations

from dataclasses import dataclass

from skill_compass.cleaning.hashing import calculate_content_hash
from skill_compass.schemas.jobs import MappedJob, RejectedRecord, RejectionReasonCode

# =============================================================================
# Deterministic duplicate comparison
# =============================================================================


OBSERVATION_AND_PROVENANCE_FIELDS = frozenset(
    {
        "source_row_number",
        "mapping_version",
        "mapping_config_hash",
        "canonical_schema_version",
        "scraped_at_raw",
        "is_expired_raw",
        "is_featured_raw",
        "mapping_status",
        "fallback_fields_used",
        "mapping_quality_flags",
    }
)


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """Return survivors, duplicate rejections, and separate duplicate counts."""

    survivors: tuple[MappedJob, ...]
    rejections: tuple[RejectedRecord, ...]
    duplicate_same_content_rows: int
    duplicate_conflicting_content_rows: int
    duplicate_identity_count: int


def mapped_content_fingerprint(mapped_job: MappedJob) -> str:
    """Hash process-relevant mapped values while excluding observation metadata."""
    values = mapped_job.model_dump(mode="python")
    process_relevant = {
        key: value
        for key, value in values.items()
        if key not in OBSERVATION_AND_PROVENANCE_FIELDS
    }
    return calculate_content_hash(process_relevant)


def duplicate_rejection(
    duplicate: MappedJob,
    reason_code: RejectionReasonCode,
    first_row_number: int,
) -> RejectedRecord:
    """Build a safe diagnostic for a later within-file duplicate occurrence."""
    detail = (
        f"Later duplicate of the first valid occurrence at source row "
        f"{first_row_number}; the first occurrence was retained."
    )
    return RejectedRecord(
        source_row_number=duplicate.source_row_number,
        source_code=duplicate.source_code,
        source_job_id=duplicate.source_job_id,
        title_raw=duplicate.title_raw[:200],
        rejection_stage="deduplication",
        rejection_reason_code=reason_code,
        rejection_reason_detail=detail,
        mapping_version=duplicate.mapping_version,
        canonical_schema_version=duplicate.canonical_schema_version,
    )


def deduplicate_mapped_jobs(mapped_jobs: tuple[MappedJob, ...]) -> DeduplicationResult:
    """Retain the first valid source row and reject later duplicate identities."""
    survivors: list[MappedJob] = []
    rejections: list[RejectedRecord] = []
    first_by_identity: dict[tuple[str, str], tuple[MappedJob, str]] = {}
    duplicate_identities: set[tuple[str, str]] = set()
    same_content_count = 0
    conflicting_content_count = 0

    for mapped_job in sorted(mapped_jobs, key=lambda job: job.source_row_number):
        identity = (mapped_job.source_code, mapped_job.source_job_id)
        fingerprint = mapped_content_fingerprint(mapped_job)
        first = first_by_identity.get(identity)
        if first is None:
            first_by_identity[identity] = (mapped_job, fingerprint)
            survivors.append(mapped_job)
            continue

        duplicate_identities.add(identity)
        first_job, first_fingerprint = first
        if fingerprint == first_fingerprint:
            reason_code: RejectionReasonCode = "duplicate_same_content"
            same_content_count += 1
        else:
            reason_code = "duplicate_conflicting_content"
            conflicting_content_count += 1
        rejections.append(
            duplicate_rejection(mapped_job, reason_code, first_job.source_row_number)
        )

    return DeduplicationResult(
        survivors=tuple(survivors),
        rejections=tuple(rejections),
        duplicate_same_content_rows=same_content_count,
        duplicate_conflicting_content_rows=conflicting_content_count,
        duplicate_identity_count=len(duplicate_identities),
    )
