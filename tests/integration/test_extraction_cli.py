"""Test the thin extraction CLI using only the sanitised cleaned-job fixture."""

from pathlib import Path

import pytest

from skill_compass.cli import main

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"


def test_extract_requirements_cli_returns_safe_success_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "extract-requirements",
            "--input",
            str(FIXTURE_PATH),
            "--profile",
            str(PROFILE_PATH),
            "--dictionary",
            str(DICTIONARY_PATH),
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Job-requirement matches: 13" in output
    assert "Reconciliation: PASS" in output
    assert "Build dashboards" not in output
    assert "https://example.test/jobs" not in output


def test_missing_cleaned_input_returns_instruction_without_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = main(
        [
            "extract-requirements",
            "--input",
            str(tmp_path / "missing.csv"),
            "--profile",
            str(PROFILE_PATH),
            "--dictionary",
            str(DICTIONARY_PATH),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "uv run skill-compass clean-csv" in output
    assert "Traceback" not in output
