"""Write stable CSV outputs for deterministic role classification.

This outer adapter serializes typed role records only and must not load rules,
score evidence, render charts, or expose full job descriptions.
"""

from __future__ import annotations

from pathlib import Path

from skill_compass.adapters.csv import write_model_csv
from skill_compass.schemas.classification import (
    JobRoleClassification,
    RoleClassificationEvidence,
    RoleClassificationQuality,
    RoleClassificationRunResult,
    RoleDistributionSummary,
    RoleReviewQueueItem,
)

# =============================================================================
# Stable output columns and writer
# =============================================================================


JOB_ROLE_CLASSIFICATION_COLUMNS = tuple(JobRoleClassification.model_fields)
ROLE_CLASSIFICATION_EVIDENCE_COLUMNS = tuple(RoleClassificationEvidence.model_fields)
ROLE_DISTRIBUTION_COLUMNS = tuple(RoleDistributionSummary.model_fields)
ROLE_CLASSIFICATION_QUALITY_COLUMNS = tuple(RoleClassificationQuality.model_fields)
ROLE_REVIEW_QUEUE_COLUMNS = tuple(RoleReviewQueueItem.model_fields)


def write_role_classification_outputs(
    output_dir: Path, result: RoleClassificationRunResult
) -> dict[str, int]:
    """Write the five approved role-classification CSV outputs."""
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "job_role_classifications.csv": (
            result.classifications,
            JOB_ROLE_CLASSIFICATION_COLUMNS,
        ),
        "role_classification_evidence.csv": (
            result.evidence,
            ROLE_CLASSIFICATION_EVIDENCE_COLUMNS,
        ),
        "role_distribution_summary.csv": (
            result.distribution,
            ROLE_DISTRIBUTION_COLUMNS,
        ),
        "role_classification_quality.csv": (
            (result.quality,),
            ROLE_CLASSIFICATION_QUALITY_COLUMNS,
        ),
        "review_queue.csv": (
            result.review_queue,
            ROLE_REVIEW_QUEUE_COLUMNS,
        ),
    }
    return {
        filename: write_model_csv(output_dir / filename, rows, columns)
        for filename, (rows, columns) in outputs.items()
    }
