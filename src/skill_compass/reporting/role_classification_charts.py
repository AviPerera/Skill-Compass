"""Render the two approved Feature 5 role-classification charts.

This reporting layer consumes typed results and must not change role outcomes,
read source data, or implement Power BI presentation logic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from skill_compass.schemas.classification import RoleClassificationRunResult

# =============================================================================
# Chart metadata and rendering
# =============================================================================


@dataclass(frozen=True, slots=True)
class RoleChartSummary:
    """Describe one saved chart and its plotted population."""

    title: str
    path: Path
    plotted_items: int


def generate_role_classification_charts(
    result: RoleClassificationRunResult, output_dir: Path
) -> tuple[RoleChartSummary, RoleChartSummary]:
    """Save role counts and deterministic confidence-score distributions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    role_path = output_dir / "role_distribution.png"
    confidence_path = output_dir / "role_confidence_distribution.png"

    role_figure = Figure(figsize=(11, 6.5))
    FigureCanvasAgg(role_figure)
    role_axes = role_figure.subplots()
    labels = [row.role_group_label for row in result.distribution]
    counts = [row.job_count for row in result.distribution]
    bars = role_axes.bar(labels, counts, color="#2F6B4F")
    role_axes.set_title("Job Advertisements by Classified Role Group", pad=16)
    role_axes.set_xlabel("Role group (full classifier-input denominator)")
    role_axes.set_ylabel("Job advertisements")
    role_axes.tick_params(axis="x", rotation=30)
    role_axes.grid(axis="y", alpha=0.25)
    role_axes.set_axisbelow(True)
    role_axes.bar_label(bars, padding=3, fontsize=9)
    role_figure.tight_layout()
    role_figure.savefig(role_path, dpi=150, bbox_inches="tight")
    role_figure.clear()

    band_counts = Counter(row.role_confidence_level for row in result.classifications)
    bands = ("high", "medium", "low")
    confidence_figure = Figure(figsize=(8.5, 5.5))
    FigureCanvasAgg(confidence_figure)
    confidence_axes = confidence_figure.subplots()
    confidence_bars = confidence_axes.bar(
        [band.title() for band in bands],
        [band_counts[band] for band in bands],
        color=("#2F6B4F", "#D59B32", "#8A4F54"),
    )
    confidence_axes.set_title("Role Classification Strength Bands", pad=16)
    confidence_axes.set_xlabel("Deterministic confidence/strength band")
    confidence_axes.set_ylabel("Job advertisements")
    confidence_axes.grid(axis="y", alpha=0.25)
    confidence_axes.set_axisbelow(True)
    confidence_axes.bar_label(confidence_bars, padding=3, fontsize=9)
    confidence_figure.tight_layout()
    confidence_figure.savefig(confidence_path, dpi=150, bbox_inches="tight")
    confidence_figure.clear()

    return (
        RoleChartSummary(
            title="Job Advertisements by Classified Role Group",
            path=role_path,
            plotted_items=len(result.distribution),
        ),
        RoleChartSummary(
            title="Role Classification Strength Bands",
            path=confidence_path,
            plotted_items=len(bands),
        ),
    )
