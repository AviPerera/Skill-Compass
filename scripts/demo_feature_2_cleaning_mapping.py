"""Present national Feature 2 JSONL mapping and cleaning evidence.

This script belongs to manual presentation support. It calls the existing
JSONL adapter, mapping configuration loader, and Feature 2 service; it must not
implement mapping or cleaning rules, expose listing content, or invoke Apify.
"""

from __future__ import annotations

import argparse
import csv
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from skill_compass.adapters.jsonl import JsonlReadResult, read_source_jsonl
from skill_compass.mapping.config import SourceMappingConfig, load_mapping_config
from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.schemas.jobs import CleanedJob, MappedJob, RejectedRecord
from skill_compass.schemas.quality import QualityMetric
from skill_compass.services.clean_jsonl import process_jsonl
from skill_compass.services.clean_source import CleaningRunResult, ReconciliationError

# =============================================================================
# Presentation configuration
# =============================================================================


BANNER_WIDTH = 79
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION_ROOT = Path("data/private/collections/full")
DEFAULT_MAPPING = Path("sources/apify_seek_current/source_mapping.yaml")
DEFAULT_OUTPUT_DIR = Path("data/processed/national")

RAW_FIELD_EXAMPLES = (
    "id",
    "title",
    "job_url",
    "company_name",
    "description_html",
    "description_text",
    "classification",
    "subclassification",
    "location",
    "work_type",
    "salary_min",
    "salary_max",
    "listing_date",
    "raw/detail/id",
    "raw/listing/classifications/0/classification/id",
)

EXCLUDED_FIELD_EXAMPLES = (
    "contact_email",
    "contact_phone",
    "raw/detail/phoneNumber",
    "raw/detail/contactMatches/0/value",
    "raw/listing/solMetadata/searchRequestToken",
    "raw/listing/solMetadata/token",
    "raw/listing/tracking",
)

UNUSED_METADATA_EXAMPLES = (
    "advertiser_id",
    "advertiser_registered",
    "advertiser_verified",
    "employer_id",
    "employer_company_url",
    "logo_url",
    "raw/listing/branding/serpLogoUrl",
    "raw/listing/displayType",
    "raw/listing/solMetadata/jobAdType",
)

DERIVED_CLEANED_FIELD_EXAMPLES = (
    "title_clean",
    "company_name_clean",
    "description_text_clean",
    "state_code",
    "city_name",
    "salary_min",
    "salary_max",
    "employment_type_codes",
    "work_mode_code",
    "listing_date",
    "content_hash",
    "quality_flags",
)

ANALYSIS_TEXT_FIELDS = (
    "title_clean",
    "summary_text_clean",
    "bullet_points_clean",
    "description_text_clean",
)

EMAIL_PATTERN = re.compile(
    r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
    re.IGNORECASE,
)
CONTACT_COLUMN_PATTERN = re.compile(r"(?:contact|phone|email)", re.IGNORECASE)
TRACKING_COLUMN_PATTERN = re.compile(r"(?:tracking|token|credential)", re.IGNORECASE)


# =============================================================================
# Argument handling and step mode
# =============================================================================


