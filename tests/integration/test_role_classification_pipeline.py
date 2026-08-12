"""Test the Feature 5 cleaned-CSV service, outputs, CLI, and demo boundary."""

import csv
import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

from skill_compass.cli import main
from skill_compass.services.classify_roles import process_role_classification

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = PROJECT_ROOT / "tests/fixtures/cleaned_jobs.csv"
RULES = PROJECT_ROOT / "profiles/data_analytics/role_rules.yaml"
SCRIPT = PROJECT_ROOT / "scripts/demo_feature_5_role_classification.py"


def _headers(path: Path) -> tuple[str, ...]:
    """Read only stable CSV headers for privacy-contract assertions."""
    with path.open("r", encoding="utf-8", newline="") as input_file:
        return tuple(csv.DictReader(input_file).fieldnames or ())


def _load_demo_script() -> ModuleType:
    """Load the standalone script without making scripts a package."""
    specification = importlib.util.spec_from_file_location(
        "feature_5_demo_test_module", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Feature 5 demonstration script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return cast(ModuleType, module)


def test_role_pipeline_writes_reconciled_privacy_safe_outputs(tmp_path: Path) -> None:
    run = process_role_classification(
        input_path=FIXTURE, rules_path=RULES, output_dir=tmp_path
    )

    result = run.classification
    assert result.input_job_count == 4
    assert len(result.classifications) == 4
    assert sum(row.job_count for row in result.distribution) == 4
    assert len(result.review_queue) == result.quality.review_count
    assert result.reconciliation_passed is True
    assert {item.path.name for item in run.output_files} == {
        "job_role_classifications.csv",
        "role_classification_evidence.csv",
        "role_distribution_summary.csv",
        "role_classification_quality.csv",
        "review_queue.csv",
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


def test_classify_roles_cli_uses_local_files_only(tmp_path: Path, capsys: Any) -> None:
    exit_code = main(
        [
            "classify-roles",
            "--input",
            str(FIXTURE),
            "--rules",
            str(RULES),
            "--output-dir",
            str(tmp_path),
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Reconciliation: PASS" in output
    assert "External API requests: 0" in output


def test_demo_script_delegates_to_the_feature_5_service(tmp_path: Path) -> None:
    module = _load_demo_script()
    captured: dict[str, Any] = {}

    def fake_command(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 0

    module.run_feature_5_demo_command = fake_command
    exit_code = module.main(
        [
            "--input",
            str(FIXTURE),
            "--rules",
            str(RULES),
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert captured == {
        "input_path": FIXTURE,
        "rules_path": RULES,
        "output_dir": tmp_path,
    }
