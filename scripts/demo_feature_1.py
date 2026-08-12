"""Present the temporary Feature 1 environment-baseline demonstration.

This script belongs to manual presentation support and must not provide a
production CLI, execute quality tools, or implement later feature logic.
"""

from __future__ import annotations

import argparse
import importlib
import platform
import re
import sys
import tomllib
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import Any

# =============================================================================
# Demonstration configuration
# =============================================================================

BANNER_WIDTH = 79
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_DISTRIBUTION_NAME = "skill-compass"
EXPECTED_PACKAGE_VERSION = "0.1.0"
EXPECTED_PYTHON_REQUIREMENT = ">=3.12,<3.13"
EXPECTED_SOURCE_LAYOUT = "src/skill_compass/"

REQUIRED_FILES = (
    ".python-version",
    "pyproject.toml",
    "uv.lock",
    ".env.example",
    "README.md",
    "src/skill_compass/__init__.py",
    "tests/test_package_import.py",
)

QUALITY_COMMANDS = (
    "uv sync",
    "uv run pytest",
    "uv run ruff check .",
    "uv run ruff format --check .",
    'uv run python -c "import skill_compass; print(skill_compass.__version__)"',
)

FEATURE_1_CONTENTS = (
    "Python environment configuration",
    "package metadata",
    "minimal package initialisation",
    "an import smoke test",
    "reproducibility instructions",
)

OUT_OF_SCOPE_FEATURES = (
    "source mapping",
    "CSV processing",
    "cleaning",
    "skill extraction",
    "role classification",
    "seniority classification",
    "PostgreSQL",
    "Power BI integration",
    "scheduled automation",
)


# =============================================================================
# Result models
# =============================================================================


@dataclass(frozen=True, slots=True)
class CheckResult:
    """Represent one presentation-level validation result."""

    label: str
    passed: bool


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    """Hold the small subset of project metadata shown in the demonstration."""

    distribution_name: str
    version: str
    python_requirement: str
    runtime_dependencies: tuple[str, ...]
    development_dependencies: tuple[str, ...]
    source_layout: str | None


@dataclass(slots=True)
class StepController:
    """Pause between presentation sections when interactive mode is requested."""

    enabled: bool

    def pause(self) -> None:
        """Wait for confirmation, disabling pauses when input is unavailable."""
        if not self.enabled:
            return

        try:
            input("\nPress Enter to continue...")
        except EOFError:
            print("\nInteractive input is unavailable; continuing without pauses.")
            self.enabled = False


# =============================================================================
# Terminal presentation helpers
# =============================================================================


def print_banner() -> None:
    """Print the opening demonstration banner."""
    print("=" * BANNER_WIDTH)
    print("SKILL COMPASS — FEATURE 1 ENVIRONMENT BASELINE DEMONSTRATION")
    print("=" * BANNER_WIDTH)


def print_section(number: int, title: str) -> None:
    """Print a consistently formatted numbered section heading."""
    heading = f"{number}. {title}"
    print(f"\n{heading}")
    print("-" * len(heading))


def print_status(passed: bool, message: str) -> None:
    """Print one deterministic PASS or FAIL line."""
    marker = "PASS" if passed else "FAIL"
    print(f"[{marker}] {message}")


def display_value(value: str) -> str:
    """Return a presentation-safe placeholder for a missing string value."""
    return value or "<unavailable>"


# =============================================================================
# Demonstration sections
# =============================================================================


def show_demonstration_context() -> None:
    """Present the project and execution context."""
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    print_section(1, "Demonstration context")
    print("Project name: Skill Compass")
    print("Current implementation: Phase 2, Stage 2")
    print("Demonstration feature: Feature 1 — Python Environment Baseline")
    print(f"Current date and time: {current_time}")
    print(f"Repository root: {REPOSITORY_ROOT}")
    print(
        "Purpose: Verify the reproducible development environment and the "
        "importable package foundation."
    )


def check_required_files() -> CheckResult:
    """Check and display the required Feature 1 repository files."""
    print_section(2, "Required repository files")
    all_files_exist = True

    for relative_path in REQUIRED_FILES:
        exists = (REPOSITORY_ROOT / relative_path).is_file()
        all_files_exist = all_files_exist and exists
        message = f"{relative_path} exists" if exists else f"{relative_path} is missing"
        print_status(exists, message)

    return CheckResult("Required files", all_files_exist)


