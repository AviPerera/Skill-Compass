"""Test Feature 7 file and CLI boundaries in the integration-test layer.

These tests use the sanitized repository fixture and must not access private
datasets, invoke external services, or duplicate classification rules.
"""

import csv
import importlib.util
import shutil
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from skill_compass.cli import main
from skill_compass.services.classify_profile_relevance import (
    process_profile_relevance,
)
from skill_compass.services.classify_roles import process_role_classification
from skill_compass.services.classify_seniority import (
    process_seniority_classification,
)
from skill_compass.services.extract_requirements import process_cleaned_csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
PROFILE = PROJECT_ROOT / "profiles/data_analytics/profile.yaml"
DICTIONARY = PROJECT_ROOT / "profiles/data_analytics/requirements.csv"
ROLE_RULES = PROJECT_ROOT / "profiles/data_analytics/role_rules.yaml"
SENIORITY_RULES = PROJECT_ROOT / "profiles/data_analytics/seniority_rules.yaml"
RELEVANCE_RULES = PROJECT_ROOT / "profiles/data_analytics/relevance_rules.yaml"
SCRIPT = PROJECT_ROOT / "scripts/demo_feature_7_profile_relevance.py"


def _headers(path: Path) -> tuple[str, ...]:
    """Read only stable CSV headers for privacy-contract assertions."""
    with path.open("r", encoding="utf-8", newline="") as input_file:
        return tuple(csv.DictReader(input_file).fieldnames or ())


def _prepare_upstream(input_dir: Path) -> None:
    """Generate local Feature 3/5/6 outputs from the sanitized fixture."""
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


def _load_demo_script() -> ModuleType:
    """Load the standalone script without making scripts a package."""
    specification = importlib.util.spec_from_file_location(
        "feature_7_demo_test_module", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Feature 7 demonstration script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return cast(ModuleType, module)


def test_relevance_pipeline_writes_reconciled_privacy_safe_outputs(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "profile_relevance"
    _prepare_upstream(input_dir)

    run = process_profile_relevance(
        input_dir=input_dir,
        rules_path=RELEVANCE_RULES,
        output_dir=output_dir,
    )

    result = run.classification
    assert result.input_job_count == 4
    assert len(result.classifications) == 4
    assert (
        result.summary.included_count
        + result.summary.excluded_count
        + result.summary.review_count
        == 4
    )
    assert len(result.review_queue) == result.summary.review_count
    assert len(result.diagnostics) == 4
    assert result.reconciliation_passed is True
    assert {item.path.name for item in run.output_files} == {
        "job_profile_relevance.csv",
        "profile_relevance_evidence.csv",
        "profile_relevance_summary.csv",
        "profile_relevance_review_queue.csv",
        "profile_relevance_diagnostics.csv",
    }
    forbidden = {
        "description_text_clean",
        "company_name_raw",
        "job_url",
        "contact_email",
        "contact_phone",
        "tracking_token",
    }
    for output in run.output_files:
        assert forbidden.isdisjoint(_headers(output.path))


def test_classify_relevance_cli_uses_local_outputs_only(
    tmp_path: Path, capsys: Any
) -> None:
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "profile_relevance"
    _prepare_upstream(input_dir)

    exit_code = main(
        [
            "classify-relevance",
            "--input",
            str(input_dir),
            "--profile",
            "data_analytics",
            "--rules",
            str(RELEVANCE_RULES),
            "--output-dir",
            str(output_dir),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reconciliation: PASS" in output
    assert "External API requests: 0" in output


def test_demo_script_delegates_to_feature_7_service(tmp_path: Path) -> None:
    module = _load_demo_script()
    captured: dict[str, Any] = {}

    def fake_command(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 0

    module.run_feature_7_demo_command = fake_command
    input_dir = tmp_path / "processed"
    output_dir = input_dir / "profile_relevance"
    exit_code = module.main(
        [
            "--input-dir",
            str(input_dir),
            "--rules",
            str(RELEVANCE_RULES),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert captured == {
        "input_dir": input_dir,
        "rules_path": RELEVANCE_RULES,
        "output_dir": output_dir,
    }
