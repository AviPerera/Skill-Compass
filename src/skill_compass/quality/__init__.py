"""Expose deterministic run-reconciliation and data-quality calculations.

This package calculates typed metrics and must not read source files, clean
records, write outputs, or contain presentation-specific logic.
"""

from skill_compass.quality.service import build_quality_metrics

__all__ = ["build_quality_metrics"]