def read_python_version_file() -> str:
    """Read the configured Python version without exposing an expected traceback."""
    version_path = REPOSITORY_ROOT / ".python-version"
    try:
        return version_path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def check_python_environment() -> CheckResult:
    """Display interpreter details and validate the Python 3.12 baseline."""
    print_section(3, "Python environment")

    active_environment = (
        Path(sys.prefix).resolve() if sys.prefix != sys.base_prefix else None
    )
    configured_version = read_python_version_file()
    interpreter_is_312 = sys.version_info[:2] == (3, 12)
    configuration_is_312 = configured_version == "3.12"

    print(f"Python executable: {Path(sys.executable).resolve()}")
    print(f"Full Python version: {sys.version.replace(chr(10), ' ')}")
    print(f"Python implementation: {platform.python_implementation()}")
    if active_environment is None:
        print("Active virtual environment: <not detected>")
    else:
        print(f"Active virtual environment: {active_environment}")

    print_status(interpreter_is_312, "Active interpreter satisfies Python 3.12")
    print(f".python-version content: {display_value(configured_version)}")
    print_status(configuration_is_312, ".python-version declares Python 3.12")

    return CheckResult("Python 3.12", interpreter_is_312 and configuration_is_312)


def dependency_name(requirement: str) -> str:
    """Extract a normalized package name from a PEP 508-style requirement."""
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement.strip())
    return match.group(0).lower() if match else requirement.strip().lower()


def string_value(value: object) -> str:
    """Return a string metadata value or an empty validation value."""
    return value if isinstance(value, str) else ""


def string_sequence(value: object) -> tuple[str, ...]:
    """Convert a TOML array to a tuple containing only string entries."""
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def load_project_metadata() -> tuple[ProjectMetadata | None, str | None]:
    """Load required project fields from pyproject.toml using the standard library."""
    pyproject_path = REPOSITORY_ROOT / "pyproject.toml"

    try:
        with pyproject_path.open("rb") as pyproject_file:
            document: dict[str, Any] = tomllib.load(pyproject_file)
    except FileNotFoundError:
        return None, "pyproject.toml is missing"
    except tomllib.TOMLDecodeError as error:
        return None, f"pyproject.toml contains invalid TOML: {error}"
    except OSError as error:
        return None, f"pyproject.toml could not be read: {error}"

    project = document.get("project")
    dependency_groups = document.get("dependency-groups")
    if not isinstance(project, dict):
        return None, "pyproject.toml is missing the [project] table"

    runtime_dependencies = string_sequence(project.get("dependencies"))
    dev_requirements: tuple[str, ...] = ()
    if isinstance(dependency_groups, dict):
        dev_requirements = string_sequence(dependency_groups.get("dev"))

    development_dependencies = tuple(
        sorted(dependency_name(requirement) for requirement in dev_requirements)
    )
    source_layout = (
        EXPECTED_SOURCE_LAYOUT
        if (REPOSITORY_ROOT / EXPECTED_SOURCE_LAYOUT).is_dir()
        else None
    )

    return (
        ProjectMetadata(
            distribution_name=string_value(project.get("name")),
            version=string_value(project.get("version")),
            python_requirement=string_value(project.get("requires-python")),
            runtime_dependencies=runtime_dependencies,
            development_dependencies=development_dependencies,
            source_layout=source_layout,
        ),
        None,
    )


def check_project_metadata() -> CheckResult:
    """Display and validate the approved Feature 1 project metadata."""
    print_section(4, "Project metadata")
    project, error = load_project_metadata()

    if project is None:
        print_status(False, error or "Project metadata is unavailable")
        print("Distribution name: <unavailable>")
        print("Project version: <unavailable>")
        print("Declared Python requirement: <unavailable>")
        print("Runtime dependency count: <unavailable>")
        print("Development dependencies: <unavailable>")
        print("Package/source layout: <unavailable>")
        return CheckResult("Project metadata", False)

    name_is_valid = project.distribution_name == EXPECTED_DISTRIBUTION_NAME
    version_is_valid = project.version == EXPECTED_PACKAGE_VERSION
    requirement_is_valid = project.python_requirement == EXPECTED_PYTHON_REQUIREMENT
    tools_are_declared = {"pytest", "ruff"}.issubset(project.development_dependencies)
    layout_is_valid = project.source_layout == EXPECTED_SOURCE_LAYOUT

    # These independent checks make a metadata failure useful during a live review.
    print_status(
        name_is_valid, f"Distribution name: {display_value(project.distribution_name)}"
    )
    print_status(version_is_valid, f"Project version: {display_value(project.version)}")
    print_status(
        requirement_is_valid,
        f"Declared Python requirement: {display_value(project.python_requirement)}",
    )
    runtime_dependencies = tuple(
        sorted(
            dependency_name(requirement) for requirement in project.runtime_dependencies
        )
    )
    runtime_dependency_names = ", ".join(runtime_dependencies) or "<none>"
    print(
        f"[INFO] Runtime dependencies ({len(runtime_dependencies)}): "
        f"{runtime_dependency_names}"
    )
    dependencies = ", ".join(project.development_dependencies) or "<none>"
    print_status(tools_are_declared, f"Development dependencies: {dependencies}")
    source_layout = project.source_layout or "<not detected>"
    print_status(layout_is_valid, f"Package/source layout: {source_layout}")

    return CheckResult(
        "Project metadata",
        all(
            (
                name_is_valid,
                version_is_valid,
                requirement_is_valid,
                tools_are_declared,
                layout_is_valid,
            )
        ),
    )


