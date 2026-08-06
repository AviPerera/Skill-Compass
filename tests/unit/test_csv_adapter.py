"""Verify explicit CSV parsing and deterministic logical source row numbers."""

from pathlib import Path

from skill_compass.adapters.csv import read_source_csv
from skill_compass.mapping.config import load_mapping_config

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.csv"


def test_fixture_uses_explicit_csv_contract() -> None:
    mapping = load_mapping_config(MAPPING_PATH)

    result = read_source_csv(FIXTURE_PATH, mapping.input_format)

    assert result.encoding == "utf-8-sig"
    assert result.delimiter == ","
    assert result.quotechar == '"'
    assert len(result.rows) == 10
    assert result.rows[0].source_row_number == 1
    assert result.rows[-1].source_row_number == 10
    assert "contact_email" in result.headers
