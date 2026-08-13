"""Load governed local outputs and run the channel-neutral analytics engine.

This application service coordinates typed adapters, configuration loaders,
analytics, and exports. It must not render charts or access external services.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from skill_compass.adapters.analytics_csv import write_analytics_outputs
from skill_compass.adapters.extraction_csv import read_cleaned_jobs_csv
from skill_compass.adapters.relevance_csv import (
    read_job_requirement_matches_csv,
    read_profile_relevance_csv,
    read_role_classifications_csv,
    read_seniority_classifications_csv,
)
from skill_compass.analytics.service import build_analytics
from skill_compass.classification.config import load_role_rules
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.schemas.analytics import AnalyticsRunResult

# =============================================================================
# Conventional paths and service result
# =============================================================================


ROLE_PATH = Path("role_classification/job_role_classifications.csv")
SENIORITY_PATH = Path("seniority_classification/job_seniority_classifications.csv")
RELEVANCE_PATH = Path("profile_relevance/job_profile_relevance.csv")
REQUIREMENT_PATH = Path("skill_extraction/job_requirement_matches.csv")


@dataclass(frozen=True, slots=True)
class AnalyticsOutputFileSummary:
    """Describe one generated Feature 8 output and its logical row count."""

    path: Path
    row_count: int


@dataclass(frozen=True, slots=True)
class AnalyticsCsvRunResult:
    """Bundle the typed analytics result and generated output evidence."""

    input_dir: Path
    output_dir: Path
    analytics: AnalyticsRunResult
    output_files: tuple[AnalyticsOutputFileSummary, ...]


# =============================================================================
# Public application service
# =============================================================================


def process_analytics(
    *,
    input_dir: Path,
    profile_path: Path,
    dictionary_path: Path,
    role_rules_path: Path,
    seniority_rules_path: Path,
    output_dir: Path,
    minimum_sample_size: int = 20,
) -> AnalyticsCsvRunResult:
    """Load existing Feature 2/3/5/6/7 outputs, calculate, and export analytics."""
    profile = load_extraction_profile(profile_path)
    dictionary = load_requirement_dictionary(dictionary_path, profile)
    role_rules = load_role_rules(role_rules_path)
    seniority_rules = load_seniority_rules(seniority_rules_path)
    result = build_analytics(
        cleaned_jobs=read_cleaned_jobs_csv(input_dir / "cleaned_jobs.csv"),
        role_classifications=read_role_classifications_csv(input_dir / ROLE_PATH),
        seniority_classifications=read_seniority_classifications_csv(
            input_dir / SENIORITY_PATH
        ),
        relevance_classifications=read_profile_relevance_csv(
            input_dir / RELEVANCE_PATH
        ),
        requirement_matches=read_job_requirement_matches_csv(
            input_dir / REQUIREMENT_PATH
        ),
        role_rules=role_rules,
        seniority_rules=seniority_rules,
        requirement_dictionary=dictionary,
        minimum_sample_size=minimum_sample_size,
    )
    counts = write_analytics_outputs(output_dir, result)
    return AnalyticsCsvRunResult(
        input_dir=input_dir,
        output_dir=output_dir,
        analytics=result,
        output_files=tuple(
            AnalyticsOutputFileSummary(output_dir / filename, row_count)
            for filename, row_count in counts.items()
        ),
    )
