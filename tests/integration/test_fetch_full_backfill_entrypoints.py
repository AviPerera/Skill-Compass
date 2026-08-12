"""Test no-cost national fetch manifest validation through both entry points."""

import importlib.util
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from skill_compass.cli import main as cli_main
from skill_compass.collection.search_scopes import (
    build_search_scopes,
    load_search_scope_config,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/fetch_full_backfill.py"
SEARCH_SCOPES_PATH = PROJECT_ROOT / "profiles/data_analytics/search_scopes.yaml"


def _script_main() -> Callable[[Sequence[str] | None], int]:
    """Load the standalone script without making scripts a package."""
    specification = importlib.util.spec_from_file_location(
        "fetch_full_backfill_test_module", SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("fetch full backfill script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    loaded_module = cast(ModuleType, module)
    return cast(Callable[[Sequence[str] | None], int], loaded_module.main)


def _write_complete_manifest(path: Path) -> None:
    """Write fictional references for all currently configured scopes."""
    scopes = build_search_scopes(load_search_scope_config(SEARCH_SCOPES_PATH))
    path.write_text(
        "scope_id,run_id,dataset_id\n"
        + "".join(
            f"{scope.scope_id},,fictional-{scope.scope_id}\n" for scope in scopes
        ),
        encoding="utf-8",
    )


def test_script_complete_manifest_dry_run_reports_ready_and_zero_requests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "full_backfill_sources.csv"
    _write_complete_manifest(manifest_path)

    exit_code = _script_main()(
        [
            "--manifest",
            str(manifest_path),
            "--dry-run",
            "--include-all-successful-runs",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Actor invocation: NO" in output
    assert "Mode: Existing Apify datasets only" in output
    assert "Expected scopes: 66" in output
    assert "Supplied datasets: 66" in output
    assert "Missing scopes: 0" in output
    assert "Manifest ready: YES" in output
    assert "Supplemental discovery: REQUESTED" in output
    assert "Supplemental Actor: scrapersdelight/seek-jobs-scraper" in output
    assert "Successful-run discovery was not executed." in output
    assert "No Apify API request made." in output


def test_cli_incomplete_manifest_dry_run_reports_not_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "partial.csv"
    manifest_path.write_text(
        "scope_id,run_id,dataset_id\nnt_state,,fictional-nt\n",
        encoding="utf-8",
    )

    exit_code = cli_main(
        ["fetch-backfill", "--manifest", str(manifest_path), "--dry-run"]
    )

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Supplied datasets: 1" in output
    assert "Missing scopes: 65" in output
    assert "Manifest ready: NO" in output
    assert "No Actor was invoked." in output


def test_invalid_manifest_dry_run_fails_before_api_access(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = tmp_path / "invalid.csv"
    manifest_path.write_text(
        "scope_id,run_id,dataset_id\nunknown,,fictional\n",
        encoding="utf-8",
    )

    exit_code = _script_main()(["--manifest", str(manifest_path), "--dry-run"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "unknown scope_id" in output
    assert "Actor invocation: NO" in output
    assert "No Apify API request made." in output
