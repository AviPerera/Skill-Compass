"""Define stable tabular quality metrics for pipeline reconciliation.

These application records carry calculated evidence and must not read inputs,
perform cleaning, or choose presentation-specific formatting.
"""

from typing import Literal

from skill_compass.schemas.jobs import ImmutableModel


class QualityMetric(ImmutableModel):
    """Represent one deterministic row in the data-quality summary."""

    metric_category: str
    metric_name: str
    metric_value: str
    metric_status: Literal["pass", "fail", "warning", "info"]
    metric_detail: str
