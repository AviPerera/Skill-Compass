"""Provide the thin command-line boundary for Skill Compass application services.

This adapter parses arguments and reports safe summaries; it must not contain
mapping, cleaning, extraction, classification, or quality business rules.
"""

from __future__ import annotations

import argparse
import csv
from collections.abc import Sequence
from pathlib import Path

from skill_compass.classification.errors import (
    RoleClassificationError,
    RoleConfigurationError,
    SeniorityClassificationError,
    SeniorityConfigurationError,
)
from skill_compass.collection.apify_client import ApifyCollectionError
from skill_compass.collection.seek_adapter import SeekCollectionConfigurationError
from skill_compass.config.settings import CollectionConfigurationError
from skill_compass.extraction.errors import (
    ExtractionConfigurationError,
    ExtractionInputError,
    ExtractionReconciliationError,
)
from skill_compass.mapping.errors import MappingConfigurationError
from skill_compass.services.apify_connection_test import run_apify_connection_test
from skill_compass.services.classify_roles import process_role_classification
from skill_compass.services.classify_seniority import process_seniority_classification
from skill_compass.services.clean_csv import ReconciliationError, process_csv
from skill_compass.services.clean_jsonl import process_jsonl
from skill_compass.services.extract_requirements import process_cleaned_csv
from skill_compass.services.fetch_apify import (
    DEFAULT_FETCH_OUTPUT_ROOT,
    fetch_existing_apify_dataset,
)
from skill_compass.services.fetch_backfill import (
    DEFAULT_BACKFILL_FETCH_ROOT,
    DEFAULT_SEEK_COLLECTION_PATH,
    run_fetch_backfill_command,
)
from skill_compass.services.full_collection import (
    DEFAULT_ACTOR_CONFIG_PATH,
    DEFAULT_FULL_COLLECTION_ROOT,
    DEFAULT_SEARCH_SCOPES_PATH,
    run_full_collection_command,
)