@dataclass(slots=True)
class StepController:
    """Pause between major presentation sections when requested."""

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


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse optional source, mapping, output, and interactive-step arguments."""
    parser = argparse.ArgumentParser(
        description="Demonstrate national JSONL mapping and deterministic cleaning."
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="existing national_jobs_raw.jsonl; newest full backfill is the default",
    )
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--step", action="store_true", help="pause after each major section"
    )
    return parser.parse_args(argv)


def repository_path(path: Path) -> Path:
    """Resolve a relative path from the repository root."""
    return path if path.is_absolute() else REPOSITORY_ROOT / path


def newest_national_input() -> Path:
    """Find the newest named full-backfill national file without modifying it."""
    collection_root = repository_path(DEFAULT_COLLECTION_ROOT)
    candidates = tuple(collection_root.glob("*/national_jobs_raw.jsonl"))
    if not candidates:
        raise FileNotFoundError(
            "no national_jobs_raw.jsonl was found below "
            f"{display_path(collection_root)}"
        )
    return max(candidates, key=lambda path: (path.parent.name, path.as_posix()))


def resolve_input_path(argument: Path | None) -> Path:
    """Resolve an explicit input or discover the newest local full backfill."""
    return (
        repository_path(argument) if argument is not None else newest_national_input()
    )


# =============================================================================
# Safe terminal and metric helpers
# =============================================================================


def display_path(path: Path) -> str:
    """Prefer a repository-relative display path without changing the real path."""
    try:
        return path.resolve().relative_to(REPOSITORY_ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def print_banner() -> None:
    """Print the Feature 2 national demonstration title."""
    print("=" * BANNER_WIDTH)
    print("SKILL COMPASS — FEATURE 2 LIVE DEMONSTRATION")
    print("NATIONAL JSONL MAPPING AND DETERMINISTIC CLEANING")
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


def metric_count(result: CleaningRunResult, name: str) -> int:
    """Return one integer count from the typed Feature 2 quality metrics."""
    value = next(
        metric.metric_value
        for metric in result.quality_metrics
        if metric.metric_name == name
    )
    return int(value)


def declared_source_paths(config: SourceMappingConfig) -> set[str]:
    """Return source paths declared by the already validated mapping contract."""
    return {
        source_path
        for field in config.fields.values()
        for source_path in (*field.preferred, *field.fallbacks)
    }


def excluded_source_paths(
    source: JsonlReadResult, config: SourceMappingConfig
) -> set[str]:
    """Identify present paths described by configured exclusion rules."""
    patterns = tuple(re.compile(pattern) for pattern in config.excluded_field_patterns)
    return {
        field
        for field in source.source_fields
        if field in config.excluded_fields
        or any(pattern.search(field) for pattern in patterns)
    }


def print_present_examples(
    heading: str, examples: tuple[str, ...], present_fields: set[str]
) -> None:
    """Print only approved structural field names that exist in the input."""
    print(heading)
    for field in examples:
        if field in present_fields:
            print(f"- {field}")


def count_csv_matches(path: Path, pattern: re.Pattern[str]) -> int:
    """Count matching output cells without displaying any cell value."""
    matches = 0
    with path.open("r", encoding="utf-8", newline="") as input_file:
        for row in csv.reader(input_file, strict=True):
            matches += sum(bool(pattern.search(value)) for value in row)
    return matches


def output_column_count(filename: str) -> int:
    """Return the stable typed output column count for one Feature 2 file."""
    column_models = {
        "mapped_jobs.csv": MappedJob,
        "cleaned_jobs.csv": CleanedJob,
        "rejected_jobs.csv": RejectedRecord,
        "data_quality_summary.csv": QualityMetric,
    }
    return len(column_models[filename].model_fields)


# =============================================================================
# Live demonstration sections
# =============================================================================


def show_safety_boundary(input_path: Path) -> None:
    """Make the local processing and no-Actor boundary explicit."""
    print_section(1, "Safety boundary")
    print_status(input_path.is_file(), "Existing national JSONL input found")
    print("Actor invocation: NO")
    print("Network requests: NO")
    print("Collection operation: NO")
    print(
        "Purpose: Process the previously collected national dataset through Feature 2."
    )


def show_raw_input(input_path: Path, source: JsonlReadResult) -> None:
    """Present safe file structure without displaying any listing values."""
    print_section(2, "Raw national input")
    print(f"Input: {display_path(input_path)}")
    print(f"Encoding: {source.encoding.upper()}")
    print("File format: JSON Lines")
    print(f"File size: {input_path.stat().st_size / 1024 / 1024:.2f} MiB")
    print(f"Raw job records: {len(source.rows):,}")
    print(
        "Flattened source fields discovered (JSONL column equivalents): "
        f"{len(source.source_fields)}"
    )
    print_present_examples(
        "Example source field names:", RAW_FIELD_EXAMPLES, set(source.source_fields)
    )
    print("No listing descriptions or private field values are displayed.")


def show_mapping_contract(source: JsonlReadResult, config: SourceMappingConfig) -> None:
    """Present governed mapping versions and path coverage."""
    print_section(3, "Source mapping contract")
    declared = declared_source_paths(config)
    present = set(source.source_fields)
    print(f"Source code: {config.source_code}")
    print(f"Mapping version: {config.mapping_version}")
    print(f"Canonical schema version: {config.canonical_schema_version}")
    print(f"Mapping configuration hash: {config.mapping_config_hash[:12]}...")
    print(f"Canonical mapping definitions: {len(config.fields)}")
    print(f"Declared preferred and fallback source paths: {len(declared)}")
    print(f"Declared source paths present in this dataset: {len(declared & present)}")
    print("Required canonical fields:")
    print("- source_job_id")
    print("- title_raw")
    print("- job_url")
    print_status(True, "Source mapping contract validated")


def show_column_selection(source: JsonlReadResult, config: SourceMappingConfig) -> None:
    """Explain source reduction, privacy exclusions, and derived columns."""
    print_section(4, "Column selection and exclusion")
    present = set(source.source_fields)
    declared = declared_source_paths(config)
    unmapped = present - declared
    excluded = excluded_source_paths(source, config)
    print(f"Raw flattened source fields: {len(present)}")
    print(f"Source paths recognised by the mapping: {len(present & declared)}")
    print(f"Source paths intentionally not mapped: {len(unmapped)}")
    print(f"Privacy-related source paths excluded: {len(excluded)}")
    print_present_examples(
        "Examples of excluded private or tracking paths:",
        EXCLUDED_FIELD_EXAMPLES,
        excluded,
    )
    print_present_examples(
        "Examples of unused vendor metadata:", UNUSED_METADATA_EXAMPLES, unmapped
    )
    print(f"Mapped Feature 2 staging columns: {len(MappedJob.model_fields)}")
    print(f"Final cleaned Feature 2 columns: {len(CleanedJob.model_fields)}")
    print(
        "The cleaned contract adds derived analytical fields rather than "
        "retaining source-specific metadata."
    )
    print("Examples of derived cleaned columns:")
    for field in DERIVED_CLEANED_FIELD_EXAMPLES:
        print(f"- {field}")


def show_mapping_results(result: CleaningRunResult) -> None:
    """Present mapping, structural rejection, and duplicate counts."""
    print_section(5, "Mapping results")
    print(f"Input records: {result.input_rows:,}")
    print(f"Successfully mapped: {result.mapping_success_rows:,}")
    print(f"Structural rejections: {result.structurally_rejected_rows:,}")
    print(f"Duplicate identities: {result.duplicate_identity_count:,}")
    print(f"Same-content duplicates: {result.duplicate_same_content_rows:,}")
    print(
        f"Conflicting-content duplicates: {result.duplicate_conflicting_content_rows:,}"
    )
    if result.duplicate_identity_count == 0:
        print("No duplicate identities remained in the supplied JSONL input.")
    else:
        print("Survivor rule: retain the first valid occurrence by source row number.")


def show_cleaning_results(result: CleaningRunResult) -> None:
    """Present governed cleaning outcomes and reviewable unknown counts."""
    print_section(6, "Cleaning results")
    print(f"Titles cleaned: {metric_count(result, 'titles_cleaned'):,}")
    print(f"Geography parsed: {metric_count(result, 'geography_parsed'):,}")
    print(f"Geography unknown: {metric_count(result, 'geography_unknown'):,}")
    print(f"Employment type known: {metric_count(result, 'employment_type_known'):,}")
    print(
        f"Employment type unknown: {metric_count(result, 'employment_type_unknown'):,}"
    )
    work_mode_unknown = metric_count(result, "work_mode_unknown")
    print(f"Work mode known: {len(result.cleaned_jobs) - work_mode_unknown:,}")
    print(f"Work mode unknown: {work_mode_unknown:,}")
    print(f"Listing dates parsed: {metric_count(result, 'listing_date_parsed'):,}")
    print(
        "Listing dates unparseable: "
        f"{metric_count(result, 'listing_date_unparseable'):,}"
    )
    print(
        "Structured salaries parsed: "
        f"{metric_count(result, 'salary_parsed_structured'):,}"
    )
    print(
        "Salary-label fallbacks parsed: "
        f"{metric_count(result, 'salary_parsed_label_fallback'):,}"
    )
    print(f"Salary unavailable or unknown: {metric_count(result, 'salary_unknown'):,}")
    print(
        f"Content hashes produced: {metric_count(result, 'content_hashes_produced'):,}"
    )
    print(
        "Records carrying one or more quality flags: "
        f"{metric_count(result, 'records_with_quality_flags'):,}"
    )
    print(
        "Quality flags do not automatically exclude a job; missing salary, for "
        "example, can remain analytically usable."
    )


def show_analytical_eligibility(result: CleaningRunResult) -> None:
    """Present the exact job population made available to later analysis."""
    print_section(7, "Analytical eligibility")
    eligible_rate = (
        result.analytically_eligible_rows / len(result.cleaned_jobs)
        if result.cleaned_jobs
        else 0.0
    )
    print(f"Cleaned jobs: {len(result.cleaned_jobs):,}")
    print(f"Analytically eligible jobs: {result.analytically_eligible_rows:,}")
    print(f"Analytically ineligible jobs: {result.analytically_ineligible_rows:,}")
    print(
        "Jobs available for subsequent analysis: "
        f"{result.analytically_eligible_rows:,} ({eligible_rate:.1%})"
    )
    print("Requirement extraction analyses four cleaned text sections:")
    for field in ANALYSIS_TEXT_FIELDS:
        print(f"- {field}")
    print(
        "Stable identifiers, versions, and content hashes accompany these fields "
        "for evidence and reconciliation."
    )


def show_privacy_validation(result: CleaningRunResult) -> bool:
    """Report output privacy checks without displaying matching cell values."""
    print_section(8, "Privacy validation")
    paths = {summary.path.name: summary.path for summary in result.output_files}
    mapped_email_count = count_csv_matches(paths["mapped_jobs.csv"], EMAIL_PATTERN)
    cleaned_email_count = count_csv_matches(paths["cleaned_jobs.csv"], EMAIL_PATTERN)
    output_fields = set(MappedJob.model_fields) | set(CleanedJob.model_fields)
    contact_field_count = sum(
        bool(CONTACT_COLUMN_PATTERN.search(field)) for field in output_fields
    )
    tracking_field_count = sum(
        bool(TRACKING_COLUMN_PATTERN.search(field)) for field in output_fields
    )
    print(f"Email-shaped values in mapped output: {mapped_email_count}")
    print(f"Email-shaped values in cleaned output: {cleaned_email_count}")
    print(f"Private contact fields emitted: {contact_field_count}")
    print(f"Tracking fields emitted: {tracking_field_count}")
    passed = all(
        count == 0
        for count in (
            mapped_email_count,
            cleaned_email_count,
            contact_field_count,
            tracking_field_count,
        )
    )
    print_status(passed, "Privacy boundary")
    return passed


def show_generated_outputs(result: CleaningRunResult) -> None:
    """Present each stable output path, record count, and typed column count."""
    print_section(9, "Generated Feature 2 outputs")
    for summary in result.output_files:
        print(display_path(summary.path))
        print(
            f"  {summary.row_count:,} records; "
            f"{output_column_count(summary.path.name)} columns"
        )


def show_reconciliation(result: CleaningRunResult) -> None:
    """Present the exact Feature 2 row reconciliation."""
    print_section(10, "Reconciliation")
    print(f"Input records: {result.input_rows:,}")
    print(f"Cleaned records: {len(result.cleaned_jobs):,}")
    print(f"Rejected records: {result.total_rejected_rows:,}")
    print("Reconciliation formula:")
    print(
        f"{result.input_rows:,} = {len(result.cleaned_jobs):,} + "
        f"{result.total_rejected_rows:,}"
    )
    print_status(result.reconciliation_passed, "Reconciliation")


def show_final_result(passed: bool) -> None:
    """Print the final result and the next implemented boundary."""
    print("\n" + "=" * BANNER_WIDTH)
    outcome = "PASS" if passed else "FAIL"
    print(f"FEATURE 2 NATIONAL MAPPING AND CLEANING RESULT: {outcome}")
    print("=" * BANNER_WIDTH)
    if passed:
        print("\nNext implemented stage:")
        print("uv run skill-compass extract-requirements")


# =============================================================================
# Demonstration orchestration
# =============================================================================


def run_demonstration(arguments: argparse.Namespace) -> int:
    """Run existing Feature 2 components once and present privacy-safe evidence."""
    steps = StepController(enabled=arguments.step)
    try:
        input_path = resolve_input_path(arguments.input)
        mapping_path = repository_path(arguments.mapping)
        output_dir = repository_path(arguments.output_dir)

        print_banner()
        show_safety_boundary(input_path)
        steps.pause()

        source = read_source_jsonl(input_path)
        config = load_mapping_config(mapping_path)
        result = process_jsonl(
            input_path=input_path,
            mapping_path=mapping_path,
            output_dir=output_dir,
        )

        sections = (
            lambda: show_raw_input(input_path, source),
            lambda: show_mapping_contract(source, config),
            lambda: show_column_selection(source, config),
            lambda: show_mapping_results(result),
            lambda: show_cleaning_results(result),
            lambda: show_analytical_eligibility(result),
        )
        for section in sections:
            section()
            steps.pause()

        privacy_passed = show_privacy_validation(result)
        steps.pause()
        show_generated_outputs(result)
        steps.pause()
        show_reconciliation(result)
        steps.pause()
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
        print("Actor invocation: NO")
        show_final_result(False)
        return 1

    passed = result.reconciliation_passed and privacy_passed
    show_final_result(passed)
    steps.pause()
    return 0 if passed else 1


def main(argv: Sequence[str] | None = None) -> int:
    """Parse arguments and return the live demonstration exit code."""
    return run_demonstration(parse_arguments(argv))


if __name__ == "__main__":
    raise SystemExit(main())