def check_package_import() -> tuple[CheckResult, CheckResult]:
    """Import the package and validate its public version metadata."""
    print_section(5, "Package import")

    try:
        package = importlib.import_module("skill_compass")
    except ImportError as error:
        print_status(False, f"skill_compass import failed: {error}")
        print("Package module location: <unavailable>")
        print_status(False, "Package version is unavailable")
        return (
            CheckResult("Package import", False),
            CheckResult("Package version", False),
        )

    package_location = getattr(package, "__file__", None)
    package_version = getattr(package, "__version__", "")
    version_is_valid = package_version == EXPECTED_PACKAGE_VERSION

    print_status(True, "skill_compass imported successfully")
    print(f"Package module location: {package_location or '<unavailable>'}")
    print_status(
        version_is_valid,
        f"Package version is {display_value(package_version)}",
    )

    return (
        CheckResult("Package import", True),
        CheckResult("Package version", version_is_valid),
    )


def check_installed_tool(distribution_name: str) -> CheckResult:
    """Display the installed version of one required development tool."""
    try:
        installed_version = metadata.version(distribution_name)
    except metadata.PackageNotFoundError:
        print_status(False, f"{distribution_name} is not installed")
        return CheckResult(f"{distribution_name} availability", False)

    print_status(True, f"{distribution_name} version: {installed_version}")
    return CheckResult(f"{distribution_name} availability", True)


def check_installed_development_tools() -> tuple[CheckResult, CheckResult]:
    """Display installed pytest and Ruff versions without importing either tool."""
    print_section(6, "Installed development tools")
    return (check_installed_tool("pytest"), check_installed_tool("ruff"))


def show_manual_quality_commands() -> None:
    """Print, but never execute, the manual Feature 1 quality commands."""
    print_section(7, "Manual quality commands")
    print("Run these commands separately from this demonstration:")
    for command in QUALITY_COMMANDS:
        print(command)


def show_architecture_boundary() -> None:
    """Present the narrow Feature 1 architecture boundary."""
    print_section(8, "Architecture boundary confirmation")
    print("Feature 1 contains only:")
    for item in FEATURE_1_CONTENTS:
        print(f"- {item}")

    print("\nThe following are intentionally not part of Feature 1:")
    for item in OUT_OF_SCOPE_FEATURES:
        print(f"- {item}")


def show_final_summary(results: tuple[CheckResult, ...]) -> bool:
    """Print the ordered result table and return the overall result."""
    print_section(9, "Final summary")
    label_width = max(len("Check"), *(len(result.label) for result in results))
    print(f"{'Check':<{label_width}}  Result")
    print(f"{'-' * label_width}  ------")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        print(f"{result.label:<{label_width}}  {status}")

    demonstration_passed = all(result.passed for result in results)
    outcome = "PASS" if demonstration_passed else "FAIL"
    print(f"\nFEATURE 1 DEMONSTRATION RESULT: {outcome}")
    return demonstration_passed


# =============================================================================
# Command-line orchestration
# =============================================================================


def parse_arguments() -> argparse.Namespace:
    """Parse the optional manual presentation mode."""
    parser = argparse.ArgumentParser(
        description="Demonstrate the Skill Compass Feature 1 environment baseline."
    )
    parser.add_argument(
        "--step",
        action="store_true",
        help="pause after each major presentation section",
    )
    return parser.parse_args()


def main() -> int:
    """Run the demonstration and return zero only when every check passes."""
    arguments = parse_arguments()
    steps = StepController(enabled=arguments.step)

    print_banner()

    show_demonstration_context()
    steps.pause()

    required_files = check_required_files()
    steps.pause()

    python_environment = check_python_environment()
    steps.pause()

    project_metadata = check_project_metadata()
    steps.pause()

    package_import, package_version = check_package_import()
    steps.pause()

    pytest_available, ruff_available = check_installed_development_tools()
    steps.pause()

    show_manual_quality_commands()
    steps.pause()

    show_architecture_boundary()
    steps.pause()

    results = (
        required_files,
        python_environment,
        project_metadata,
        package_import,
        package_version,
        pytest_available,
        ruff_available,
    )
    demonstration_passed = show_final_summary(results)
    steps.pause()

    return 0 if demonstration_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
