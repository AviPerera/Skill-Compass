"""Render the two approved Feature 3 demonstration charts.

This reporting layer consumes typed channel-neutral summaries and must not
change extraction results, read source data, or implement Power BI visuals.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, median

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from skill_compass.schemas.extraction import ExtractionRunResult

# =============================================================================
# Typed reporting metadata and chart series
# =============================================================================


TOP_SKILLS_TITLE = "Top 15 Extracted Skills in the Adelaide Sample"
SKILLS_DISTRIBUTION_TITLE = "Distribution of Detected Skills per Job Advertisement"


@dataclass(frozen=True, slots=True)
class ChartSummary:
    """Describe one generated graph and its accessible terminal interpretation."""

    title: str
    path: Path
    source_metric: str
    plotted_items: int
    interpretation: str


def top_skill_series(
    result: ExtractionRunResult, limit: int
) -> tuple[tuple[str, int, float], ...]:
    """Return ranked skill names, distinct-job counts, and decimal demand rates."""
    if limit < 1:
        raise ValueError("top skill limit must be at least 1")
    return tuple(
        (
            row.requirement_name,
            row.matched_job_count,
            float(row.demand_rate),
        )
        for row in result.skill_demand[:limit]
    )


def skill_count_distribution(
    result: ExtractionRunResult,
) -> tuple[tuple[int, int], ...]:
    """Return a complete discrete distribution including zero-skill eligible jobs."""
    counts = [
        summary.distinct_skill_count
        for summary in result.job_summaries
        if summary.analytically_eligible
    ]
    frequency = Counter(counts)
    maximum = max(counts, default=0)
    return tuple(
        (skill_count, frequency[skill_count]) for skill_count in range(maximum + 1)
    )


# =============================================================================
# Matplotlib presentation rendering
# =============================================================================


def render_top_skills_chart(
    result: ExtractionRunResult, path: Path, top_skills: int
) -> tuple[Figure, tuple[tuple[str, int, float], ...]]:
    """Render distinct eligible-job counts for the top ranked active skills."""
    series = top_skill_series(result, top_skills)
    names = [item[0] for item in reversed(series)]
    counts = [item[1] for item in reversed(series)]
    figure = Figure(figsize=(11, 7))
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    bars = axes.barh(names, counts, color="#2563A6")
    axes.set_title(TOP_SKILLS_TITLE, fontsize=14, pad=16)
    axes.set_xlabel("Distinct eligible job advertisements")
    axes.grid(axis="x", alpha=0.25)
    axes.set_axisbelow(True)
    axes.bar_label(bars, padding=3, fontsize=9)
    axes.text(
        0.99,
        0.01,
        f"Eligible-job denominator: {result.analytically_eligible_jobs}",
        transform=axes.transAxes,
        ha="right",
        va="bottom",
        fontsize=9,
        color="#404040",
    )
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    return figure, series


def render_skill_distribution_chart(
    result: ExtractionRunResult, path: Path
) -> tuple[Figure, tuple[tuple[int, int], ...], float, float]:
    """Render the discrete detected-skill distribution for all eligible jobs."""
    distribution = skill_count_distribution(result)
    skill_counts = [item[0] for item in distribution]
    job_counts = [item[1] for item in distribution]
    eligible_values = [
        summary.distinct_skill_count
        for summary in result.job_summaries
        if summary.analytically_eligible
    ]
    average = mean(eligible_values) if eligible_values else 0.0
    midpoint = median(eligible_values) if eligible_values else 0.0

    figure = Figure(figsize=(10, 6))
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    bars = axes.bar(skill_counts, job_counts, color="#3B7D5B", width=0.8)
    axes.set_title(SKILLS_DISTRIBUTION_TITLE, fontsize=14, pad=16)
    axes.set_xlabel("Distinct detected skills per eligible job")
    axes.set_ylabel("Eligible job advertisements")
    axes.set_xticks(skill_counts)
    axes.grid(axis="y", alpha=0.25)
    axes.set_axisbelow(True)
    axes.bar_label(bars, padding=3, fontsize=9)
    axes.text(
        0.98,
        0.95,
        f"Average: {average:.2f}\nMedian: {midpoint:g}",
        transform=axes.transAxes,
        ha="right",
        va="top",
        bbox={"boxstyle": "round", "facecolor": "white", "alpha": 0.8},
    )
    figure.tight_layout()
    figure.savefig(path, dpi=150, bbox_inches="tight")
    return figure, distribution, average, midpoint


def generate_extraction_charts(
    result: ExtractionRunResult,
    charts_dir: Path,
    *,
    top_skills: int = 15,
    show_plots: bool = False,
) -> tuple[ChartSummary, ChartSummary]:
    """Save both approved PNGs and optionally show them after successful saving."""
    charts_dir.mkdir(parents=True, exist_ok=True)
    top_path = charts_dir / "top_15_skills_by_job_count.png"
    distribution_path = charts_dir / "skills_per_job_distribution.png"
    top_figure, top_series = render_top_skills_chart(result, top_path, top_skills)
    distribution_figure, distribution, average, midpoint = (
        render_skill_distribution_chart(result, distribution_path)
    )
    if show_plots:
        display_saved_charts(
            (
                (TOP_SKILLS_TITLE, top_path),
                (SKILLS_DISTRIBUTION_TITLE, distribution_path),
            )
        )
    top_figure.clear()
    distribution_figure.clear()

    if top_series and top_series[0][1] > 0:
        top_interpretation = (
            f"{top_series[0][0]} ranked first with {top_series[0][1]} "
            "distinct eligible job advertisements."
        )
    else:
        top_interpretation = "No active skill was detected in an eligible job."
    distribution_interpretation = (
        f"Eligible jobs averaged {average:.2f} detected skills; the median was "
        f"{midpoint:g}, including jobs with zero detected skills."
    )
    return (
        ChartSummary(
            title=TOP_SKILLS_TITLE,
            path=top_path,
            source_metric="distinct eligible-job count per active skill",
            plotted_items=len(top_series),
            interpretation=top_interpretation,
        ),
        ChartSummary(
            title=SKILLS_DISTRIBUTION_TITLE,
            path=distribution_path,
            source_metric="distinct detected skill count per eligible job",
            plotted_items=len(distribution),
            interpretation=distribution_interpretation,
        ),
    )


def display_saved_charts(charts: tuple[tuple[str, Path], ...]) -> None:
    """Open saved PNGs only for an explicit interactive presentation request."""
    try:
        from tkinter import TclError as TkDisplayError
    except ImportError:
        TkDisplayError = RuntimeError

    try:
        import matplotlib.pyplot as plt

        for title, path in charts:
            image = plt.imread(path)
            figure, axes = plt.subplots(figsize=(11, 7))
            axes.imshow(image)
            axes.set_title(title)
            axes.axis("off")
            figure.tight_layout()
        plt.show()
    except (ImportError, OSError, RuntimeError, TkDisplayError) as error:
        raise RuntimeError(
            "interactive plot display is unavailable; PNG files were saved"
        ) from error
