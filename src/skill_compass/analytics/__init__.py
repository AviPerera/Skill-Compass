"""Expose channel-neutral analytics without presentation or persistence logic.

This package calculates reusable facts and aggregates and must not query Power
BI views, render dashboards, access source-specific fields, or manage databases.
"""

from skill_compass.analytics.service import AnalyticsInputError, build_analytics

__all__ = ["AnalyticsInputError", "build_analytics"]
