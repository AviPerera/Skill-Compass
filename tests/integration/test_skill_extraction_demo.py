"""Test the Feature 3 live demonstration with the sanitised cleaned fixture."""

import importlib.util
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
PROFILE_PATH = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY_PATH = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
SCRIPT_PATH = PROJECT_ROOT / "scripts/demo_2_skill_extraction.py"


def load_demo_module() -> ModuleType:
    """Load the standalone presentation script without packaging scripts."""
    specification = importlib.util.spec_from_file_location(
        "demo_2_skill_extraction_test_module", SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Feature 3 demonstration script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def demo_main() -> Callable[[Sequence[str] | None], int]:
    """Return the loaded demonstration script's typed main function."""
    return cast(Callable[[Sequence[str] | None], int], load_demo_module().main)


def fixture_arguments(output_dir: Path) -> list[str]:
    """Return explicit sanitised input and configuration arguments."""
    return [
        "--input",
        str(FIXTURE_PATH),
        "--profile",
        str(PROFILE_PATH),
        "--dictionary",
        str(DICTIONARY_PATH),
        "--output-dir",
        str(output_dir),
        "--sample-size",
        "2",
        "--top-skills",
        "5",
    ]


def test_default_demo_runs_without_prompts_or_plot_windows(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = demo_main()(fixture_arguments(tmp_path))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Press Enter to continue..." not in output
    assert "DEMO 2 REQUIREMENT AND SKILL EXTRACTION RESULT: PASS" in output
    assert "Reconciliation formula: 4 = 3 + 1 + 0" in output
    assert "Build dashboards with Excel and stakeholder management." not in output
    assert "Power BI is not required. Produce data storytelling outputs." not in output
    assert "https://example.test/jobs" not in output
    assert (tmp_path / "charts/top_15_skills_by_job_count.png").stat().st_size > 0
    assert (tmp_path / "charts/skills_per_job_distribution.png").stat().st_size > 0


def test_step_mode_controls_pauses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt: prompts.append(prompt) or "")

    exit_code = demo_main()([*fixture_arguments(tmp_path), "--step"])

    assert exit_code == 0
    assert len(prompts) >= 10
    assert set(prompts) == {"\nPress Enter to continue..."}


def test_missing_cleaned_input_is_controlled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = fixture_arguments(tmp_path / "outputs")
    arguments[1] = str(tmp_path / "missing.csv")

    exit_code = demo_main()(arguments)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "uv run skill-compass clean-csv" in output
    assert "DEMO 2 REQUIREMENT AND SKILL EXTRACTION RESULT: FAIL" in output
    assert "Traceback" not in output


def test_show_plots_is_optional() -> None:
    module = load_demo_module()

    default_arguments = module.parse_arguments([])
    show_arguments = module.parse_arguments(["--show-plots"])

    assert default_arguments.show_plots is False
    assert show_arguments.show_plots is True
