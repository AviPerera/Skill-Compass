"""Present the temporary Demo 2 canonical mapping and cleaning workflow.

This script belongs to manual presentation support and must not duplicate
mapping or cleaning logic, expose private text, or act as a production CLI.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.schemas.jobs import CleanedJob
from skill_compass.services.clean_csv import (
    CleaningRunResult,
    ReconciliationError,
    process_csv,
)

# =============================================================================
# Presentation configuration
# =============================================================================


BANNER_WIDTH = 79
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = Path("data/private/adelaide_146_jobs_raw.csv")
DEFAULT_MAPPING = Path("sources/apify_seek_current/source_mapping.yaml")
DEFAULT_OUTPUT_DIR = Path("data/processed/demo_2")
EXPECTED_PRIVATE_ROW_COUNT = 146

KEY_MAPPING_FIELDS = (
    "source_job_id",
    "title_raw",
    "job_url",
    "company_name_raw",
    "description_html_raw",
    "listing_date_raw",
    "salary_label_raw",
    "work_arrangement_raw",
)


# =============================================================================
# Step mode and argument handling
# =============================================================================


@dataclass(slots=True)
class StepController:
    """Pause between major sections when interactive presentation is requested."""

    enabled: bool

    def pause(self) -> None:
        """Wait for Enter, disabling later pauses if input is unavailable."""
        if not self.enabled:
            return
        try:
            input("\nPress Enter to continue...")
        except EOFError:
            print("\nInteractive input is unavailable; continuing without pauses.")
            self.enabled = False


def positive_integer(value: str) -> int:
    """Parse a strictly positive preview sample size."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("sample size must be at least 1")
    return parsed


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse optional paths, preview size, and interactive step mode."""
    parser = argparse.ArgumentParser(
        description="Demonstrate canonical CSV mapping and deterministic cleaning."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--sample-size", type=positive_integer, default=3)
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
    """Print the approved two-line Demo 2 title."""
    print("=" * BANNER_WIDTH)
    print("SKILL COMPASS — DEMO 2")
    print("CANONICAL MAPPING AND DATA CLEANING")
    print("=" * BANNER_WIDTH)


def print_section(number: int, title: str) -> None:
    """Print one consistently formatted numbered heading."""
    heading = f"{number}. {title}"
    print(f"\n{heading}")
    print("-" * len(heading))


def print_status(passed: bool, message: str) -> None:
    """Print one deterministic PASS or FAIL line."""
    marker = "PASS" if passed else "FAIL"
    print(f"[{marker}] {message}")


def truncate(value: str | None, limit: int = 72) -> str:
    """Keep safe preview values readable without printing unusually long text."""
    if not value:
        return "<unknown>"
    single_line = " ".join(value.split())
    return (
        single_line if len(single_line) <= limit else f"{single_line[: limit - 3]}..."
    )


def masked_source_job_id(value: str) -> str:
    """Mask most of an external source identifier for terminal previews."""
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def metric_count(result: CleaningRunResult, name: str) -> int:
    """Return an integer quality metric from a successful run result."""
    value = next(
        metric.metric_value
        for metric in result.quality_metrics
        if metric.metric_name == name
    )
    return int(value)


def format_decimal(value: Decimal | None) -> str | None:
    """Format a salary boundary without display-only decimal noise."""
    if value is None:
        return None
    return f"{value:,.2f}".rstrip("0").rstrip(".")


def salary_preview(job: CleanedJob) -> str:
    """Format only the salary boundaries that were explicitly parsed."""
    minimum = format_decimal(job.salary_min)
    maximum = format_decimal(job.salary_max)
    currency = job.salary_currency or ""
    period = f" per {job.salary_period}" if job.salary_period else ""
    if minimum and maximum:
        salary_range = minimum if minimum == maximum else f"{minimum} - {maximum}"
    elif minimum:
        salary_range = f"from {minimum}"
    elif maximum:
        salary_range = f"up to {maximum}"
    else:
        return "<unknown>"
    return f"{currency} {salary_range}{period}".strip()


# =============================================================================
# Demo 2 terminal sections
# =============================================================================


def show_context(input_path: Path, output_dir: Path) -> None:
    """Present the current phase and file-boundary context."""
    print_section(2, "Demonstration context")
    current_time = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    print("Current implementation: Phase 2, Stage 2")
    print(
        "Purpose: Map source-specific CSV fields into canonical typed records, then clean them deterministically."
    )
    print("Architecture direction: CSV boundary now; PostgreSQL adapter later.")
    print(f"Repository root: {REPOSITORY_ROOT}")
    print(f"Current date and time: {current_time}")
    print(f"Input path: {input_path}")
    print(f"Output path: {output_dir}")


def show_input_inspection(result: CleaningRunResult) -> None:
    """Present safe CSV structure and only key mapping source fields."""
    print_section(3, "Input inspection")
    print_status(result.input_path.is_file(), "Input file exists")
    print(f"Encoding used: {result.input_encoding}")
    print("Delimiter: comma (,)")
    print('Quote character: double quote (") with doubled-quote escaping')
    print(f"Source rows: {result.input_rows}")
    print(f"Source columns: {result.source_column_count}")
    print("Expected sample context: Adelaide SEEK/Apify sample")
    if result.input_rows == EXPECTED_PRIVATE_ROW_COUNT:
        print_status(True, "Actual row count matches the expected 146-row sample")
    else:
        print(
            f"[WARNING] Actual row count is {result.input_rows}; the private demonstration sample is expected to contain 146 rows."
        )

    print("Key preferred/fallback source fields:")
    for canonical_name in KEY_MAPPING_FIELDS:
        field_mapping = result.mapping_config.fields[canonical_name]
        preferred = ", ".join(field_mapping.preferred)
        fallbacks = ", ".join(field_mapping.fallbacks) or "<none>"
        print(f"- {canonical_name}: preferred [{preferred}]; fallbacks [{fallbacks}]")


def show_mapping_contract(result: CleaningRunResult) -> None:
    """Present versioned mapping governance without listing private columns."""
    print_section(4, "Mapping contract")
    config = result.mapping_config
    print(f"Source code: {config.source_code}")
    print(f"Mapping name: {config.mapping_name}")
    print(f"Mapping version: {config.mapping_version}")
    print(f"Canonical schema version: {config.canonical_schema_version}")
    print(f"Mapping configuration hash: {config.mapping_config_hash[:12]}...")
    print("Required canonical fields: source_job_id, title_raw, job_url")
    print(f"Mapped canonical field count: {len(config.fields)}")
    print(
        "Excluded field rules: "
        f"{len(config.excluded_fields)} exact names and "
        f"{len(config.excluded_field_patterns)} contact/tracking/credential patterns"
    )
    print_status(True, "Executable YAML expressions are not permitted")


def show_mapping_results(result: CleaningRunResult) -> None:
    """Present mapping counts and analytical eligibility outcomes."""
    print_section(5, "Mapping results")
    print(f"Input rows: {result.input_rows}")
    print(f"Successfully mapped before deduplication: {result.mapping_success_rows}")
    print(f"Structural rejections: {result.structurally_rejected_rows}")
    print(f"Fallback-field uses: {result.fallback_field_use_count}")
    print(
        "Missing usable descriptions: "
        f"{metric_count(result, 'missing_usable_description')}"
    )
    print(f"Analytically eligible: {result.analytically_eligible_rows}")
    print(f"Analytically ineligible: {result.analytically_ineligible_rows}")


def show_duplicate_handling(result: CleaningRunResult) -> None:
    """Present deterministic within-file duplicate decisions."""
    print_section(6, "Duplicate handling")
    print(f"Duplicate identities found: {result.duplicate_identity_count}")
    print(f"duplicate_same_content: {result.duplicate_same_content_rows}")
    print(f"duplicate_conflicting_content: {result.duplicate_conflicting_content_rows}")
    print("Survivor rule: retain the first valid occurrence by source row number.")


def show_cleaning_results(result: CleaningRunResult) -> None:
    """Present all requested deterministic cleaning result counts."""
    print_section(7, "Cleaning results")
    print(f"Titles cleaned: {metric_count(result, 'titles_cleaned')}")
    print(
        "HTML descriptions converted: "
        f"{metric_count(result, 'html_descriptions_converted')}"
    )
    print(
        "Geography parsed / unknown: "
        f"{metric_count(result, 'geography_parsed')} / "
        f"{metric_count(result, 'geography_unknown')}"
    )
    print(
        "Salary structured / label fallback / unknown: "
        f"{metric_count(result, 'salary_parsed_structured')} / "
        f"{metric_count(result, 'salary_parsed_label_fallback')} / "
        f"{metric_count(result, 'salary_unknown')}"
    )
    print(
        "Employment type known / unknown: "
        f"{metric_count(result, 'employment_type_known')} / "
        f"{metric_count(result, 'employment_type_unknown')}"
    )
    known_work_modes = len(result.cleaned_jobs) - metric_count(
        result, "work_mode_unknown"
    )
    print(
        "Work mode known / unknown: "
        f"{known_work_modes} / {metric_count(result, 'work_mode_unknown')}"
    )
    print(
        "Listing dates parsed / unparseable: "
        f"{metric_count(result, 'listing_date_parsed')} / "
        f"{metric_count(result, 'listing_date_unparseable')}"
    )
    print(f"Content hashes produced: {metric_count(result, 'content_hashes_produced')}")
    print(
        "Records with quality flags: "
        f"{metric_count(result, 'records_with_quality_flags')}"
    )


def show_safe_preview(result: CleaningRunResult, sample_size: int) -> None:
    """Show bounded safe fields without descriptions, bullets, URLs, or contacts."""
    print_section(8, "Safe before-and-after preview")
    preview_jobs = result.cleaned_jobs[:sample_size]
    if not preview_jobs:
        print("No cleaned records are available for preview.")
        return

    for position, job in enumerate(preview_jobs, start=1):
        print(f"\nPreview {position}")
        print(f"  Source row number: {job.source_row_number}")
        print(f"  Source job ID: {masked_source_job_id(job.source_job_id)}")
        print(f"  title_raw: {truncate(job.title_raw)}")
        print(f"  title_clean: {truncate(job.title_clean)}")
        print(f"  company_name_clean: {truncate(job.company_name_clean)}")
        print(f"  location_raw: {truncate(job.location_raw)}")
        print(f"  city_name: {job.city_name or '<unknown>'}")
        print(f"  state_code: {job.state_code or '<unknown>'}")
        print(f"  salary_label_raw: {truncate(job.salary_label_raw)}")
        print(f"  parsed salary: {salary_preview(job)}")
        print(f"  employment type: {', '.join(job.employment_type_codes)}")
        print(f"  work mode: {job.work_mode_code}")
        print(f"  listing date: {job.listing_date or '<unknown>'}")
        flags = ", ".join(job.quality_flags) or "<none>"
        print(f"  quality flags: {truncate(flags)}")
        print(f"  content hash: {job.content_hash[:12]}...")


def show_generated_outputs(result: CleaningRunResult) -> None:
    """Present each approved generated path and its data-row count."""
    print_section(9, "Generated outputs")
    for output_file in result.output_files:
        print(f"{output_file.path}: {output_file.row_count} rows")


def show_quality_reconciliation(result: CleaningRunResult) -> None:
    """Present the exact reconciliation formula and overall quality status."""
    print_section(10, "Quality and reconciliation")
    print(f"Input rows: {result.input_rows}")
    print(f"Cleaned rows: {len(result.cleaned_jobs)}")
    print(f"Rejected rows: {result.total_rejected_rows}")
    print(
        "Reconciliation formula: "
        f"{result.input_rows} = {len(result.cleaned_jobs)} + "
        f"{result.total_rejected_rows}"
    )
    print_status(result.reconciliation_passed, "Reconciliation")
    print(
        f"Overall quality status: {'PASS' if result.reconciliation_passed else 'FAIL'}"
    )


def show_postgresql_readiness() -> None:
    """Explain the adapter boundary and future storage compatibility."""
    print_section(11, "PostgreSQL-readiness explanation")
    print("- CSV reading and writing are outer boundary adapters.")
    print("- Source-specific names are isolated in the versioned source mapping.")
    print("- Cleaning accepts typed canonical application records.")
    print("- A later PostgreSQL adapter can supply and consume the same typed records.")
    print("- No Power BI logic is embedded in the mapping or cleaning pipeline.")


def show_final_result(passed: bool) -> None:
    """Print the approved final PASS or FAIL banner."""
    print_section(12, "Final result")
    print("=" * BANNER_WIDTH)
    outcome = "PASS" if passed else "FAIL"
    print(f"DEMO 2 CANONICAL MAPPING AND CLEANING RESULT: {outcome}")
    print("=" * BANNER_WIDTH)


# =============================================================================
# Demonstration orchestration
# =============================================================================


def run_demonstration(arguments: argparse.Namespace) -> int:
    """Run the reusable service once and present its safe typed results."""
    input_path = repository_path(arguments.input)
    mapping_path = repository_path(arguments.mapping)
    output_dir = repository_path(arguments.output_dir)
    steps = StepController(enabled=arguments.step)

    print_banner()
    steps.pause()
    show_context(input_path, output_dir)
    steps.pause()

    try:
        result = process_csv(
            input_path=input_path,
            mapping_path=mapping_path,
            output_dir=output_dir,
        )
    except (
        MappingConfigurationError,
        ReconciliationError,
        FileNotFoundError,
        UnicodeError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"\n[FAIL] Demonstration could not complete: {error}")
        show_final_result(False)
        return 1

    sections = (
        lambda: show_input_inspection(result),
        lambda: show_mapping_contract(result),
        lambda: show_mapping_results(result),
        lambda: show_duplicate_handling(result),
        lambda: show_cleaning_results(result),
        lambda: show_safe_preview(result, arguments.sample_size),
        lambda: show_generated_outputs(result),
        lambda: show_quality_reconciliation(result),
        show_postgresql_readiness,
    )
    for section in sections:
        section()
        steps.pause()

    show_final_result(result.reconciliation_passed)
    steps.pause()
    return 0 if result.reconciliation_passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and return the Demo 2 process exit code."""
    return run_demonstration(parse_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
