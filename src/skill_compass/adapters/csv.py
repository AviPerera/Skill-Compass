"""Read source CSV rows using explicit, deterministic format settings.

This outer adapter owns file parsing and row numbering only; it must not apply
source-field precedence, canonical cleaning, deduplication, or quality rules.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from skill_compass.mapping.config import CsvInputFormat
from skill_compass.schemas.jobs import CleanedJob, MappedJob, RejectedRecord
from skill_compass.schemas.quality import QualityMetric

# =============================================================================
# Typed CSV reader results
# =============================================================================


@dataclass(frozen=True, slots=True)
class CsvSourceRow:
    """Represent one logical data row and its deterministic one-based position."""

    source_row_number: int
    values: dict[str, str]


@dataclass(frozen=True, slots=True)
class CsvReadResult:
    """Represent parsed source rows plus safe structural metadata."""

    encoding: str
    delimiter: str
    quotechar: str
    headers: tuple[str, ...]
    rows: tuple[CsvSourceRow, ...]


# =============================================================================
# Explicit CSV input adapter
# =============================================================================


def read_source_csv(path: Path, input_format: CsvInputFormat) -> CsvReadResult:
    """Read a CSV file without dialect sniffing or source-specific transformations."""
    rows: list[CsvSourceRow] = []

    with path.open("r", encoding=input_format.encoding, newline="") as input_file:
        reader = csv.DictReader(
            input_file,
            delimiter=input_format.delimiter,
            quotechar=input_format.quotechar,
            doublequote=input_format.doublequote,
            strict=True,
        )
        headers = tuple(reader.fieldnames or ())
        if not headers:
            raise ValueError("source CSV must contain a header row")

        for source_row_number, values in enumerate(reader, start=1):
            if None in values:
                raise ValueError(
                    f"source CSV row {source_row_number} has more values than headers"
                )
            normalized_values = {
                header: value if isinstance(value, str) else ""
                for header, value in values.items()
            }
            rows.append(
                CsvSourceRow(
                    source_row_number=source_row_number,
                    values=normalized_values,
                )
            )

    return CsvReadResult(
        encoding=input_format.encoding,
        delimiter=input_format.delimiter,
        quotechar=input_format.quotechar,
        headers=headers,
        rows=tuple(rows),
    )


# =============================================================================
# Stable CSV output adapter
# =============================================================================


MAPPED_JOB_COLUMNS = tuple(MappedJob.model_fields)
CLEANED_JOB_COLUMNS = tuple(CleanedJob.model_fields)
REJECTED_RECORD_COLUMNS = tuple(RejectedRecord.model_fields)
QUALITY_METRIC_COLUMNS = tuple(QualityMetric.model_fields)


def serialize_csv_value(value: object) -> str:
    """Serialize typed values to deterministic UTF-8 CSV cell text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, (tuple, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def write_model_csv(
    path: Path, records: tuple[Any, ...], columns: tuple[str, ...]
) -> int:
    """Write typed model records with stable UTF-8 headers and column order."""
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(
            output_file,
            fieldnames=columns,
            delimiter=",",
            quotechar='"',
            doublequote=True,
            extrasaction="raise",
        )
        writer.writeheader()
        for record in records:
            values = record.model_dump(mode="python")
            writer.writerow(
                {column: serialize_csv_value(values[column]) for column in columns}
            )
    return len(records)


def write_pipeline_outputs(
    *,
    output_dir: Path,
    mapped_jobs: tuple[MappedJob, ...],
    cleaned_jobs: tuple[CleanedJob, ...],
    rejected_records: tuple[RejectedRecord, ...],
    quality_metrics: tuple[QualityMetric, ...],
) -> dict[str, int]:
    """Write all four approved pipeline CSV outputs and return their row counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "mapped_jobs.csv": (mapped_jobs, MAPPED_JOB_COLUMNS),
        "cleaned_jobs.csv": (cleaned_jobs, CLEANED_JOB_COLUMNS),
        "rejected_jobs.csv": (rejected_records, REJECTED_RECORD_COLUMNS),
        "data_quality_summary.csv": (quality_metrics, QUALITY_METRIC_COLUMNS),
    }
    return {
        filename: write_model_csv(output_dir / filename, records, columns)
        for filename, (records, columns) in outputs.items()
    }