# =============================================================================
# Command parsing and safe output
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    """Build the Skill Compass parser and current explicit subcommands."""
    parser = argparse.ArgumentParser(prog="skill-compass")
    subcommands = parser.add_subparsers(dest="command", required=True)

    clean_csv = subcommands.add_parser(
        "clean-csv", help="map and deterministically clean an explicit source CSV"
    )
    clean_csv.add_argument("--input", type=Path, required=True)
    clean_csv.add_argument("--mapping", type=Path, required=True)
    clean_csv.add_argument("--output-dir", type=Path, required=True)

    clean_jsonl = subcommands.add_parser(
        "clean-jsonl",
        help="map and deterministically clean an existing source JSONL file",
    )
    clean_jsonl.add_argument("--input", type=Path, required=True)
    clean_jsonl.add_argument("--mapping", type=Path, required=True)
    clean_jsonl.add_argument("--output-dir", type=Path, required=True)

    extract = subcommands.add_parser(
        "extract-requirements",
        help="extract deterministic requirements from a Feature 2 cleaned CSV",
    )
    extract.add_argument("--input", type=Path, required=True)
    extract.add_argument("--profile", type=Path, required=True)
    extract.add_argument("--dictionary", type=Path, required=True)
    extract.add_argument("--output-dir", type=Path, required=True)

    classify = subcommands.add_parser(
        "classify-roles",
        help="classify roles from a Feature 2 cleaned CSV without external calls",
    )
    classify.add_argument("--input", type=Path, required=True)
    classify.add_argument("--rules", type=Path, required=True)
    classify.add_argument("--output-dir", type=Path, required=True)

    classify_seniority = subcommands.add_parser(
        "classify-seniority",
        help="classify seniority from a Feature 2 cleaned CSV without external calls",
    )
    classify_seniority.add_argument("--input", type=Path, required=True)
    classify_seniority.add_argument("--rules", type=Path, required=True)
    classify_seniority.add_argument("--output-dir", type=Path, required=True)

    apify_test = subcommands.add_parser(
        "test-apify-connection",
        help="run the explicit five-item SEEK Actor connection test",
    )
    apify_test.add_argument(
        "--config",
        type=Path,
        default=Path("sources/apify_seek_current/collection.yaml"),
    )

    fetch_apify = subcommands.add_parser(
        "fetch-apify",
        help="fetch an existing Apify dataset without invoking an Actor",
    )
    fetch_identifier = fetch_apify.add_mutually_exclusive_group(required=True)
    fetch_identifier.add_argument("--dataset-id")
    fetch_identifier.add_argument("--run-id")
    fetch_apify.add_argument(
        "--config",
        type=Path,
        default=Path("sources/apify_seek_current/collection.yaml"),
    )
    fetch_apify.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_FETCH_OUTPUT_ROOT,
    )

    fetch_backfill = subcommands.add_parser(
        "fetch-backfill",
        help="fetch all existing national backfill datasets without an Actor",
    )
    fetch_backfill.add_argument(
        "--manifest",
        type=Path,
        help="private 66-scope source CSV; not needed for successful-run discovery",
    )
    fetch_backfill.add_argument("--dry-run", action="store_true")
    fetch_backfill.add_argument("--force", action="store_true")
    fetch_backfill.add_argument(
        "--include-all-successful-runs",
        action="store_true",
        help="append datasets from all other successful runs of the configured Actor",
    )
    fetch_backfill.add_argument(
        "--actor-config",
        type=Path,
        default=DEFAULT_SEEK_COLLECTION_PATH,
        help="source configuration containing the approved Actor ID",
    )
    fetch_backfill.add_argument(
        "--search-scopes", type=Path, default=DEFAULT_SEARCH_SCOPES_PATH
    )
    fetch_backfill.add_argument(
        "--output-root", type=Path, default=DEFAULT_BACKFILL_FETCH_ROOT
    )

    collect_full = subcommands.add_parser(
        "collect-full",
        help="plan or explicitly execute the one-time national backfill",
    )
    collect_mode = collect_full.add_mutually_exclusive_group(required=True)
    collect_mode.add_argument("--dry-run", action="store_true")
    collect_mode.add_argument("--execute", action="store_true")
    collect_full.add_argument("--resume", action="store_true")
    collect_full.add_argument("--force", action="store_true")
    collect_full.add_argument(
        "--search-scopes", type=Path, default=DEFAULT_SEARCH_SCOPES_PATH
    )
    collect_full.add_argument(
        "--actor-config", type=Path, default=DEFAULT_ACTOR_CONFIG_PATH
    )
    collect_full.add_argument(
        "--output-root", type=Path, default=DEFAULT_FULL_COLLECTION_ROOT
    )
    return parser


