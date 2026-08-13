"""Test Feature 8 local joins, exports, CLI, and privacy boundaries.

These integration tests use only sanitised fixtures and must not access private
national data, invoke external services, or assert invented analytical labels.
"""

from __future__ import annotations

import csv
import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from skill_compass.cli import main
from skill_compass.services.build_analytics import process_analytics
from skill_compass.services.classify_profile_relevance import (
    process_profile_relevance,
)
from skill_compass.services.classify_roles import process_role_classification
from skill_compass.services.classify_seniority import (
    process_seniority_classification,
)
from skill_compass.services.demo_dashboard import run_dashboard_demo
from skill_compass.services.extract_requirements import process_cleaned_csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
PROFILE = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
ROLE_RULES = PROJECT_ROOT / "profiles/data_analytics/role_rules.yaml"
SENIORITY_RULES = PROJECT_ROOT / "profiles/data_analytics/seniority_rules.yaml"
RELEVANCE_RULES = PROJECT_ROOT / "profiles/data_analytics/relevance_rules.yaml"
REFERENCE_WORKBOOK = (
    PROJECT_ROOT
    / "powerbi/reference/Skill_Compass_Final_Synthetic_PowerBI_Dataset_100_Jobs.xlsx"
)
SCRIPT = PROJECT_ROOT / "scripts/demo_dashboard_visuals.py"


def _prepare_upstream(input_dir: Path) -> None:
    """Generate all local typed inputs required by the Feature 8 service."""
    input_dir.mkdir(parents=True)
    cleaned_path = input_dir / "cleaned_jobs.csv"
    shutil.copyfile(FIXTURE, cleaned_path)
    process_cleaned_csv(
        input_path=cleaned_path,
        profile_path=PROFILE,
        dictionary_path=DICTIONARY,
        output_dir=input_dir / "skill_extraction",
    )
    process_role_classification(
        input_path=cleaned_path,
        rules_path=ROLE_RULES,
        output_dir=input_dir / "role_classification",
    )
    process_seniority_classification(
        input_path=cleaned_path,
        rules_path=SENIORITY_RULES,
        output_dir=input_dir / "seniority_classification",
    )
    process_profile_relevance(
        input_dir=input_dir,
        rules_path=RELEVANCE_RULES,
        output_dir=input_dir / "profile_relevance",
    )


def _headers(path: Path) -> tuple[str, ...]:
    """Return one generated CSV header for privacy assertions."""
    with path.open("r", encoding="utf-8", newline="") as input_file:
        return tuple(csv.DictReader(input_file).fieldnames or ())


def _load_demo_script() -> ModuleType:
    """Load the thin demo entry point without making scripts a package."""
    specification = importlib.util.spec_from_file_location(
        "feature_8_dashboard_demo_test_module", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Feature 8 dashboard demo script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return cast(ModuleType, module)


def test_analytics_pipeline_reconciles_and_writes_privacy_safe_outputs(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "analytics"
    _prepare_upstream(input_dir)

    run = process_analytics(
        input_dir=input_dir,
        profile_path=PROFILE,
        dictionary_path=DICTIONARY,
        role_rules_path=ROLE_RULES,
        seniority_rules_path=SENIORITY_RULES,
        output_dir=output_dir,
        minimum_sample_size=1,
    )

    result = run.analytics
    assert result.classifier_input_job_count == 4
    assert (
        result.included_job_count + result.excluded_job_count + result.review_job_count
        == 4
    )
    assert len(result.job_facts) == result.included_job_count
    assert sum(row.job_count for row in result.seniority_distribution) == sum(
        job.seniority_rank is not None for job in result.job_facts
    )
    assert result.reconciliation_passed is True
    assert {item.path.name for item in run.output_files} == {
        "job_facts.csv",
        "job_skill_facts.csv",
        "skill_demand.csv",
        "skill_role_demand.csv",
        "role_summary.csv",
        "role_seniority_summary.csv",
        "seniority_summary.csv",
        "state_summary.csv",
        "city_summary.csv",
        "employment_type_summary.csv",
        "work_mode_summary.csv",
        "skill_combinations.csv",
        "analytics_quality_summary.csv",
        "analytics_run_summary.json",
    }
    forbidden = {
        "description_text_clean",
        "summary_text_clean",
        "evidence_snippet",
        "contact_email",
        "contact_phone",
        "tracking_token",
    }
    for item in run.output_files:
        if item.path.suffix == ".csv":
            assert forbidden.isdisjoint(_headers(item.path))


def test_build_analytics_cli_uses_existing_local_outputs_only(
    tmp_path: Path, capsys: Any
) -> None:
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "analytics"
    _prepare_upstream(input_dir)

    exit_code = main(
        [
            "build-analytics",
            "--input",
            str(input_dir),
            "--profile",
            str(PROFILE),
            "--dictionary",
            str(DICTIONARY),
            "--role-rules",
            str(ROLE_RULES),
            "--seniority-rules",
            str(SENIORITY_RULES),
            "--output-dir",
            str(output_dir),
            "--minimum-sample-size",
            "1",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reconciliation: PASS" in output
    assert "External API requests: 0" in output


def test_dashboard_demo_generates_complete_approved_visual_inventory(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "dashboard_demo"
    _prepare_upstream(input_dir)

    result = run_dashboard_demo(
        input_dir=input_dir,
        output_dir=output_dir,
        profile_path=PROFILE,
        dictionary_path=DICTIONARY,
        role_rules_path=ROLE_RULES,
        seniority_rules_path=SENIORITY_RULES,
        reference_workbook=REFERENCE_WORKBOOK,
    )

    assert len(result.visuals) == 22
    assert {visual.page_number for visual in result.visuals} == set(range(1, 7))
    assert all(visual.path.is_file() for visual in result.visuals)
    assert all(visual.path.stat().st_size > 0 for visual in result.visuals)
    assert (output_dir / "visuals/dashboard_visual_manifest.json").is_file()
    assert sum("Synthetic" in visual.data_source for visual in result.visuals) == 2


def test_dashboard_demo_script_delegates_all_local_paths(tmp_path: Path) -> None:
    module = _load_demo_script()
    captured: dict[str, Any] = {}

    def fake_command(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 0

    module.run_dashboard_demo_command = fake_command
    input_dir = tmp_path / "processed"
    output_dir = tmp_path / "dashboard"
    exit_code = module.main(
        [
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--profile",
            str(PROFILE),
            "--dictionary",
            str(DICTIONARY),
            "--role-rules",
            str(ROLE_RULES),
            "--seniority-rules",
            str(SENIORITY_RULES),
            "--reference-workbook",
            str(REFERENCE_WORKBOOK),
        ]
    )

    assert exit_code == 0
    assert captured == {
        "input_dir": input_dir,
        "output_dir": output_dir,
        "profile_path": PROFILE,
        "dictionary_path": DICTIONARY,
        "role_rules_path": ROLE_RULES,
        "seniority_rules_path": SENIORITY_RULES,
        "reference_workbook": REFERENCE_WORKBOOK,
    }
