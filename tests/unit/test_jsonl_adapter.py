"""Verify strict JSONL parsing and deterministic slash-path flattening."""

from pathlib import Path

import pytest

from skill_compass.adapters.jsonl import read_source_jsonl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.jsonl"


def test_fixture_flattens_objects_arrays_and_scalars() -> None:
    result = read_source_jsonl(FIXTURE_PATH)

    assert result.encoding == "utf-8"
    assert len(result.rows) == 4
    assert result.rows[0].source_row_number == 1
    assert result.rows[-1].source_row_number == 4
    assert result.rows[0].values["bullet_points/1"] == "Python"
    assert result.rows[0].values["is_remote"] == "false"
    assert result.rows[1].values["raw/detail/id"] == "2002"
    assert "raw/listing/classifications/0/classification/id" in result.source_fields


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ('{"id": 1}\nnot-json\n', "source JSONL line 2 is not valid JSON"),
        ('{"id": 1}\n[]\n', "source JSONL line 2 must be a JSON object"),
        ('{"id": 1}\n\n', "source JSONL line 2 is blank"),
        ("", "source JSONL must contain at least one JSON object"),
    ],
)
def test_invalid_jsonl_fails_with_safe_line_diagnostic(
    tmp_path: Path, content: str, message: str
) -> None:
    input_path = tmp_path / "invalid.jsonl"
    input_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        read_source_jsonl(input_path)