def run_clean_csv(arguments: argparse.Namespace) -> int:
    """Call the reusable service and print a concise privacy-safe run summary."""
    try:
        result = process_csv(
            input_path=arguments.input,
            mapping_path=arguments.mapping,
            output_dir=arguments.output_dir,
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
        print(f"clean-csv failed: {error}")
        return 1

    print("clean-csv completed successfully")
    print(f"Input rows: {result.input_rows}")
    print(f"Cleaned rows: {len(result.cleaned_jobs)}")
    print(f"Rejected rows: {result.total_rejected_rows}")
    print("Reconciliation: PASS")
    print(f"Output directory: {result.output_dir}")
    return 0


def run_clean_jsonl(arguments: argparse.Namespace) -> int:
    """Process existing JSONL and explicitly preserve the no-Actor boundary."""
    try:
        result = process_jsonl(
            input_path=arguments.input,
            mapping_path=arguments.mapping,
            output_dir=arguments.output_dir,
        )
    except (
        MappingConfigurationError,
        ReconciliationError,
        FileNotFoundError,
        UnicodeError,
        OSError,
        ValueError,
    ) as error:
        print(f"clean-jsonl failed: {error}")
        print("Actor invocation: NO")
        return 1

    print("clean-jsonl completed successfully")
    print("Actor invocation: NO")
    print(f"Input rows: {result.input_rows}")
    print(f"Cleaned rows: {len(result.cleaned_jobs)}")
    print(f"Rejected rows: {result.total_rejected_rows}")
    print("Reconciliation: PASS")
    print(f"Output directory: {result.output_dir}")
    return 0


def run_extract_requirements(arguments: argparse.Namespace) -> int:
    """Call the extraction service and print a concise privacy-safe summary."""
    try:
        result = process_cleaned_csv(
            input_path=arguments.input,
            profile_path=arguments.profile,
            dictionary_path=arguments.dictionary,
            output_dir=arguments.output_dir,
        )
    except (
        ExtractionConfigurationError,
        ExtractionInputError,
        ExtractionReconciliationError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"extract-requirements failed: {error}")
        return 1

    extraction = result.extraction
    print("extract-requirements completed successfully")
    print(f"Cleaned input jobs: {extraction.input_cleaned_jobs}")
    print(f"Eligible jobs: {extraction.analytically_eligible_jobs}")
    print(f"Skipped jobs: {extraction.skipped_jobs}")
    print(f"Job-requirement matches: {len(extraction.job_requirement_matches)}")
    print(f"Evidence rows: {len(extraction.evidence)}")
    print("Reconciliation: PASS")
    print(f"Output directory: {result.output_dir}")
    return 0


def run_classify_roles(arguments: argparse.Namespace) -> int:
    """Call the role service and print a concise privacy-safe summary."""
    try:
        run = process_role_classification(
            input_path=arguments.input,
            rules_path=arguments.rules,
            output_dir=arguments.output_dir,
        )
    except (
        RoleClassificationError,
        RoleConfigurationError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"classify-roles failed: {error}")
        print("External API requests: 0")
        return 1

    result = run.classification
    print("classify-roles completed successfully")
    print(f"Cleaned input jobs: {result.input_job_count}")
    print(f"Dashboard-role jobs: {result.quality.classified_into_dashboard_role}")
    print(f"Other jobs: {result.quality.other_count}")
    print(f"Review jobs: {result.quality.review_count}")
    print(f"Evidence rows: {len(result.evidence)}")
    print("Reconciliation: PASS")
    print("External API requests: 0")
    print(f"Output directory: {run.output_dir}")
    return 0


def run_classify_seniority(arguments: argparse.Namespace) -> int:
    """Call the seniority service and print a concise privacy-safe summary."""
    try:
        run = process_seniority_classification(
            input_path=arguments.input,
            rules_path=arguments.rules,
            output_dir=arguments.output_dir,
        )
    except (
        SeniorityClassificationError,
        SeniorityConfigurationError,
        csv.Error,
        OSError,
        ValueError,
    ) as error:
        print(f"classify-seniority failed: {error}")
        print("External API requests: 0")
        return 1

    result = run.classification
    print("classify-seniority completed successfully")
    print(f"Cleaned input jobs: {result.input_job_count}")
    print(f"Dashboard-level jobs: {result.quality.classified_into_dashboard_level}")
    print(f"Graduate-level jobs: {result.quality.graduate_level_count}")
    print(f"Unknown jobs: {result.quality.unknown_count}")
    print(f"Review jobs: {result.quality.review_count}")
    print(f"Evidence rows: {len(result.evidence)}")
    print("Reconciliation: PASS")
    print("External API requests: 0")
    print(f"Output directory: {run.output_dir}")
    return 0


def run_test_apify_connection(arguments: argparse.Namespace) -> int:
    """Run only the bounded Apify test and print no source records or secrets."""
    try:
        response = run_apify_connection_test(config_path=arguments.config)
    except (
        ApifyCollectionError,
        CollectionConfigurationError,
        SeekCollectionConfigurationError,
        OSError,
        ValueError,
    ) as error:
        print(f"test-apify-connection failed: {error}")
        return 1

    result = response.result
    print("=" * 60)
    print("SKILL COMPASS — APIFY CONNECTION TEST")
    print("=" * 60)
    print()
    print("Actor connection: PASS")
    print(f"Run status: {result.status}")
    print(f"Run ID: {result.run_id}")
    print(f"Dataset ID: {result.dataset_id}")
    print(f"Items retrieved: {result.returned_item_count}")
    print(f"Cap assessment: {result.cap_status.value}")
    print()
    print("No processing or analysis was executed.")
    return 0


def run_fetch_apify(arguments: argparse.Namespace) -> int:
    """Fetch existing raw data and clearly report the no-Actor cost boundary."""
    try:
        result = fetch_existing_apify_dataset(
            config_path=arguments.config,
            dataset_id=arguments.dataset_id,
            run_id=arguments.run_id,
            output_root=arguments.output_root,
        )
    except (
        ApifyCollectionError,
        CollectionConfigurationError,
        SeekCollectionConfigurationError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        print(f"fetch-apify failed: {error}")
        return 1

    manifest = result.manifest
    print("=" * 60)
    print("SKILL COMPASS — EXISTING APIFY DATASET FETCH")
    print("=" * 60)
    print()
    print("Actor invocation: NO")
    print("Existing dataset fetch only")
    if manifest.run_id is not None:
        print(f"Run ID: {manifest.run_id}")
    print(f"Dataset ID: {manifest.dataset_id}")
    print(f"Items retrieved: {manifest.returned_item_count}")
    print(f"Cap assessment: {manifest.cap_status.value}")
    print(f"Raw JSONL: {result.items_path}")
    print(f"Fetch manifest: {result.manifest_path}")
    print()
    print("No processing or analysis was executed.")
    return 0


def run_collect_full(arguments: argparse.Namespace) -> int:
    """Delegate the safety-gated national backfill to its reusable service."""
    return run_full_collection_command(
        dry_run=arguments.dry_run,
        execute=arguments.execute,
        resume=arguments.resume,
        force=arguments.force,
        search_scopes_path=arguments.search_scopes,
        actor_config_path=arguments.actor_config,
        output_root=arguments.output_root,
        resume_command="uv run skill-compass collect-full --execute --resume",
    )


def run_fetch_backfill(arguments: argparse.Namespace) -> int:
    """Delegate no-Actor national retrieval to the reusable Feature 4B service."""
    if arguments.dry_run and arguments.force:
        print("--force cannot be combined with --dry-run. Actor invocation: NO")
        return 2
    return run_fetch_backfill_command(
        source_manifest_path=arguments.manifest,
        dry_run=arguments.dry_run,
        force=arguments.force,
        include_all_successful_runs=arguments.include_all_successful_runs,
        actor_config_path=arguments.actor_config,
        search_scopes_path=arguments.search_scopes,
        output_root=arguments.output_root,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch one parsed command and return its process exit code."""
    parser = build_parser()
    arguments = parser.parse_args(argv)
    if arguments.command == "clean-csv":
        return run_clean_csv(arguments)
    if arguments.command == "clean-jsonl":
        return run_clean_jsonl(arguments)
    if arguments.command == "extract-requirements":
        return run_extract_requirements(arguments)
    if arguments.command == "classify-roles":
        return run_classify_roles(arguments)
    if arguments.command == "classify-seniority":
        return run_classify_seniority(arguments)
    if arguments.command == "test-apify-connection":
        return run_test_apify_connection(arguments)
    if arguments.command == "fetch-apify":
        return run_fetch_apify(arguments)
    if arguments.command == "fetch-backfill":
        return run_fetch_backfill(arguments)
    if arguments.command == "collect-full":
        return run_collect_full(arguments)
    parser.error("unsupported command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
