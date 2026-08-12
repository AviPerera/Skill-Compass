"""Regression-test the Feature 1 environment demonstration as a subprocess.

This integration test verifies the public script boundary and must not duplicate
its environment or project-metadata validation logic.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = PROJECT_ROOT / "scripts/demo_feature_1.py"


def test_feature_1_demo_accepts_current_runtime_dependencies() -> None:
    """Require the non-interactive demonstration to accept later dependencies."""
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "Press Enter to continue..." not in completed.stdout
    assert "[INFO] Runtime dependencies (" in completed.stdout
    assert "FEATURE 1 DEMONSTRATION RESULT: PASS" in completed.stdout
