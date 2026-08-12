"""Write stable CSV outputs for deterministic seniority classification.

This outer adapter serializes typed seniority records only and must not load
rules, score evidence, render charts, or expose full job descriptions.
"""

from __future__ import annotations

from pathlib import Path

from skill_compass.adapters.csv import write_model_csv
from skill_compass.schemas.classification import (
    JobSeniorityClassification,
    SeniorityClassificationEvidence,
    SeniorityClassificationQuality,
    SeniorityClassificationRunResult,
    SeniorityDistributionSummary,
    SeniorityReviewQueueItem,
)

# =============================================================================
# Stable output columns and writer
# =============================================================================


JOB_SENIORITY_CLASSIFICATION_COLUMNS = tuple(JobSeniorityClassification.model_fields)
SENIORITY_CLASSIFICATION_EVIDENCE_COLUMNS = tuple(
    SeniorityClassificationEvidence.model_fields
)
SENIORITY_DISTRIBUTION_COLUMNS = tuple(SeniorityDistributionSummary.model_fields)
SENIORITY_CLASSIFICATION_QUALITY_COLUMNS = tuple(
    SeniorityClassificationQuality.model_fields
)
SENIORITY_REVIEW_QUEUE_COLUMNS = tuple(SeniorityReviewQueueItem.model_fields)


def write_seniority_classification_outputs(
    output_dir: Path, result: SeniorityClassificationRunResult
) -> dict[str, int]:
    """Write the five approved seniority-classification CSV outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "job_seniority_classifications.csv": (
            result.classifications,
            JOB_SENIORITY_CLASSIFICATION_COLUMNS,
        ),
        "seniority_classification_evidence.csv": (
            result.evidence,
            SENIORITY_CLASSIFICATION_EVIDENCE_COLUMNS,
        ),
        "seniority_distribution_summary.csv": (
            result.distribution,
            SENIORITY_DISTRIBUTION_COLUMNS,
        ),
        "seniority_classification_quality.csv": (
            (result.quality,),
            SENIORITY_CLASSIFICATION_QUALITY_COLUMNS,
        ),
        "seniority_review_queue.csv": (
            result.review_queue,
            SENIORITY_REVIEW_QUEUE_COLUMNS,
        ),
    }
    return {
        filename: write_model_csv(output_dir / filename, rows, columns)
        for filename, (rows, columns) in outputs.items()
    }
