"""Test the temporary Demo 2 script using only the fictional CSV fixture."""

import importlib.util
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/apify_seek_jobs.csv"
MAPPING_PATH = PROJECT_ROOT / "sources/apify_seek_current/source_mapping.yaml"
SCRIPT_PATH = PROJECT_ROOT / "scripts/demo_2_cleaning.py"


def load_demo_module() -> ModuleType:
    """Load the standalone presentation script without making scripts a package."""
    specification = importlib.util.spec_from_file_location(
        "demo_2_cleaning_test_module", SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Demo 2 script could not be loaded for testing")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def demo_main() -> Callable[[Sequence[str] | None], int]:
    """Return the loaded standalone script's typed main function."""
    return cast(Callable[[Sequence[str] | None], int], load_demo_module().main)


def test_non_step_demo_runs_without_prompt_and_returns_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = demo_main()(
        [
            "--input",
            str(FIXTURE_PATH),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path),
            "--sample-size",
            "2",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Press Enter to continue..." not in output
    assert "DEMO 2 CANONICAL MAPPING AND CLEANING RESULT: PASS" in output
    assert "Build reports." not in output
    assert "Prepare dashboards." not in output
    assert "https://example.test/jobs" not in output


def test_missing_input_produces_controlled_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = demo_main()(
        [
            "--input",
            str(tmp_path / "missing-private-input.csv"),
            "--mapping",
            str(MAPPING_PATH),
            "--output-dir",
            str(tmp_path / "outputs"),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "Demonstration could not complete" in output
    assert "DEMO 2 CANONICAL MAPPING AND CLEANING RESULT: FAIL" in output
    assert "Traceback" not in output
