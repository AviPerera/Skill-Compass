"""Expose presentation-only reporting for reviewable extraction outputs.

This package may render charts from typed results but must not perform core
matching, demand calculation, database persistence, or Power BI visual logic.
"""

from skill_compass.reporting.skill_extraction_charts import (
    ChartSummary,
    generate_extraction_charts,
)

__all__ = ["ChartSummary", "generate_extraction_charts"]
