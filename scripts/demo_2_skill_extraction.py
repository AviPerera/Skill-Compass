"""Present the temporary Demo 2 requirement and skill extraction workflow.

This manual presentation layer calls reusable Feature 3 services and must not
regenerate Feature 2 data, implement matching, expose full text, or act as a CLI.
"""

from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from skill_compass.extraction.errors import (
    ExtractionConfigurationError,
    ExtractionInputError,
    ExtractionReconciliationError,
)
from skill_compass.reporting.skill_extraction_charts import (
    ChartSummary,
    generate_extraction_charts,
)
from skill_compass.schemas.extraction import (
    ExtractionRunResult,
    JobRequirementMatch,
    RequirementEvidence,
    SkillDemandSummary,
)
from skill_compass.services.extract_requirements import (
    FEATURE_2_CLEANING_COMMAND,
    ExtractionCsvRunResult,
    process_cleaned_csv,
)

# =============================================================================
# Presentation configuration and arguments
# =============================================================================


BANNER_WIDTH = 79
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("data/processed/demo_2/cleaned_jobs.csv")
DEFAULT_PROFILE = Path("profiles/data_analytics/profile.yaml")
DEFAULT_DICTIONARY = Path("profiles/data_analytics/requirements.csv")
DEFAULT_OUTPUT_DIR = Path("data/processed/demo_2/skill_extraction")
EXPECTED_OUTPUT_NAMES = {
    "job_requirement_matches.csv",
    "requirement_evidence.csv",
    "job_extraction_summary.csv",
    "skill_demand_summary.csv",
    "extraction_quality_summary.csv",
}


@dataclass(slots=True)
class StepController:
    """Pause after major sections only when interactive step mode is requested."""

    enabled: bool

    def pause(self) -> None:
        """Wait for Enter and disable later pauses if input is unavailable."""
        if not self.enabled:
            return
        try:
            input("\nPress Enter to continue...")
        except EOFError:
            print("\nInteractive input is unavailable; continuing without pauses.")
            self.enabled = False


def positive_integer(value: str) -> int:
    """Parse a strictly positive presentation count."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse optional paths, presentation sizes, plot display, and step mode."""
    parser = argparse.ArgumentParser(
        description="Demonstrate deterministic requirement and skill extraction."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--dictionary", type=Path, default=DEFAULT_DICTIONARY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-size", type=positive_integer, default=3)
    parser.add_argument("--top-skills", type=positive_integer, default=15)
    parser.add_argument(
        "--show-plots",
        action="store_true",
        help="display both plot windows after saving the PNG files",
    )
    parser.add_argument(
        "--step", action="store_true", help="pause after each major section"
    )
    return parser.parse_args(argv)


def repository_path(path: Path) -> Path:
    """Resolve relative demonstration paths from the repository root."""
    return path if path.is_absolute() else REPOSITORY_ROOT / path


# =============================================================================
# Plain terminal helpers
# =============================================================================


def print_banner() -> None:
    """Print the approved two-line Feature 3 Demo 2 title."""
    print("=" * BANNER_WIDTH)
    print("SKILL COMPASS — DEMO 2")
    print("REQUIREMENT AND SKILL EXTRACTION")
    print("=" * BANNER_WIDTH)


def print_section(number: int, title: str) -> None:
    """Print one consistently formatted numbered section heading."""
    heading = f"{number}. {title}"
    print(f"\n{heading}")
    print("-" * len(heading))


def print_status(passed: bool, message: str) -> None:
    """Print one deterministic PASS or FAIL marker."""
    print(f"[{'PASS' if passed else 'FAIL'}] {message}")


def truncate(value: str | None, limit: int = 96) -> str:
    """Keep safe presentation values bounded and single-line."""
    if not value:
        return "<none>"
    single_line = " ".join(value.split())
    return (
        single_line if len(single_line) <= limit else f"{single_line[: limit - 3]}..."
    )


def masked_source_job_id(value: str) -> str:
    """Mask most characters of an external job identifier."""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def quality_value(result: ExtractionRunResult, name: str) -> str:
    """Return one unique stable extraction quality metric value."""
    return next(
        metric.metric_value
        for metric in result.quality_metrics
        if metric.metric_name == name
    )


# =============================================================================
# Demonstration terminal sections
# =============================================================================


def show_context(input_path: Path, output_dir: Path) -> None:
    """Present the Stage 2 capability and current adapter boundary."""
    print_section(2, "Demonstration context")
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print("Current implementation: Phase 2, Stage 2")
    print("Capability: Deterministic dictionary-based requirement extraction.")
    print("Architecture direction: Cleaned CSV adapter now; PostgreSQL adapter later.")
    print(f"Repository root: {REPOSITORY_ROOT}")
    print(f"Current date and time: {current_time}")
    print(f"Cleaned input path: {input_path}")
    print(f"Extraction output path: {output_dir}")


