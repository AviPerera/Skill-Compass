"""Test the thin clean-csv CLI against the fictional integration fixture."""

from pathlib import Path

import pytest

from skill_compass.cli import main

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.csv"
JSONL_FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.jsonl"
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"


def test_clean_csv_cli_returns_success_and_safe_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "clean-csv",
            "--input",
            str(FIXTURE_PATH),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reconciliation: PASS" in output
    assert "Fictional description" not in output
    assert "https://example.test/jobs" not in output


def test_clean_jsonl_cli_processes_existing_data_without_actor_invocation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "clean-jsonl",
            "--input",
            str(JSONL_FIXTURE_PATH),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "clean-jsonl completed successfully" in output
    assert "Actor invocation: NO" in output
    assert "Reconciliation: PASS" in output
    assert "private-jsonl@example.test" not in output
