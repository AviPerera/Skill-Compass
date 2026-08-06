"""Map one source-specific row into a typed canonical application record.

This mapping-layer service owns precedence and structural validation but must
not open CSV files, clean canonical values, deduplicate jobs, or write outputs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlparse

from pydantic import ValidationError

from skill_compass.mapping.config import FieldMapping, SourceMappingConfig
from skill_compass.mapping.transformers import (
    COLLECTION_TRANSFORMER,
    apply_scalar_transformer,
    collect_text,
)
from skill_compass.schemas.jobs import MappedJob, RejectedRecord, RejectionReasonCode

# =============================================================================
# Mapping result contract
# =============================================================================


@dataclass(frozen=True, slots=True)
class MappingOutcome:
    """Return either one mapped job or one safe rejected-record diagnostic."""

    mapped_job: MappedJob | None
    rejected_record: RejectedRecord | None
    preferred_fields_used: tuple[str, ...] = ()


# =============================================================================
# Source value resolution
# =============================================================================


def source_value(row: Mapping[str, str], field_name: str) -> str:
    """Return a source value as text while treating null-like entries as empty."""
    value = row.get(field_name, "")
    return value if isinstance(value, str) else ""


def resolve_field(
    row: Mapping[str, str],
    canonical_name: str,
    field_mapping: FieldMapping,
) -> tuple[object, tuple[str, ...], tuple[str, ...]]:
    """Resolve preferred fields before ordered fallbacks and transform the value."""
    preferred_values = tuple(
        source_value(row, field_name) for field_name in field_mapping.preferred
    )
    fallback_values = tuple(
        source_value(row, field_name) for field_name in field_mapping.fallbacks
    )

    if field_mapping.transformer == COLLECTION_TRANSFORMER:
        preferred_collection = collect_text(preferred_values)
        if preferred_collection:
            used = tuple(
                field_name
                for field_name, value in zip(
                    field_mapping.preferred, preferred_values, strict=True
                )
                if value.strip()
            )
            return preferred_collection, (canonical_name,), used

        fallback_collection = collect_text(fallback_values)
        used = tuple(
            field_name
            for field_name, value in zip(
                field_mapping.fallbacks, fallback_values, strict=True
            )
            if value.strip()
        )
        fallback_usage = tuple(f"{canonical_name}:{field}" for field in used)
        return fallback_collection, (), fallback_usage

    for field_name, value in zip(
        field_mapping.preferred, preferred_values, strict=True
    ):
        if value.strip():
            transformed = apply_scalar_transformer(field_mapping.transformer, value)
            return transformed, (canonical_name,), ()

    for field_name, value in zip(field_mapping.fallbacks, fallback_values, strict=True):
        if value.strip():
            transformed = apply_scalar_transformer(field_mapping.transformer, value)
            return transformed, (), (f"{canonical_name}:{field_name}",)

    return None if field_mapping.transformer != COLLECTION_TRANSFORMER else (), (), ()


# =============================================================================
# Structural validation and rejection safety
# =============================================================================


REDACTED_TEXT_FIELDS = frozenset(
    {
        "summary_text_raw",
        "description_html_raw",
        "description_text_raw",
    }
)
REDACTED_COLLECTION_FIELDS = frozenset({"bullet_points_raw"})
EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.IGNORECASE,
)


def sensitive_row_values(
    row: Mapping[str, str], config: SourceMappingConfig
) -> tuple[str, ...]:
    """Collect non-trivial excluded values for exact in-row text redaction."""
    compiled_patterns = tuple(
        re.compile(pattern) for pattern in config.excluded_field_patterns
    )
    values: set[str] = set()
    for field_name, raw_value in row.items():
        is_excluded = field_name in config.excluded_fields or any(
            pattern.search(field_name) for pattern in compiled_patterns
        )
        normalized = raw_value.strip() if isinstance(raw_value, str) else ""
        if (
            is_excluded
            and not field_name.casefold().endswith("/type")
            and len(normalized) >= 6
        ):
            values.add(normalized)
    return tuple(sorted(values, key=lambda value: (-len(value), value.casefold())))


def redact_sensitive_text(value: str, sensitive_values: tuple[str, ...]) -> str:
    """Redact exact excluded values and email addresses from mapped free text."""
    redacted = value
    for sensitive_value in sensitive_values:
        redacted = re.sub(
            re.escape(sensitive_value), "[redacted]", redacted, flags=re.IGNORECASE
        )
    return EMAIL_PATTERN.sub("[redacted-email]", redacted)


def redact_mapped_text(
    mapped_values: dict[str, object],
    row: Mapping[str, str],
    config: SourceMappingConfig,
) -> None:
    """Remove excluded row values from canonical free-text fields in place."""
    sensitive_values = sensitive_row_values(row, config)
    for field_name in REDACTED_TEXT_FIELDS:
        value = mapped_values.get(field_name)
        if isinstance(value, str):
            mapped_values[field_name] = redact_sensitive_text(value, sensitive_values)
    for field_name in REDACTED_COLLECTION_FIELDS:
        value = mapped_values.get(field_name)
        if isinstance(value, tuple):
            mapped_values[field_name] = tuple(
                redact_sensitive_text(item, sensitive_values)
                for item in value
                if isinstance(item, str)
            )


def safe_diagnostic(value: object, limit: int = 200) -> str | None:
    """Return a short single-line value suitable for rejected-record diagnostics."""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized[:limit] or None


def valid_source_job_id(value: str) -> bool:
    """Accept a bounded external text identifier without control characters."""
    return len(value) <= 200 and re.search(r"[\x00-\x1f\x7f]", value) is None


def valid_job_url(value: str) -> bool:
    """Require an absolute HTTP(S) URL for the canonical job URL."""
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def rejection(
    *,
    row_number: int,
    config: SourceMappingConfig,
    mapped_values: Mapping[str, object],
    reason_code: RejectionReasonCode,
    reason_detail: str,
) -> MappingOutcome:
    """Build one privacy-safe mapping rejection outcome."""
    rejected = RejectedRecord(
        source_row_number=row_number,
        source_code=config.source_code,
        source_job_id=safe_diagnostic(mapped_values.get("source_job_id")),
        title_raw=safe_diagnostic(mapped_values.get("title_raw")),
        rejection_stage="mapping",
        rejection_reason_code=reason_code,
        rejection_reason_detail=reason_detail,
        mapping_version=config.mapping_version,
        canonical_schema_version=config.canonical_schema_version,
    )
    return MappingOutcome(mapped_job=None, rejected_record=rejected)


# =============================================================================
# Public mapping service
# =============================================================================


def map_source_row(
    row: Mapping[str, str],
    config: SourceMappingConfig,
    source_row_number: int,
) -> MappingOutcome:
    """Map one row deterministically or return one controlled structural rejection."""
    mapped_values: dict[str, object] = {}
    preferred_fields_used: list[str] = []
    fallback_fields_used: list[str] = []

    for canonical_name, field_mapping in config.fields.items():
        value, preferred_usage, fallback_usage = resolve_field(
            row, canonical_name, field_mapping
        )
        mapped_values[canonical_name] = value
        preferred_fields_used.extend(preferred_usage)
        fallback_fields_used.extend(fallback_usage)

    # Redaction happens while source-specific excluded fields remain available.
    redact_mapped_text(mapped_values, row, config)

    source_job_id = mapped_values.get("source_job_id")
    title_raw = mapped_values.get("title_raw")
    job_url = mapped_values.get("job_url")

    if not isinstance(source_job_id, str) or not source_job_id:
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="missing_source_job_id",
            reason_detail="No usable source job identifier was mapped.",
        )
    if not valid_source_job_id(source_job_id):
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="invalid_source_job_id",
            reason_detail="The mapped source job identifier is invalid.",
        )
    if not isinstance(title_raw, str) or not title_raw:
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="missing_title",
            reason_detail="No usable title was mapped.",
        )
    if not isinstance(job_url, str) or not job_url:
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="missing_job_url",
            reason_detail="No usable job URL was mapped.",
        )
    if not valid_job_url(job_url):
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="invalid_job_url",
            reason_detail="The mapped job URL must be an absolute HTTP(S) URL.",
        )

    quality_flags: list[str] = []
    if not mapped_values.get("company_name_raw"):
        quality_flags.append("missing_company")

    usable_description = any(
        (
            mapped_values.get("description_text_raw"),
            mapped_values.get("description_html_raw"),
            mapped_values.get("summary_text_raw"),
            mapped_values.get("bullet_points_raw"),
        )
    )
    if not usable_description:
        quality_flags.append("missing_usable_description")

    complete_values = {
        **mapped_values,
        "source_code": config.source_code,
        "source_row_number": source_row_number,
        "mapping_version": config.mapping_version,
        "mapping_config_hash": config.mapping_config_hash,
        "canonical_schema_version": config.canonical_schema_version,
        "fallback_fields_used": tuple(fallback_fields_used),
        "mapping_quality_flags": tuple(quality_flags),
        "usable_description_status": "usable" if usable_description else "missing",
        "analytically_eligible": usable_description,
    }

    try:
        mapped_job = MappedJob.model_validate(complete_values)
    except ValidationError:
        return rejection(
            row_number=source_row_number,
            config=config,
            mapped_values=mapped_values,
            reason_code="mapped_record_validation_error",
            reason_detail="The canonical mapped record failed contract validation.",
        )

    return MappingOutcome(
        mapped_job=mapped_job,
        rejected_record=None,
        preferred_fields_used=tuple(preferred_fields_used),
    )
