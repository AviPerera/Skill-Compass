"""Process source CSV through the canonical Feature 2 pipeline.

This application service connects the CSV adapter to format-neutral mapping and
cleaning orchestration. It must not implement business rules or presentation
logic.
"""

from __future__ import annotations

from pathlib import Path

from skill_compass.adapters.csv import read_source_csv
from skill_compass.mapping.config import load_mapping_config
from skill_compass.services.clean_source import (
    CleaningRunResult,
    ReconciliationError,
    process_source_rows,
)

__all__ = ["CleaningRunResult", "ReconciliationError", "process_csv"]

# =============================================================================
# Reusable CSV processing boundary
# =============================================================================


def process_csv(
    *, input_path: Path, mapping_path: Path, output_dir: Path
) -> CleaningRunResult:
    """Map, deduplicate, clean, reconcile, and write one explicit CSV input."""
    mapping_config = load_mapping_config(mapping_path)
    csv_input = read_source_csv(input_path, mapping_config.input_format)
    return process_source_rows(
        input_path=input_path,
        output_dir=output_dir,
        input_encoding=csv_input.encoding,
        source_column_count=len(csv_input.headers),
        source_rows=csv_input.rows,
        mapping_config=mapping_config,
    )
