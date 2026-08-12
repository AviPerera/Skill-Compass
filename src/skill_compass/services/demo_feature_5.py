"""Run and report the local Feature 5 role-classification demonstration.

This presentation service calls production classification and chart code; it
must not expose descriptions, invoke Apify, or implement classification rules.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skill_compass.classification.errors import (
    RoleClassificationError,
    RoleConfigurationError,
)
from skill_compass.reporting.role_classification_charts import (
    RoleChartSummary,
    generate_role_classification_charts,
)
from skill_compass.schemas.classification import (
    JobRoleClassification,
    RoleClassificationEvidence,
)
from skill_compass.services.classify_roles import (
    RoleClassificationCsvRunResult,
    process_role_classification,
)

# =============================================================================
# Demonstration configuration and execution
# =============================================================================


DEFAULT_ROLE_INPUT = Path("data/processed/national/cleaned_jobs.csv")
DEFAULT_ROLE_RULES = Path("profiles/data_analytics/role_rules.yaml")
DEFAULT_ROLE_OUTPUT = Path("data/processed/national/role_classification")
EXPECTED_ROLE_OUTPUTS = {
    "job_role_classifications.csv",
    "role_classification_evidence.csv",
    "role_distribution_summary.csv",
    "role_classification_quality.csv",
    "review_queue.csv",
}


@dataclass(frozen=True, slots=True)
class Feature5DemoResult:
    """Bundle production run evidence and generated demonstration charts."""

    run: RoleClassificationCsvRunResult
    charts: tuple[RoleChartSummary, RoleChartSummary]


def run_feature_5_demo(
    *,
    input_path: Path = DEFAULT_ROLE_INPUT,
    rules_path: Path = DEFAULT_ROLE_RULES,
    output_dir: Path = DEFAULT_ROLE_OUTPUT,
) -> Feature5DemoResult:
    """Classify an existing local cleaned file and generate both saved charts."""
    run = process_role_classification(
        input_path=input_path,
        rules_path=rules_path,
        output_dir=output_dir,
    )
    charts = generate_role_classification_charts(run.classification, output_dir)
    return Feature5DemoResult(run=run, charts=charts)


# =============================================================================
# Privacy-safe terminal rendering
# =============================================================================


def _masked_source_job_id(value: str) -> str:
    """Mask most of an external identifier in terminal demonstration output."""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _example_rows(result: Feature5DemoResult) -> tuple[JobRoleClassification, ...]:
    """Select up to five deterministic examples, including Review when present."""
    rows = result.run.classification.classifications
    selected: list[JobRoleClassification] = []
    seen_codes: set[str] = set()
    for row in rows:
        if (
            row.role_group_code in {"other", "review"}
            or row.role_group_code in seen_codes
        ):
            continue
        selected.append(row)
        seen_codes.add(row.role_group_code)
        if len(selected) == 4:
            break
    review = next((row for row in rows if row.role_review_flag), None)
    if review is not None:
        selected.append(review)
    for row in rows:
        if len(selected) >= 5:
            break
        if row not in selected:
            selected.append(row)
    return tuple(selected[:5])


def render_feature_5_demo(result: Feature5DemoResult) -> str:
    """Render calculated distribution, confidence, evidence, and PASS/FAIL status."""
    run = result.run
    classification = run.classification
    quality = classification.quality
    jobs = {(job.source_code, job.source_job_id): job for job in run.cleaned_jobs}
    evidence_by_job: dict[tuple[str, str], list[RoleClassificationEvidence]] = (
        defaultdict(list)
    )
    for evidence in classification.evidence:
        evidence_by_job[(evidence.source_code, evidence.source_job_id)].append(evidence)

    lines = [
        "=" * 79,
        "SKILL COMPASS - FEATURE 5",
        "EXPLAINABLE ROLE CLASSIFICATION",
        "=" * 79,
        "",
        f"Input dataset:                    {run.input_path}",
        f"Input jobs:                       {classification.input_job_count:,}",
        f"Role classifier version:          {classification.rules.role_classifier_version}",
        f"Role rules version:               {classification.rules.role_rules_version}",
        f"Role rules hash:                  {classification.rules.role_rules_hash[:12]}...",
        "External API requests:             0",
        "",
        "ROLE DISTRIBUTION",
        "-" * 79,
    ]
    for row in classification.distribution:
        lines.append(
            f"{row.role_group_label:28} {row.job_count:>8,}  "
            f"{float(row.job_share):>7.2%}"
        )
    lines.extend(
        [
            "",
            "CONFIDENCE AND REVIEW",
            "-" * 79,
            f"High strength:                    {quality.high_confidence_count:,}",
            f"Medium strength:                  {quality.medium_confidence_count:,}",
            f"Low strength:                     {quality.low_confidence_count:,}",
            f"Other:                            {quality.other_count:,}",
            f"Review:                           {quality.review_count:,}",
            f"Review rate:                      {float(quality.review_rate):.2%}",
            "",
            "EXPLAINABLE EXAMPLES",
            "-" * 79,
        ]
    )
    for position, row in enumerate(_example_rows(result), start=1):
        job = jobs[(row.source_code, row.source_job_id)]
        lines.extend(
            [
                f"Example {position}",
                f"  Source job ID: {_masked_source_job_id(row.source_job_id)}",
                f"  Title: {' '.join(job.title_clean.split())[:120]}",
                f"  Role: {row.role_group_label}",
                f"  Strength: {float(row.role_confidence_score):.4f}",
                f"  Reason: {row.role_reason}",
            ]
        )
        for evidence in evidence_by_job[(row.source_code, row.source_job_id)][:4]:
            lines.append(
                "  Evidence: "
                f"{evidence.role_group_code} / {evidence.evidence_section} / "
                f"{evidence.evidence_term} ({evidence.evidence_weight})"
            )
        lines.append("")

    output_names = {item.path.name for item in run.output_files}
    output_passed = output_names == EXPECTED_ROLE_OUTPUTS and all(
        item.path.is_file() for item in run.output_files
    )
    charts_passed = all(
        chart.path.is_file() and chart.path.stat().st_size > 0
        for chart in result.charts
    )
    passed = classification.reconciliation_passed and output_passed and charts_passed
    lines.extend(
        [
            "QUALITY SUMMARY",
            "-" * 79,
            f"Classification reconciliation:   {'PASS' if classification.reconciliation_passed else 'FAIL'}",
            f"CSV output validation:            {'PASS' if output_passed else 'FAIL'}",
            f"Chart validation:                 {'PASS' if charts_passed else 'FAIL'}",
            f"Missing titles:                   {quality.missing_title_count:,}",
            f"Missing descriptions:             {quality.missing_description_count:,}",
            f"Denominator: {quality.denominator_definition}",
            "",
            "GENERATED OUTPUTS",
            "-" * 79,
        ]
    )
    lines.extend(f"{item.path}: {item.row_count:,} rows" for item in run.output_files)
    lines.extend(f"{chart.path}: {chart.title}" for chart in result.charts)
    lines.extend(
        [
            "",
            "FEATURE 5 DEMONSTRATION RESULT",
            "-" * 79,
            f"Overall result:                    {'PASS' if passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


def run_feature_5_demo_command(
    *,
    input_path: Path = DEFAULT_ROLE_INPUT,
    rules_path: Path = DEFAULT_ROLE_RULES,
    output_dir: Path = DEFAULT_ROLE_OUTPUT,
    output: Callable[[str], None] = print,
) -> int:
    """Run the local demonstration and map controlled failures to an exit code."""
    try:
        result = run_feature_5_demo(
            input_path=input_path,
            rules_path=rules_path,
            output_dir=output_dir,
        )
    except (
        RoleClassificationError,
        RoleConfigurationError,
        OSError,
        ValueError,
    ) as error:
        output(f"Feature 5 demonstration failed safely: {error}")
        output("No external API request occurred.")
        return 1
    output(render_feature_5_demo(result))
    return 0
