"""Render the two approved Feature 7 profile-relevance charts.

This reporting layer consumes typed production results and must not alter
decisions, read source data, or implement Power BI presentation logic.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from skill_compass.schemas.classification import ProfileRelevanceRunResult

# =============================================================================
# Chart metadata and rendering
# =============================================================================


@dataclass(frozen=True, slots=True)
class ProfileRelevanceChartSummary:
    """Describe one saved chart and the number of plotted categories."""

    title: str
    path: Path
    plotted_items: int


def generate_profile_relevance_charts(
    result: ProfileRelevanceRunResult, output_dir: Path
) -> tuple[ProfileRelevanceChartSummary, ProfileRelevanceChartSummary]:
    """Save the relevance distribution and non-empty Review-reason counts."""
    output_dir.mkdir(parents=True, exist_ok=True)
    distribution_path = output_dir / "profile_relevance_distribution.png"
    reasons_path = output_dir / "top_review_reasons.png"

    statuses = ("included", "excluded", "review")
    status_counts = Counter(row.relevance_status for row in result.classifications)
    distribution_figure = Figure(figsize=(8.5, 5.5))
    FigureCanvasAgg(distribution_figure)
    distribution_axes = distribution_figure.subplots()
    bars = distribution_axes.bar(
        [status.title() for status in statuses],
        [status_counts[status] for status in statuses],
        color=("#2F6B4F", "#8A4F54", "#D59B32"),
        label="Job advertisements",
    )
    distribution_axes.set_title("Profile Relevance Distribution", pad=16)
    distribution_axes.set_xlabel("Profile relevance status")
    distribution_axes.set_ylabel("Job advertisements")
    distribution_axes.legend()
    distribution_axes.grid(axis="y", alpha=0.25)
    distribution_axes.set_axisbelow(True)
    distribution_axes.bar_label(bars, padding=3, fontsize=9)
    distribution_figure.tight_layout()
    distribution_figure.savefig(distribution_path, dpi=150, bbox_inches="tight")
    distribution_figure.clear()

    reason_counts = Counter(
        row.relevance_reason_code
        for row in result.classifications
        if row.relevance_review_flag
    )
    ordered_reasons = sorted(
        reason_counts.items(), key=lambda item: (-item[1], item[0])
    )[:10]
    reason_labels = [reason.replace("_", " ").title() for reason, _ in ordered_reasons]
    reason_values = [count for _, count in ordered_reasons]
    reasons_figure = Figure(figsize=(10, 6))
    FigureCanvasAgg(reasons_figure)
    reasons_axes = reasons_figure.subplots()
    if ordered_reasons:
        reason_bars = reasons_axes.barh(
            reason_labels[::-1], reason_values[::-1], color="#D59B32"
        )
        reasons_axes.bar_label(reason_bars, padding=3, fontsize=9)
    else:
        reasons_axes.text(
            0.5,
            0.5,
            "No Review cases",
            ha="center",
            va="center",
            transform=reasons_axes.transAxes,
        )
    reasons_axes.set_title("Top Profile Relevance Review Reasons", pad=16)
    reasons_axes.set_xlabel("Review job advertisements")
    reasons_axes.set_ylabel("Review reason")
    reasons_axes.grid(axis="x", alpha=0.25)
    reasons_axes.set_axisbelow(True)
    reasons_figure.tight_layout()
    reasons_figure.savefig(reasons_path, dpi=150, bbox_inches="tight")
    reasons_figure.clear()

    return (
        ProfileRelevanceChartSummary(
            title="Profile Relevance Distribution",
            path=distribution_path,
            plotted_items=len(statuses),
        ),
        ProfileRelevanceChartSummary(
            title="Top Profile Relevance Review Reasons",
            path=reasons_path,
            plotted_items=len(ordered_reasons),
        ),
    )
