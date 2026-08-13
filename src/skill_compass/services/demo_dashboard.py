"""Run and report the complete static dashboard visual demonstration.

This presentation service coordinates Feature 8 and reporting code. It must not
implement analytical measures, invoke external services, or build Power BI files.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skill_compass.reporting.dashboard_visuals import (
    DashboardVisualSummary,
    generate_dashboard_visuals,
)
from skill_compass.services.build_analytics import (
    AnalyticsCsvRunResult,
    process_analytics,
)

# =============================================================================
# Conventional local paths and result contract
# =============================================================================


DEFAULT_INPUT_DIR = Path("data/processed/national")
DEFAULT_OUTPUT_DIR = Path("data/processed/national/dashboard_demo")
DEFAULT_PROFILE = Path("profiles/data_analytics/profile.yaml")
DEFAULT_DICTIONARY = Path("profiles/data_analytics/requirements.csv")
DEFAULT_ROLE_RULES = Path("profiles/data_analytics/role_rules.yaml")
DEFAULT_SENIORITY_RULES = Path("profiles/data_analytics/seniority_rules.yaml")
DEFAULT_REFERENCE_WORKBOOK = Path(
    "powerbi/reference/Skill_Compass_Final_Synthetic_PowerBI_Dataset_100_Jobs.xlsx"
)
EXPECTED_VISUAL_COUNT = 22


@dataclass(frozen=True, slots=True)
class DashboardDemoResult:
    """Bundle analytics evidence and the complete visual inventory."""

    analytics_run: AnalyticsCsvRunResult
    visuals: tuple[DashboardVisualSummary, ...]
    output_dir: Path


# =============================================================================
# Demonstration execution and privacy-safe terminal output
# =============================================================================


def run_dashboard_demo(
    *,
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    profile_path: Path = DEFAULT_PROFILE,
    dictionary_path: Path = DEFAULT_DICTIONARY,
    role_rules_path: Path = DEFAULT_ROLE_RULES,
    seniority_rules_path: Path = DEFAULT_SENIORITY_RULES,
    reference_workbook: Path = DEFAULT_REFERENCE_WORKBOOK,
) -> DashboardDemoResult:
    """Build analytics and generate every approved static visual artifact."""
    analytics_run = process_analytics(
        input_dir=input_dir,
        profile_path=profile_path,
        dictionary_path=dictionary_path,
        role_rules_path=role_rules_path,
        seniority_rules_path=seniority_rules_path,
        output_dir=output_dir / "analytics",
    )
    visuals = generate_dashboard_visuals(
        analytics_run.analytics,
        output_dir / "visuals",
        reference_workbook,
    )
    return DashboardDemoResult(
        analytics_run=analytics_run,
        visuals=visuals,
        output_dir=output_dir,
    )


def render_dashboard_demo(result: DashboardDemoResult) -> str:
    """Render a concise inventory and explicit provenance boundary."""
    analytics = result.analytics_run.analytics
    page_counts = {
        page: sum(visual.page_number == page for visual in result.visuals)
        for page in range(1, 7)
    }
    files_pass = all(
        visual.path.is_file() and visual.path.stat().st_size > 0
        for visual in result.visuals
    )
    manifest_pass = (
        result.output_dir / "visuals/dashboard_visual_manifest.json"
    ).is_file()
    passed = (
        analytics.reconciliation_passed
        and len(result.visuals) == EXPECTED_VISUAL_COUNT
        and files_pass
        and manifest_pass
    )
    lines = [
        "=" * 79,
        "SKILL COMPASS - FEATURE 8 ANALYTICS AND DASHBOARD VISUAL DEMO",
        "=" * 79,
        "",
        f"Classifier input jobs:            {analytics.classifier_input_job_count:,}",
        f"Included dashboard jobs:          {analytics.included_job_count:,}",
        f"Job-skill facts:                  {len(analytics.job_skill_facts):,}",
        f"Skill combinations:               {len(analytics.skill_combinations):,}",
        "External API requests:             0",
        "Power BI files modified:           NO",
        "",
        "VISUAL INVENTORY",
        "-" * 79,
    ]
    page_names = {
        1: "Executive Summary",
        2: "Skills Analysis",
        3: "Role Analysis",
        4: "Location Insights",
        5: "Graduate Roadmap",
        6: "Methodology",
    }
    lines.extend(
        f"Page {page} - {page_names[page]:22} {page_counts[page]:>2} artifacts"
        for page in range(1, 7)
    )
    lines.extend(
        [
            "",
            "PROVENANCE",
            "-" * 79,
            "National pipeline data: pages 1-4, combinations on page 5",
            "Synthetic/provisional metadata: priority matrix and roadmap stages only",
            "Implemented project workflow: methodology process flow",
            "",
            "QUALITY",
            "-" * 79,
            f"Analytics reconciliation:         {'PASS' if analytics.reconciliation_passed else 'FAIL'}",
            f"Expected visual count (22):       {'PASS' if len(result.visuals) == EXPECTED_VISUAL_COUNT else 'FAIL'}",
            f"PNG file validation:              {'PASS' if files_pass else 'FAIL'}",
            f"Manifest validation:              {'PASS' if manifest_pass else 'FAIL'}",
            f"Output directory:                 {result.output_dir}",
            "",
            "FEATURE 8 DASHBOARD DEMONSTRATION RESULT",
            "-" * 79,
            f"Overall result:                    {'PASS' if passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


def run_dashboard_demo_command(
    *,
    input_dir: Path = DEFAULT_INPUT_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    profile_path: Path = DEFAULT_PROFILE,
    dictionary_path: Path = DEFAULT_DICTIONARY,
    role_rules_path: Path = DEFAULT_ROLE_RULES,
    seniority_rules_path: Path = DEFAULT_SENIORITY_RULES,
    reference_workbook: Path = DEFAULT_REFERENCE_WORKBOOK,
    output: Callable[[str], None] = print,
) -> int:
    """Run the local demo and map controlled failures to a process exit code."""
    try:
        result = run_dashboard_demo(
            input_dir=input_dir,
            output_dir=output_dir,
            profile_path=profile_path,
            dictionary_path=dictionary_path,
            role_rules_path=role_rules_path,
            seniority_rules_path=seniority_rules_path,
            reference_workbook=reference_workbook,
        )
    except (OSError, ValueError) as error:
        output(f"Feature 8 dashboard demonstration failed safely: {error}")
        output("No external API request occurred.")
        return 1
    output(render_dashboard_demo(result))
    return 0
