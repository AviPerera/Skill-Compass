"""Expose boundary adapters for current file-based pipeline inputs and outputs.

Adapters translate external storage formats only and must not contain mapping,
cleaning, deduplication, hashing, or quality-metric business rules.
"""

from skill_compass.adapters.csv import (
    CsvReadResult,
    CsvSourceRow,
    read_source_csv,
    write_pipeline_outputs,
)

__all__ = [
    "CsvReadResult",
    "CsvSourceRow",
    "read_source_csv",
    "write_pipeline_outputs",
]
