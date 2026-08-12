"""Test full-collection script and CLI dry runs without external requests."""

import importlib.util
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest

from skill_compass.cli import main as cli_main

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/run_full_collection.py"


def _script_main() -> Callable[[Sequence[str] | None], int]:
    """Load the standalone script without turning scripts into a package."""
    specification = importlib.util.spec_from_file_location(
        "run_full_collection_test_module", SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("full collection script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    loaded_module = cast(ModuleType, module)
    return cast(Callable[[Sequence[str] | None], int], loaded_module.main)


def test_script_dry_run_derives_66_and_makes_no_requests(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = _script_main()(["--dry-run", "--output-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "State-level scopes:            6" in output
    assert "NSW classification scopes:   30" in output
    assert "VIC classification scopes:   30" in output
    assert "Actor runs planned:           66" in output
    assert "No Actor requests made." in output
    assert list(tmp_path.iterdir()) == []


def test_cli_dry_run_uses_same_service(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(["collect-full", "--dry-run", "--output-root", str(tmp_path)])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Total scopes expected:        66" in output
    assert "No Apify credits consumed." in output


def test_script_requires_explicit_mode_and_only_shows_help(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as error:
        _script_main()([])

    captured = capsys.readouterr()
    assert error.value.code == 2
    assert "--dry-run" in captured.err
    assert "--execute" in captured.err