def show_feature_2_prerequisite(run: ExtractionCsvRunResult) -> None:
    """Confirm the typed cleaned input and retained Feature 2 versions."""
    print_section(3, "Feature 2 prerequisite")
    extraction = run.extraction
    print_status(run.input_path.is_file(), "Cleaned Feature 2 input exists")
    print(f"Cleaned row count: {extraction.input_cleaned_jobs}")
    print(f"Analytically eligible row count: {extraction.analytically_eligible_jobs}")
    versions = sorted({job.canonical_schema_version for job in run.cleaned_jobs})
    print(f"Canonical schema version: {', '.join(versions) or '<none>'}")
    print_status(True, "Feature 3 reads typed cleaned fields, not raw Apify fields")


def show_profile_and_dictionary(result: ExtractionRunResult) -> None:
    """Present governed configuration versions, hashes, counts, and weights."""
    print_section(4, "Profile and dictionary")
    profile = result.profile
    dictionary = result.requirement_dictionary
    print(f"Profile code: {profile.profile_code}")
    print(f"Profile version: {profile.profile_version}")
    print(f"Dictionary version: {dictionary.dictionary_version}")
    print(f"Extractor version: {profile.extractor_version}")
    print(
        f"Extraction output schema version: {profile.extraction_output_schema_version}"
    )
    print(f"Profile hash: {profile.profile_hash[:12]}...")
    print(f"Dictionary hash: {dictionary.dictionary_hash[:12]}...")
    print(f"Extractor configuration hash: {result.extractor_config_hash[:12]}...")
    print(f"Active requirement count: {len(dictionary.requirements)}")
    print(f"Active alias count: {len(dictionary.active_aliases)}")
    print(f"Category count: {len(dictionary.category_codes)}")
    print("Configured section weights:")
    for section_name, weight in profile.section_weights.items():
        print(f"- {section_name}: {weight}")
    match_types = sorted({alias.match_type for alias in dictionary.active_aliases})
    print(f"Enabled match types: {', '.join(match_types)}")


def show_false_positive_controls() -> None:
    """Describe the deterministic controls applied by the reusable matcher."""
    print_section(5, "False-positive controls")
    print("- Word boundaries protect short tokens such as R and SQL.")
    print("- Multi-word aliases are matched as complete normalised phrases.")
    print("- Longest valid spans win deterministic overlap conflicts.")
    print(
        "- Title, summary, bullets and description remain separate evidence sections."
    )
    print("- Conservative negative context is retained as suppressed evidence.")
    print("- URLs, companies, contacts, IDs, headers and quality flags are excluded.")


def show_extraction_results(result: ExtractionRunResult) -> None:
    """Present complete extraction coverage and distribution counts."""
    print_section(6, "Extraction results")
    print(f"Cleaned input jobs: {result.input_cleaned_jobs}")
    print(f"Eligible jobs: {result.analytically_eligible_jobs}")
    print(f"Ineligible / skipped jobs: {result.skipped_jobs}")
    print(
        "Jobs with at least one requirement: "
        f"{quality_value(result, 'jobs_with_at_least_one_requirement')}"
    )
    print(
        f"Jobs with no requirements: {quality_value(result, 'jobs_with_no_requirements')}"
    )
    print(f"Jobs requiring review: {quality_value(result, 'jobs_requiring_review')}")
    print(f"Distinct job-requirement matches: {len(result.job_requirement_matches)}")
    print(f"Total evidence rows: {len(result.evidence)}")
    print(
        "Average skills per eligible job: "
        f"{quality_value(result, 'average_requirements_per_eligible_job')}"
    )
    print(
        "Median skills per eligible job: "
        f"{quality_value(result, 'median_requirements_per_eligible_job')}"
    )
    print(
        "Minimum / maximum skills per eligible job: "
        f"{quality_value(result, 'minimum_requirements_per_eligible_job')} / "
        f"{quality_value(result, 'maximum_requirements_per_eligible_job')}"
    )


def show_confidence_results(result: ExtractionRunResult) -> None:
    """Present stable match-confidence and negative-context counts."""
    print_section(7, "Confidence results")
    print(
        f"High-confidence matches: {quality_value(result, 'high_confidence_matches')}"
    )
    print(
        f"Medium-confidence matches: {quality_value(result, 'medium_confidence_matches')}"
    )
    print(f"Low-confidence matches: {quality_value(result, 'low_confidence_matches')}")
    print(f"Review matches: {quality_value(result, 'review_matches')}")
    print(
        f"Suppressed negative-context count: {result.suppressed_negative_context_count}"
    )


