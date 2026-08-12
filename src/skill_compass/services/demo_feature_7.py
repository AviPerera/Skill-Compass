"""Run and report the local Feature 7 profile-relevance demonstration.

This presentation service calls production classification and chart code. It
must not expose descriptions, invoke external services, or implement rules.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from skill_compass.classification.errors import RelevanceClassificationError
from skill_compass.reporting.profile_relevance_charts import (
    ProfileRelevanceChartSummary,
    generate_profile_relevance_charts,
)
from skill_compass.schemas.classification import ProfileRelevanceEvidence
from skill_compass.services.classify_profile_relevance import (
    ProfileRelevanceCsvRunResult,
    process_profile_relevance,
)

# =============================================================================
# Demonstration configuration and execution
# =============================================================================


DEFAULT_RELEVANCE_INPUT = Path("data/processed/national")
DEFAULT_RELEVANCE_RULES = Path("profiles/data_analytics/relevance_rules.yaml")
DEFAULT_RELEVANCE_OUTPUT = Path("data/processed/national/profile_relevance")
EXPECTED_RELEVANCE_OUTPUTS = {
    "job_profile_relevance.csv",
    "profile_relevance_evidence.csv",
    "profile_relevance_summary.csv",
    "profile_relevance_review_queue.csv",
    "profile_relevance_diagnostics.csv",
}


@dataclass(frozen=True, slots=True)
class Feature7DemoResult:
    """Bundle production run evidence and generated demonstration charts."""

    run: ProfileRelevanceCsvRunResult
    charts: tuple[ProfileRelevanceChartSummary, ProfileRelevanceChartSummary]


def run_feature_7_demo(
    *,
    input_dir: Path = DEFAULT_RELEVANCE_INPUT,
    rules_path: Path = DEFAULT_RELEVANCE_RULES,
    output_dir: Path = DEFAULT_RELEVANCE_OUTPUT,
) -> Feature7DemoResult:
    """Classify existing local processed outputs and generate both charts."""
    run = process_profile_relevance(
        input_dir=input_dir,
        rules_path=rules_path,
        output_dir=output_dir,
    )
    charts = generate_profile_relevance_charts(run.classification, output_dir)
    return Feature7DemoResult(run=run, charts=charts)


# =============================================================================
# Privacy-safe terminal rendering
# =============================================================================


def _masked_source_job_id(value: str) -> str:
    """Mask most of an external identifier in terminal output."""
    return "***" if len(value) <= 4 else f"{value[:2]}***{value[-2:]}"


def _example_indices(result: Feature7DemoResult, status: str) -> tuple[int, ...]:
    """Select at most two deterministic examples for one final state."""
    return tuple(
        index
        for index, row in enumerate(result.run.classification.classifications)
        if row.relevance_status == status
    )[:2]


def render_feature_7_demo(result: Feature7DemoResult) -> str:
    """Render calculated decisions, interactions, examples, and PASS/FAIL."""
    run = result.run
    classification = run.classification
    summary = classification.summary
    evidence_by_job: dict[tuple[str, str], list[ProfileRelevanceEvidence]] = (
        defaultdict(list)
    )
    for evidence in classification.evidence:
        evidence_by_job[(evidence.source_code, evidence.source_job_id)].append(evidence)
    review_reasons = Counter(
        row.relevance_reason_code
        for row in classification.classifications
        if row.relevance_review_flag
    )
    role_interaction = Counter(
        (diagnostic.role_group, diagnostic.relevance_status)
        for diagnostic in classification.diagnostics
    )
    unknown_seniority = Counter(
        diagnostic.relevance_status
        for diagnostic in classification.diagnostics
        if diagnostic.seniority_level == "unknown"
    )

    lines = [
        "=" * 79,
        "SKILL COMPASS - FEATURE 7",
        "EXPLAINABLE PROFILE RELEVANCE CLASSIFICATION",
        "=" * 79,
        "",
        "Purpose: gate canonical jobs into Included, Excluded, or Review.",
        f"Input dataset:                    {run.input_dir}",
        f"Input jobs:                       {summary.total_classifier_input:,}",
        f"Profile:                          {classification.rules.profile_code}",
        f"Classifier version:               {classification.rules.relevance_classifier_version}",
        f"Rules version:                    {classification.rules.relevance_rules_version}",
        f"Rules hash:                       {classification.rules.relevance_rules_hash[:12]}...",
        "External API requests:             0",
        "",
        "PROFILE RELEVANCE DISTRIBUTION",
        "-" * 79,
        f"Included:                         {summary.included_count:>8,}  {float(summary.included_rate):>7.2%}",
        f"Excluded:                         {summary.excluded_count:>8,}  {float(summary.excluded_rate):>7.2%}",
        f"Review:                           {summary.review_count:>8,}  {float(summary.review_rate):>7.2%}",
        "Baseline Feature 7 review rate:    unavailable (first governed run)",
        "",
        "EVIDENCE COVERAGE",
        "-" * 79,
        f"Role-supported decisions:         {summary.role_supported_decision_count:,}",
        f"Multi-family decisions:           {summary.multi_evidence_decision_count:,}",
        f"Missing descriptions:             {summary.missing_description_count:,}",
        f"Insufficient evidence:            {summary.insufficient_evidence_count:,}",
        f"Conflicting evidence:             {summary.conflicting_evidence_count:,}",
        "",
        "TOP REVIEW REASONS",
        "-" * 79,
    ]
    if review_reasons:
        lines.extend(
            f"{reason:36} {count:>8,}"
            for reason, count in review_reasons.most_common(8)
        )
    else:
        lines.append("No Review cases")

    lines.extend(["", "BOUNDED EXAMPLES", "-" * 79])
    for status in ("included", "excluded", "review"):
        lines.append(status.upper())
        for index in _example_indices(result, status):
            row = classification.classifications[index]
            job = run.cleaned_jobs[index]
            lines.append(
                f"  {_masked_source_job_id(row.source_job_id)} | "
                f"{' '.join(job.title_clean.split())[:100]} | "
                f"{row.relevance_score} | {row.relevance_reason_code}"
            )
            for evidence in evidence_by_job[(row.source_code, row.source_job_id)][:3]:
                lines.append(
                    f"    {evidence.evidence_family}: {evidence.evidence_term} "
                    f"({evidence.evidence_weight})"
                )

    lines.extend(["", "ROLE / RELEVANCE INTERACTION", "-" * 79])
    for (role, status), count in sorted(
        role_interaction.items(), key=lambda item: (item[0][0], item[0][1])
    ):
        lines.append(f"{role:28} {status:10} {count:>8,}")
    lines.extend(
        [
            "",
            "SENIORITY-UNKNOWN / RELEVANCE INTERACTION",
            "-" * 79,
            f"Unknown seniority + Included:     {unknown_seniority['included']:,}",
            f"Unknown seniority + Excluded:     {unknown_seniority['excluded']:,}",
            f"Unknown seniority + Review:       {unknown_seniority['review']:,}",
        ]
    )

    output_names = {item.path.name for item in run.output_files}
    outputs_passed = output_names == EXPECTED_RELEVANCE_OUTPUTS and all(
        item.path.is_file() for item in run.output_files
    )
    charts_passed = all(
        chart.path.is_file() and chart.path.stat().st_size > 0
        for chart in result.charts
    )
    passed = classification.reconciliation_passed and outputs_passed and charts_passed
    lines.extend(
        [
            "",
            "QUALITY SUMMARY",
            "-" * 79,
            f"Classification reconciliation:   {'PASS' if classification.reconciliation_passed else 'FAIL'}",
            f"CSV output validation:            {'PASS' if outputs_passed else 'FAIL'}",
            f"Chart validation:                 {'PASS' if charts_passed else 'FAIL'}",
            "Accuracy claimed:                 NO - human labels not yet available",
            f"Denominator: {summary.denominator_definition}",
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
            "FEATURE 7 DEMONSTRATION RESULT",
            "-" * 79,
            f"Overall result:                    {'PASS' if passed else 'FAIL'}",
        ]
    )
    return "\n".join(lines)


def run_feature_7_demo_command(
    *,
    input_dir: Path = DEFAULT_RELEVANCE_INPUT,
    rules_path: Path = DEFAULT_RELEVANCE_RULES,
    output_dir: Path = DEFAULT_RELEVANCE_OUTPUT,
    output: Callable[[str], None] = print,
) -> int:
    """Run the local demonstration and map controlled failures to an exit code."""
    try:
        result = run_feature_7_demo(
            input_dir=input_dir, rules_path=rules_path, output_dir=output_dir
        )
    except (RelevanceClassificationError, OSError, ValueError) as error:
        output(f"Feature 7 demonstration failed safely: {error}")
        output("No external API request occurred.")
        return 1
    output(render_feature_7_demo(result))
    return 0
