"""Render the two approved Feature 6 seniority-classification charts.

This reporting layer consumes typed results and must not change classifications,
read source data, or implement Power BI presentation logic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from skill_compass.schemas.classification import SeniorityClassificationRunResult

# =============================================================================
# Chart metadata and rendering
# =============================================================================


@dataclass(frozen=True, slots=True)
class SeniorityChartSummary:
    """Describe one saved chart and its plotted population."""

    title: str
    path: Path
    plotted_items: int


def generate_seniority_classification_charts(
    result: SeniorityClassificationRunResult, output_dir: Path
) -> tuple[SeniorityChartSummary, SeniorityChartSummary]:
    """Save calculated seniority counts and confidence-band distributions."""
    output_dir.mkdir(parents=True, exist_ok=True)
    distribution_path = output_dir / "seniority_distribution.png"
    confidence_path = output_dir / "seniority_confidence_distribution.png"

    distribution_figure = Figure(figsize=(10, 6))
    FigureCanvasAgg(distribution_figure)
    distribution_axes = distribution_figure.subplots()
    labels = [row.seniority_label for row in result.distribution]
    counts = [row.job_count for row in result.distribution]
    bars = distribution_axes.bar(labels, counts, color="#315C8C")
    distribution_axes.set_title("Job Advertisements by Seniority Level", pad=16)
    distribution_axes.set_xlabel("Seniority outcome (full cleaned-job denominator)")
    distribution_axes.set_ylabel("Job advertisements")
    distribution_axes.tick_params(axis="x", rotation=20)
    distribution_axes.grid(axis="y", alpha=0.25)
    distribution_axes.set_axisbelow(True)
    distribution_axes.bar_label(bars, padding=3, fontsize=9)
    distribution_figure.tight_layout()
    distribution_figure.savefig(distribution_path, dpi=150, bbox_inches="tight")
    distribution_figure.clear()

    band_counts = Counter(
        row.seniority_confidence_level for row in result.classifications
    )
    bands = ("high", "medium", "low")
    confidence_figure = Figure(figsize=(8.5, 5.5))
    FigureCanvasAgg(confidence_figure)
    confidence_axes = confidence_figure.subplots()
    confidence_bars = confidence_axes.bar(
        [band.title() for band in bands],
        [band_counts[band] for band in bands],
        color=("#315C8C", "#D59B32", "#8A4F54"),
    )
    confidence_axes.set_title("Seniority Classification Strength Bands", pad=16)
    confidence_axes.set_xlabel("Deterministic confidence/strength band")
    confidence_axes.set_ylabel("Job advertisements")
    confidence_axes.grid(axis="y", alpha=0.25)
    confidence_axes.set_axisbelow(True)
    confidence_axes.bar_label(confidence_bars, padding=3, fontsize=9)
    confidence_figure.tight_layout()
    confidence_figure.savefig(confidence_path, dpi=150, bbox_inches="tight")
    confidence_figure.clear()

    return (
        SeniorityChartSummary(
            title="Job Advertisements by Seniority Level",
            path=distribution_path,
            plotted_items=len(result.distribution),
        ),
        SeniorityChartSummary(
            title="Seniority Classification Strength Bands",
            path=confidence_path,
            plotted_items=len(bands),
        ),
    )