def confidence_summary(row: SkillDemandSummary) -> str:
    """Format compact high/medium/low/review job counts for one skill."""
    return (
        f"H{row.high_confidence_job_count}/M{row.medium_confidence_job_count}/"
        f"L{row.low_confidence_job_count}/R{row.review_job_count}"
    )


def show_top_skills(result: ExtractionRunResult, top_skills: int) -> None:
    """Print an actual ranked skill table using distinct eligible-job demand."""
    print_section(8, "Top skill results")
    rows = result.skill_demand[:top_skills]
    print(
        "Rank  Skill                         Category                  Jobs   Demand   Confidence"
    )
    print(
        "----  ----------------------------  ------------------------  -----  -------  ----------"
    )
    for row in rows:
        print(
            f"{row.rank_overall:>4}  {truncate(row.requirement_name, 28):<28}  "
            f"{truncate(row.category_name, 24):<24}  {row.matched_job_count:>5}  "
            f"{float(row.demand_rate):>6.1%}  {confidence_summary(row)}"
        )


def grouped_matches(
    result: ExtractionRunResult,
) -> dict[tuple[str, str], list[JobRequirementMatch]]:
    """Group stable job matches for bounded terminal previews."""
    grouped: dict[tuple[str, str], list[JobRequirementMatch]] = defaultdict(list)
    for match in result.job_requirement_matches:
        grouped[(match.source_code, match.source_job_id)].append(match)
    return grouped


def grouped_accepted_evidence(
    result: ExtractionRunResult,
) -> dict[tuple[str, str], list[RequirementEvidence]]:
    """Group only accepted/review evidence for bounded terminal previews."""
    grouped: dict[tuple[str, str], list[RequirementEvidence]] = defaultdict(list)
    for evidence in result.evidence:
        if evidence.evidence_status in {"accepted", "review"}:
            grouped[(evidence.source_code, evidence.source_job_id)].append(evidence)
    return grouped


def show_safe_evidence_previews(run: ExtractionCsvRunResult, sample_size: int) -> None:
    """Show bounded identifiers, titles, matches, snippets, and quality flags."""
    print_section(9, "Safe evidence previews")
    result = run.extraction
    jobs = {(job.source_code, job.source_job_id): job for job in run.cleaned_jobs}
    matches = grouped_matches(result)
    evidence = grouped_accepted_evidence(result)
    preview_keys = [key for key in jobs if matches.get(key)][:sample_size]
    if not preview_keys:
        print("No matched jobs are available for a safe evidence preview.")
        return

    summary_lookup = {
        (summary.source_code, summary.source_job_id): summary
        for summary in result.job_summaries
    }
    for position, key in enumerate(preview_keys, start=1):
        job = jobs[key]
        job_matches = matches[key]
        summary = summary_lookup[key]
        print(f"\nExample {position}")
        print(f"  Source job ID: {masked_source_job_id(job.source_job_id)}")
        print(f"  Title: {truncate(job.title_clean)}")
        print(f"  Distinct detected skills: {summary.distinct_skill_count}")
        print(
            "  Requirements: "
            + truncate(", ".join(match.requirement_name for match in job_matches), 140)
        )
        print(
            "  Confidence: "
            + truncate(
                ", ".join(
                    f"{match.requirement_name}={match.confidence_level}"
                    for match in job_matches
                ),
                140,
            )
        )
        for row in evidence[key][:3]:
            print(
                f"  Evidence ({row.section_name}; alias={row.alias_text}): "
                f"{truncate(row.evidence_snippet, 170)}"
            )
        flags = ", ".join(summary.extraction_quality_flags) or "<none>"
        print(f"  Quality flags: {truncate(flags)}")


def show_generated_outputs(run: ExtractionCsvRunResult) -> None:
    """Print all approved generated CSV paths and data-row counts."""
    print_section(10, "Generated output files")
    for output in run.output_files:
        print(f"{output.path}: {output.row_count} rows")


def show_graph_generation(charts: tuple[ChartSummary, ...]) -> None:
    """Print chart paths, source metrics, sizes, and accessible interpretations."""
    print_section(11, "Graph generation")
    for chart in charts:
        print(f"Graph title: {chart.title}")
        print(f"Graph path: {chart.path}")
        print(f"Source metric: {chart.source_metric}")
        print(f"Plotted categories or bins: {chart.plotted_items}")
        print(f"Interpretation: {chart.interpretation}")
        print_status(
            chart.path.is_file() and chart.path.stat().st_size > 0, "PNG saved"
        )


