"""Run and report the local Feature 6 seniority-classification demonstration.

This presentation service calls production classification and chart code; it
must not expose descriptions, invoke Apify, or implement seniority rules.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skill_compass.classification.errors import (
    SeniorityClassificationError,
    SeniorityConfigurationError,
)
from skill_compass.reporting.seniority_classification_charts import (
    SeniorityChartSummary,
    generate_seniority_classification_charts,
)
from skill_compass.schemas.classification import (
    JobSeniorityClassification,
    SeniorityClassificationEvidence,
)
from skill_compass.services.classify_seniority import (
    SeniorityClassificationCsvRunResult,
    process_seniority_classification,
)

# =============================================================================
# Demonstration configuration and execution
# =============================================================================


DEFAULT_SENIORITY_INPUT = Path("data/processed/national/cleaned_jobs.csv")
DEFAULT_SENIORITY_RULES = Path("profiles/data_analytics/seniority_rules.yaml")
DEFAULT_SENIORITY_OUTPUT = Path("data/processed/national/seniority_classification")
EXPECTED_SENIORITY_OUTPUTS = {
    "job_seniority_classifications.csv",
    "seniority_classification_evidence.csv",
    "seniority_distribution_summary.csv",
    "seniority_classification_quality.csv",
    "seniority_review_queue.csv",
}


@dataclass(frozen=True, slots=True)
class Feature6DemoResult:
    """Bundle production run evidence and generated demonstration charts."""

    run: SeniorityClassificationCsvRunResult
    charts: tuple[SeniorityChartSummary, SeniorityChartSummary]


def run_feature_6_demo(
    *,
    input_path: Path = DEFAULT_SENIORITY_INPUT,
    rules_path: Path = DEFAULT_SENIORITY_RULES,
    output_dir: Path = DEFAULT_SENIORITY_OUTPUT,
) -> Feature6DemoResult:
    """Classify an existing local cleaned file and generate both saved charts."""
    run = process_seniority_classification(
        input_path=input_path,
        rules_path=rules_path,
        output_dir=output_dir,
    )
    charts = generate_seniority_classification_charts(run.classification, output_dir)
    return Feature6DemoResult(run=run, charts=charts)


# =============================================================================
# Privacy-safe terminal rendering
# =============================================================================


def _masked_source_job_id(value: str) -> str:
    """Mask most of an external identifier in terminal output."""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _example_rows(result: Feature6DemoResult) -> tuple[JobSeniorityClassification, ...]:
    """Select up to five deterministic examples across distinct outcomes."""
    rows = result.run.classification.classifications
    selected: list[JobSeniorityClassification] = []
    for code in ("entry_level", "junior", "mid_level", "senior", "review"):
        match = next((row for row in rows if row.seniority_code == code), None)
        if match is not None:
            selected.append(match)
    if len(selected) < 5:
        unknown = next((row for row in rows if row.seniority_code == "unknown"), None)
        if unknown is not None:
            selected.append(unknown)
    return tuple(selected[:5])


def render_feature_6_demo(result: Feature6DemoResult) -> str:
    """Render distribution, evidence, quality, and calculated PASS/FAIL status."""
    run = result.run
    classification = run.classification
    quality = classification.quality
    jobs = {(job.source_code, job.source_job_id): job for job in run.cleaned_jobs}
    evidence_by_job: dict[tuple[str, str], list[SeniorityClassificationEvidence]] = (
        defaultdict(list)
    )
    for evidence in classification.evidence:
        evidence_by_job[(evidence.source_code, evidence.source_job_id)].append(evidence)

    lines = [
        "=" * 79,
        "SKILL COMPASS - FEATURE 6",
        "EXPLAINABLE SENIORITY CLASSIFICATION",
        "=" * 79,
        "",
        f"Input dataset:                    {run.input_path}",
        f"Input jobs:                       {classification.input_job_count:,}",
        "Approved level order:            Entry-level -> Junior -> Mid-level -> Senior",
        f"Seniority classifier version:     {classification.rules.seniority_classifier_version}",
        f"Seniority rules version:          {classification.rules.seniority_rules_version}",
        f"Seniority rules hash:             {classification.rules.seniority_rules_hash[:12]}...",
        "External API requests:             0",
        "Actor invocation:                  NO",
        "Database writes:                   NO",
        "",
        "SENIORITY DISTRIBUTION",
        "-" * 79,
    ]
    for row in classification.distribution:
        lines.append(
            f"{row.seniority_label:28} {row.job_count:>8,}  "
            f"{float(row.job_share):>7.2%}"
        )
    lines.extend(
        [
            "",
            "GRADUATE / EARLY-CAREER SUMMARY",
            "-" * 79,
            f"Entry-level + Junior jobs:        {quality.graduate_level_count:,}",
            f"Graduate-level rate:              {float(quality.graduate_level_rate):.2%}",
            "Graduate flag rule:              Entry-level and Junior only",
            "",
            "CONFIDENCE AND REVIEW",
            "-" * 79,
            f"High strength:                    {quality.high_confidence_count:,}",
            f"Medium strength:                  {quality.medium_confidence_count:,}",
            f"Low strength:                     {quality.low_confidence_count:,}",
            f"Unknown:                          {quality.unknown_count:,}",
            f"Review:                           {quality.review_count:,}",
            f"Review rate:                      {float(quality.review_rate):.2%}",
            f"Conflicting evidence:             {quality.jobs_with_conflicting_evidence:,}",
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
                f"  Seniority: {row.seniority_label}",
                f"  Rank: {row.seniority_rank if row.seniority_rank is not None else '-'}",
                f"  Graduate-level: {'YES' if row.graduate_level_flag else 'NO'}",
                f"  Strength: {float(row.seniority_confidence_score):.4f}",
                f"  Conflict: {'YES' if row.seniority_conflict_flag else 'NO'}",
                f"  Reason: {row.seniority_reason}",
            ]
        )
        for evidence in evidence_by_job[(row.source_code, row.source_job_id)][:4]:
            experience = ""
            if evidence.experience_years_min is not None:
                maximum = evidence.experience_years_max
                range_label = "+" if maximum is None else f"-{maximum}"
                experience = f" / years={evidence.experience_years_min}{range_label}"
            lines.append(
                "  Evidence: "
                f"{evidence.seniority_code} / {evidence.evidence_section} / "
                f"{evidence.evidence_term} ({evidence.evidence_weight}){experience}"
            )
        lines.append("")

    output_names = {item.path.name for item in run.output_files}
    output_passed = output_names == EXPECTED_SENIORITY_OUTPUTS and all(
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
            f"Jobs without seniority evidence:  {quality.jobs_without_seniority_evidence:,}",
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
            "FEATURE 6 DEMONSTRATION RESULT",
            "-" * 79,
            f"Overall result:                    {'PASS' if passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


def run_feature_6_demo_command(
    *,
    input_path: Path = DEFAULT_SENIORITY_INPUT,
    rules_path: Path = DEFAULT_SENIORITY_RULES,
    output_dir: Path = DEFAULT_SENIORITY_OUTPUT,
    output: Callable[[str], None] = print,
) -> int:
    """Run the local demonstration and map controlled failures to an exit code."""
    try:
        result = run_feature_6_demo(
            input_path=input_path,
            rules_path=rules_path,
            output_dir=output_dir,
        )
    except (
        SeniorityClassificationError,
        SeniorityConfigurationError,
        OSError,
        ValueError,
    ) as error:
        output(f"Feature 6 demonstration failed safely: {error}")
        output("No external API request occurred. Actor invocation: NO.")
        return 1
    output(render_feature_6_demo(result))
    return 0
