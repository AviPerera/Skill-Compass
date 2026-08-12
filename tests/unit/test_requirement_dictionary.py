"""Validate the literal versioned requirement dictionary and alias ownership."""

import csv
from pathlib import Path

import pytest

from skill_compass.extraction.dictionary import (
    REQUIRED_COLUMNS,
    load_requirement_dictionary,
)
from skill_compass.extraction.errors import ExtractionConfigurationError
from skill_compass.extraction.profile import load_extraction_profile

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"


def dictionary_rows() -> list[dict[str, str]]:
    """Read repository aliases into independent mutable test rows."""
    with DICTIONARY_PATH.open("r", encoding="utf-8", newline="") as input_file:
        return [dict(row) for row in csv.DictReader(input_file)]


def write_dictionary(path: Path, rows: list[dict[str, str]]) -> None:
    """Write modified alias rows with the stable contract header."""
    with path.open("w", encoding="utf-8", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def load(path: Path = DICTIONARY_PATH):
    """Load one dictionary using the approved repository profile."""
    return load_requirement_dictionary(path, load_extraction_profile(PROFILE_PATH))


def test_valid_dictionary_loads_and_hashes_deterministically() -> None:
    first = load()
    second = load()

    assert first.dictionary_version == "0.1.0"
    assert len(first.requirements) == 31
    assert len(first.active_aliases) >= 50
    assert len(first.category_codes) == 9
    assert first.dictionary_hash == second.dictionary_hash


def test_missing_required_column_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing_column.csv"
    path.write_text("requirement_code,alias_text\nsql,SQL\n", encoding="utf-8")

    with pytest.raises(ExtractionConfigurationError, match="missing columns"):
        load(path)


def test_duplicate_active_alias_is_rejected(tmp_path: Path) -> None:
    rows = dictionary_rows()
    rows.append(dict(rows[0]))
    path = tmp_path / "duplicate.csv"
    write_dictionary(path, rows)

    with pytest.raises(ExtractionConfigurationError, match="duplicate active alias"):
        load(path)


def test_conflicting_alias_ownership_is_rejected(tmp_path: Path) -> None:
    rows = dictionary_rows()
    conflicting = dict(rows[0])
    conflicting.update(
        {
            "requirement_code": "another_skill",
            "requirement_name": "Another Skill",
            "sort_order": "32",
        }
    )
    rows.append(conflicting)
    path = tmp_path / "conflicting.csv"
    write_dictionary(path, rows)

    with pytest.raises(ExtractionConfigurationError, match="conflicting active alias"):
        load(path)


@pytest.mark.parametrize(
    ("field_name", "value", "message"),
    [
        ("requirement_code", "Invalid Code", "invalid requirement_code"),
        ("match_type", "regex", "invalid match_type"),
        ("case_sensitive", "sometimes", "invalid Boolean"),
        ("category_code", "Invalid Category", "invalid category_code"),
    ],
)
def test_invalid_alias_fields_are_rejected(
    tmp_path: Path, field_name: str, value: str, message: str
) -> None:
    rows = dictionary_rows()
    rows[0][field_name] = value
    path = tmp_path / "invalid.csv"
    write_dictionary(path, rows)

    with pytest.raises(ExtractionConfigurationError, match=message):
        load(path)


def test_inactive_alias_is_ignored(tmp_path: Path) -> None:
    rows = dictionary_rows()
    rows[0]["active"] = "false"
    path = tmp_path / "inactive.csv"
    write_dictionary(path, rows)

    dictionary = load(path)

    assert not any(
        alias.requirement_code == "sql" and alias.alias_text == "SQL"
        for alias in dictionary.active_aliases
    )


def test_active_dictionary_version_must_match_profile(tmp_path: Path) -> None:
    rows = dictionary_rows()
    rows[0]["dictionary_version"] = "0.2.0"
    path = tmp_path / "mixed_version.csv"
    write_dictionary(path, rows)

    with pytest.raises(ExtractionConfigurationError, match="dictionary version"):
        load(path)