def output_validation_passed(run: ExtractionCsvRunResult) -> bool:
    """Confirm the five output files exist with the approved names."""
    actual_names = {output.path.name for output in run.output_files}
    return actual_names == EXPECTED_OUTPUT_NAMES and all(
        output.path.is_file() for output in run.output_files
    )


def show_quality_and_reconciliation(
    run: ExtractionCsvRunResult, outputs_passed: bool
) -> None:
    """Present exact run reconciliation and publication quality gates."""
    print_section(12, "Quality and reconciliation")
    result = run.extraction
    print(
        "Reconciliation formula: "
        f"{result.input_cleaned_jobs} = {result.processed_jobs} + "
        f"{result.skipped_jobs} + {result.processing_error_jobs}"
    )
    print(f"Processed jobs: {result.processed_jobs}")
    print(f"Skipped jobs: {result.skipped_jobs}")
    print(f"Processing errors: {result.processing_error_jobs}")
    print_status(result.reconciliation_passed, "Reconciliation")
    print_status(True, "Dictionary validation")
    print_status(outputs_passed, "Output validation")
    overall = result.reconciliation_passed and outputs_passed
    print(f"Overall extraction quality status: {'PASS' if overall else 'FAIL'}")


def show_postgresql_readiness() -> None:
    """Explain the storage-neutral application boundary for later persistence."""
    print_section(13, "PostgreSQL-readiness explanation")
    print("- Cleaned CSV reading is an outer adapter.")
    print("- The extraction engine accepts typed cleaned-job records.")
    print("- Requirement definitions and aliases are configuration-driven.")
    print("- Evidence and matches are typed application records.")
    print("- Future PostgreSQL repositories can persist the same typed records.")
    print("- No Power BI visual logic exists in the extraction engine.")


def show_final_result(passed: bool) -> None:
    """Print the approved final Demo 2 PASS or FAIL banner."""
    print_section(14, "Final result")
    print("=" * BANNER_WIDTH)
    outcome = "PASS" if passed else "FAIL"
    print(f"DEMO 2 REQUIREMENT AND SKILL EXTRACTION RESULT: {outcome}")
    print("=" * BANNER_WIDTH)


# =============================================================================
# Demonstration orchestration
# =============================================================================


def run_demonstration(arguments: argparse.Namespace) -> int:
    """Run Feature 3 once and present its safe complete processing story."""
    input_path = repository_path(arguments.input)
    profile_path = repository_path(arguments.profile)
    dictionary_path = repository_path(arguments.dictionary)
    output_dir = repository_path(arguments.output_dir)
    steps = StepController(arguments.step)

    print_banner()
    steps.pause()
    show_context(input_path, output_dir)
    steps.pause()

    if not input_path.is_file():
        print_section(3, "Feature 2 prerequisite")
        print_status(False, f"Cleaned Feature 2 input is missing: {input_path}")
        print("Create it first with:")
        print(FEATURE_2_CLEANING_COMMAND)
        show_final_result(False)
        return 1

    try:
        run = process_cleaned_csv(
            input_path=input_path,
            profile_path=profile_path,
            dictionary_path=dictionary_path,
            output_dir=output_dir,
        )
    except (
        ExtractionConfigurationError,
        ExtractionInputError,
        ExtractionReconciliationError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"\n[FAIL] Extraction could not complete: {error}")
        show_final_result(False)
        return 1

    sections = (
        lambda: show_feature_2_prerequisite(run),
        lambda: show_profile_and_dictionary(run.extraction),
        show_false_positive_controls,
        lambda: show_extraction_results(run.extraction),
        lambda: show_confidence_results(run.extraction),
        lambda: show_top_skills(run.extraction, arguments.top_skills),
        lambda: show_safe_evidence_previews(run, arguments.sample_size),
        lambda: show_generated_outputs(run),
    )
    for section in sections:
        section()
        steps.pause()

    try:
        charts = generate_extraction_charts(
            run.extraction,
            output_dir / "charts",
            top_skills=arguments.top_skills,
            show_plots=arguments.show_plots,
        )
    except (OSError, RuntimeError, ValueError) as error:
        print(f"\n[FAIL] Graph generation could not complete: {error}")
        show_final_result(False)
        return 1
    show_graph_generation(charts)
    steps.pause()

    outputs_passed = output_validation_passed(run)
    graphs_passed = all(
        chart.path.is_file() and chart.path.stat().st_size > 0 for chart in charts
    )
    show_quality_and_reconciliation(run, outputs_passed)
    steps.pause()
    show_postgresql_readiness()
    steps.pause()

    passed = run.extraction.reconciliation_passed and outputs_passed and graphs_passed
    show_final_result(passed)
    steps.pause()
    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Parse presentation arguments and return the demonstration exit code."""
    return run_demonstration(parse_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
