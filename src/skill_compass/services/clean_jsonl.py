"""Process strict source JSONL through the canonical Feature 2 pipeline.

This application service connects the JSONL adapter to format-neutral mapping
and cleaning orchestration. It must not invoke Apify, implement transformation
rules, or contain presentation logic.
"""

from __future__ import annotations

from pathlib import Path

from skill_compass.adapters.jsonl import read_source_jsonl
from skill_compass.mapping.config import load_mapping_config
from skill_compass.services.clean_source import CleaningRunResult, process_source_rows

# =============================================================================
# Reusable JSONL processing boundary
# =============================================================================


def process_jsonl(
    *, input_path: Path, mapping_path: Path, output_dir: Path
) -> CleaningRunResult:
    """Map, deduplicate, clean, reconcile, and write one strict JSONL input."""
    mapping_config = load_mapping_config(mapping_path)
    jsonl_input = read_source_jsonl(input_path)
    return process_source_rows(
        input_path=input_path,
        output_dir=output_dir,
        input_encoding=jsonl_input.encoding,
        source_column_count=len(jsonl_input.source_fields),
        source_rows=jsonl_input.rows,
        mapping_config=mapping_config,
    )
