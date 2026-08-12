"""Test the thin Feature 4 live demonstration script boundary."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/demo_feature_4.py"


def _load_script() -> ModuleType:
    """Load the standalone script without turning scripts into a package."""
    specification = importlib.util.spec_from_file_location(
        "feature_4_demo_test_module", SCRIPT_PATH
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("Feature 4 demonstration script could not be loaded")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return cast(ModuleType, module)


def test_demo_script_delegates_without_containing_retrieval_logic(
    tmp_path: Path,
) -> None:
    module = _load_script()
    captured: dict[str, Any] = {}

    def fake_command(**kwargs: Any) -> int:
        captured.update(kwargs)
        return 0

    module.run_feature_4_demo_command = fake_command

    exit_code = module.main(["--output-root", str(tmp_path), "--force"])

    assert exit_code == 0
    assert captured["force"] is True
    assert captured["output_root"] == tmp_path
