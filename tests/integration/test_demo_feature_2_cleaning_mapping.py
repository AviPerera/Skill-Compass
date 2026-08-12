"""Test the national Feature 2 demonstration with sanitised JSONL data."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/demo_feature_2_cleaning_mapping.py"
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.jsonl"
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"


def load_script() -> ModuleType:
    """Load the presentation script without executing its command-line entry."""
    specification = importlib.util.spec_from_file_location(
        "demo_feature_2_cleaning_mapping_test_module", SCRIPT_PATH
    )
    assert specification is not None
    assert specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_demo_runs_existing_jsonl_pipeline_and_prints_safe_evidence(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script()
    exit_code = module.main(
        [
            "--input",
            str(FIXTURE_PATH),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "FEATURE 2 NATIONAL MAPPING AND CLEANING RESULT: PASS" in output
    assert "Raw job records: 4" in output
    assert "Final cleaned Feature 2 columns: 51" in output
    assert "Analytically eligible jobs: 2" in output
    assert "Actor invocation: NO" in output
    assert "Privacy boundary" in output
    assert "private-jsonl@example.test" not in output
    assert "private-salary@example.test" not in output
    assert "https://example.test/jobs" not in output
    assert "Press Enter to continue" not in output


def test_demo_missing_input_fails_without_traceback_or_actor(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    module = load_script()
    exit_code = module.main(
        [
            "--input",
            str(tmp_path / "missing.jsonl"),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Demonstration could not complete" in output
    assert "Actor invocation: NO" in output
    assert "FEATURE 2 NATIONAL MAPPING AND CLEANING RESULT: FAIL" in output
    assert "Traceback" not in output


def test_demo_has_no_collection_import_boundary() -> None:
    script_text = SCRIPT_PATH.read_text(encoding="utf-8")

    assert "skill_compass.collection" not in script_text
