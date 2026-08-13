"""Render the approved static dashboard visual demonstration artifacts.

This reporting module consumes typed Feature 8 results plus explicitly labelled
synthetic roadmap metadata. It must not change analytics, implement Power BI
interactions, query source data, or present synthetic counts as market results.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.figure import Figure
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import PercentFormatter

from skill_compass.adapters.reference_workbook import read_reference_sheet
from skill_compass.schemas.analytics import (
    AnalyticsRunResult,
    SkillDemandMetric,
)

# =============================================================================
# Approved presentation tokens and manifest contract
# =============================================================================


BACKGROUND = "#F7F8F5"
FOREGROUND = "#1F2937"
PRIMARY = "#0F4F2A"
SECONDARY = "#18B78E"
TERTIARY = "#8BD414"
FOURTH = "#20B8B0"
FIFTH = "#F4A300"
MUTED = "#64748B"
PALE = "#DDFCA3"
BORDER = "#E5E7EB"
SERIES = (PRIMARY, SECONDARY, TERTIARY, FOURTH, FIFTH, MUTED)
SENIORITY_ORDER = ("entry_level", "junior", "mid_level", "senior")
STATE_TILE_POSITIONS = {
    "WA": (0, 1),
    "NT": (1, 0),
    "SA": (1, 1),
    "QLD": (2, 0),
    "NSW": (2, 1),
    "VIC": (2, 2),
    "TAS": (2, 3),
    "ACT": (3, 1),
}


@dataclass(frozen=True, slots=True)
class DashboardVisualSummary:
    """Describe one generated visual, provenance, and accessible interpretation."""

    page_number: int
    page_name: str
    visual_name: str
    visual_type: str
    path: Path
    data_source: str
    alt_text: str


def _figure(width: float = 10, height: float = 6) -> Figure:
    """Create one consistently styled non-interactive figure."""
    figure = Figure(figsize=(width, height), facecolor=BACKGROUND)
    FigureCanvasAgg(figure)
    return figure


def _style_axes(axes: object) -> None:
    """Apply the approved foreground, grid, and border treatment."""
    axes.set_facecolor("white")
    axes.tick_params(colors=FOREGROUND, labelsize=10)
    axes.title.set_color(FOREGROUND)
    axes.xaxis.label.set_color(FOREGROUND)
    axes.yaxis.label.set_color(FOREGROUND)
    for spine in axes.spines.values():
        spine.set_color(BORDER)


def _save(figure: Figure, path: Path, alt_text: str) -> None:
    """Save one PNG with embedded description metadata and close its content."""
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path,
        dpi=160,
        facecolor=figure.get_facecolor(),
        bbox_inches="tight",
        metadata={"Description": alt_text},
    )
    figure.clear()


def _no_data(axes: object, title: str) -> None:
    """Render the required explicit empty-state treatment."""
    axes.set_title(title, pad=16, fontweight="bold")
    axes.text(
        0.5,
        0.5,
        "No data for the selected filters",
        ha="center",
        va="center",
        transform=axes.transAxes,
        color=MUTED,
        fontsize=14,
    )
    axes.set_axis_off()


def _percent_label(value: float) -> str:
    """Format a stored decimal rate as a dashboard percentage."""
    return f"{value:.0%}"


# =============================================================================
# Reusable chart primitives
# =============================================================================


def _horizontal_bar(
    *,
    labels: Sequence[str],
    values: Sequence[float],
    title: str,
    axis_title: str,
    path: Path,
    alt_text: str,
    percentage: bool = False,
    color: str = PRIMARY,
) -> None:
    """Render a descending horizontal bar chart with labels and legend."""
    figure = _figure()
    axes = figure.subplots()
    _style_axes(axes)
    if not labels:
        _no_data(axes, title)
        _save(figure, path, alt_text)
        return
    reverse_labels = list(reversed(labels))
    reverse_values = list(reversed(values))
    bars = axes.barh(reverse_labels, reverse_values, color=color, label=axis_title)
    axes.set_title(title, pad=16, fontweight="bold")
    axes.set_xlabel(axis_title)
    axes.set_ylabel("Category")
    axes.set_xlim(left=0)
    if percentage:
        axes.xaxis.set_major_formatter(PercentFormatter(1.0, decimals=0))
    axes.grid(axis="x", alpha=0.2)
    axes.set_axisbelow(True)
    axes.legend(frameon=False, loc="lower right")
    labels_text = (
        [_percent_label(value) for value in reverse_values]
        if percentage
        else [f"{value:,.0f}" for value in reverse_values]
    )
    axes.bar_label(bars, labels=labels_text, padding=4, fontsize=9)
    _save(figure, path, alt_text)


def _column_chart(
    *,
    labels: Sequence[str],
    values: Sequence[float],
    title: str,
    y_axis_title: str,
    path: Path,
    alt_text: str,
    percentage: bool = False,
) -> None:
    """Render a zero-based categorical column chart."""
    figure = _figure()
    axes = figure.subplots()
    _style_axes(axes)
    if not labels:
        _no_data(axes, title)
        _save(figure, path, alt_text)
        return
    bars = axes.bar(labels, values, color=PRIMARY, label=y_axis_title)
    axes.set_title(title, pad=16, fontweight="bold")
    axes.set_xlabel("Category")
    axes.set_ylabel(y_axis_title)
    axes.set_ylim(bottom=0)
    if len(labels) > 6:
        axes.tick_params(axis="x", rotation=25)
        for tick_label in axes.get_xticklabels():
            tick_label.set_horizontalalignment("right")
    axes.grid(axis="y", alpha=0.2)
    axes.set_axisbelow(True)
    axes.legend(frameon=False)
    label_values = (
        [_percent_label(value) for value in values]
        if percentage
        else [f"{value:,.1f}" if value % 1 else f"{value:,.0f}" for value in values]
    )
    axes.bar_label(bars, labels=label_values, padding=4, fontsize=9)
    _save(figure, path, alt_text)


def _donut(
    *,
    labels: Sequence[str],
    values: Sequence[int],
    title: str,
    path: Path,
    alt_text: str,
) -> None:
    """Render a maximum-five-category donut with centre total and percentages."""
    figure = _figure(9, 6)
    axes = figure.subplots()
    _style_axes(axes)
    pairs = [
        (label, value) for label, value in zip(labels, values, strict=True) if value
    ]
    if not pairs:
        _no_data(axes, title)
        _save(figure, path, alt_text)
        return
    if len(pairs) > 5:
        visible = pairs[:4]
        pairs = [*visible, ("Other", sum(value for _, value in pairs[4:]))]
    plot_labels, plot_values = zip(*pairs, strict=True)
    wedges, _, percentage_texts = axes.pie(
        plot_values,
        colors=SERIES[: len(plot_values)],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.38, "edgecolor": "white"},
        autopct=lambda value: f"{value:.0f}%" if value >= 3 else "",
        pctdistance=0.8,
        textprops={"fontsize": 9, "color": FOREGROUND},
    )
    for wedge, percentage_text in zip(wedges, percentage_texts, strict=True):
        red, green, blue, _ = wedge.get_facecolor()
        luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue
        percentage_text.set_color("white" if luminance < 0.5 else FOREGROUND)
        percentage_text.set_fontweight("bold")
    total = sum(plot_values)
    axes.text(
        0, 0.05, f"{total:,}", ha="center", va="center", fontsize=20, fontweight="bold"
    )
    axes.text(
        0,
        -0.14,
        "job advertisements",
        ha="center",
        va="center",
        fontsize=9,
        color=MUTED,
    )
    axes.set_title(title, pad=16, fontweight="bold")
    axes.legend(
        plot_labels,
        title="Category",
        loc="center left",
        bbox_to_anchor=(1, 0.5),
        frameon=False,
    )
    _save(figure, path, alt_text)


def _heatmap(
    *,
    row_labels: Sequence[str],
    column_labels: Sequence[str],
    matrix: Sequence[Sequence[float]],
    title: str,
    path: Path,
    alt_text: str,
) -> None:
    """Render a labelled role-skill demand-rate heatmap with a threshold legend."""
    figure = _figure(12, 7)
    axes = figure.subplots()
    _style_axes(axes)
    if not row_labels or not column_labels:
        _no_data(axes, title)
        _save(figure, path, alt_text)
        return
    colour_map = LinearSegmentedColormap.from_list(
        "skill_compass", ("#ECF8E0", TERTIARY, SECONDARY, PRIMARY)
    )
    image = axes.imshow(matrix, aspect="auto", vmin=0, vmax=1, cmap=colour_map)
    axes.set_title(title, pad=16, fontweight="bold")
    axes.set_xlabel("Role group")
    axes.set_ylabel("Skill")
    axes.set_xticks(range(len(column_labels)), column_labels, rotation=25, ha="right")
    axes.set_yticks(range(len(row_labels)), row_labels)
    for row_index, row in enumerate(matrix):
        for column_index, value in enumerate(row):
            axes.text(
                column_index,
                row_index,
                _percent_label(value),
                ha="center",
                va="center",
                color="white" if value >= 0.5 else FOREGROUND,
                fontsize=8,
            )
    colour_bar = figure.colorbar(image, ax=axes, pad=0.02)
    colour_bar.set_label("Role-specific demand rate")
    _save(figure, path, alt_text)


# =============================================================================
# Page-specific rendering
# =============================================================================


def _top_skills(
    result: AnalyticsRunResult, limit: int = 10
) -> tuple[SkillDemandMetric, ...]:
    """Return the highest-demand governed skills in rank order."""
    return tuple(row for row in result.skill_demand if row.supporting_job_count)[:limit]


def _matrix_data(
    result: AnalyticsRunResult,
    limit: int = 12,
) -> tuple[list[str], list[str], list[list[float]]]:
    """Build a top-skill by governed-role matrix from typed rates."""
    skills = _top_skills(result, limit)
    roles = sorted(result.role_summary, key=lambda row: row.sort_order)
    rate_by_cell = {
        (row.requirement_code, row.role_group_code): float(row.demand_rate)
        for row in result.skill_role_demand
    }
    return (
        [row.requirement_name for row in skills],
        [row.role_group_label for row in roles],
        [
            [
                rate_by_cell.get((skill.requirement_code, role.role_group_code), 0)
                for role in roles
            ]
            for skill in skills
        ],
    )


def _render_skill_table(result: AnalyticsRunResult, path: Path) -> str:
    """Render the required detailed skill-ranking table as a static artifact."""
    rows = _top_skills(result, 15)
    alt_text = (
        f"Skill ranking table showing {len(rows)} ranked skills and their demand rates."
    )
    figure = _figure(12, 7)
    axes = figure.subplots()
    axes.axis("off")
    axes.set_title("Skill Ranking Table", pad=20, fontweight="bold", color=FOREGROUND)
    cell_text = [
        [
            row.rank_overall,
            row.requirement_name,
            row.category_name,
            f"{float(row.demand_rate):.0%}",
            f"{row.supporting_job_count:,}",
        ]
        for row in rows
    ]
    table = axes.table(
        cellText=cell_text,
        colLabels=("Rank", "Skill", "Category", "Demand Rate", "Job Ads"),
        colWidths=(0.08, 0.27, 0.31, 0.17, 0.13),
        loc="center",
        cellLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.45)
    for (row_index, _), cell in table.get_celld().items():
        cell.set_edgecolor(BORDER)
        if row_index == 0:
            cell.set_facecolor(PRIMARY)
            cell.set_text_props(color="white", weight="bold")
        elif row_index % 2 == 0:
            cell.set_facecolor("#F0F5EE")
    _save(figure, path, alt_text)
    return alt_text


def _render_role_profiles(result: AnalyticsRunResult, path: Path) -> str:
    """Render role-skill demand plus concise data-derived role profiles."""
    row_labels, column_labels, matrix = _matrix_data(result, 8)
    alt_text = "Role by skill heatmap with each role's three highest-demand skills."
    figure = _figure(14, 8)
    grid = figure.add_gridspec(1, 2, width_ratios=(1.7, 1), wspace=0.25)
    axes = figure.add_subplot(grid[0, 0])
    profile_axes = figure.add_subplot(grid[0, 1])
    _style_axes(axes)
    profile_axes.axis("off")
    if row_labels and column_labels:
        colour_map = LinearSegmentedColormap.from_list(
            "role_profiles", ("#ECF8E0", TERTIARY, SECONDARY, PRIMARY)
        )
        axes.imshow(matrix, aspect="auto", vmin=0, vmax=1, cmap=colour_map)
        axes.set_xticks(
            range(len(column_labels)), column_labels, rotation=25, ha="right"
        )
        axes.set_yticks(range(len(row_labels)), row_labels)
        axes.set_xlabel("Role group")
        axes.set_ylabel("Skill")
        for row_index, row in enumerate(matrix):
            for column_index, value in enumerate(row):
                axes.text(
                    column_index,
                    row_index,
                    _percent_label(value),
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white" if value >= 0.5 else FOREGROUND,
                )
    else:
        _no_data(axes, "Role x Skill Matrix")
    axes.set_title("Role x Skill Matrix", pad=16, fontweight="bold")
    profile_axes.set_title("Role Profiles", pad=16, fontweight="bold", color=FOREGROUND)
    by_role: dict[str, list[object]] = defaultdict(list)
    for row in result.skill_role_demand:
        if row.supporting_job_count:
            by_role[row.role_group_label].append(row)
    y_position = 0.96
    for role in sorted(result.role_summary, key=lambda row: row.sort_order):
        top = sorted(
            by_role[role.role_group_label],
            key=lambda row: (-row.demand_rate, row.requirement_name),
        )[:3]
        profile_axes.text(
            0.02,
            y_position,
            role.role_group_label,
            transform=profile_axes.transAxes,
            fontweight="bold",
            color=PRIMARY,
            va="top",
        )
        y_position -= 0.045
        profile_axes.text(
            0.02,
            y_position,
            ", ".join(row.requirement_name for row in top) or "No detected skills",
            transform=profile_axes.transAxes,
            color=FOREGROUND,
            va="top",
            wrap=True,
            fontsize=9,
        )
        y_position -= 0.13
    _save(figure, path, alt_text)
    return alt_text


def _render_seniority_split(result: AnalyticsRunResult, path: Path) -> str:
    """Render a 100-percent stacked governed role-seniority comparison."""
    alt_text = (
        "One hundred percent stacked columns comparing seniority distribution by role."
    )
    figure = _figure(12, 7)
    axes = figure.subplots()
    _style_axes(axes)
    roles = sorted(result.role_summary, key=lambda row: row.sort_order)
    levels = sorted(
        {
            (row.seniority_rank, row.seniority_code, row.seniority_label)
            for row in result.role_seniority
        }
    )
    bottoms = [0.0] * len(roles)
    for index, (_, code, label) in enumerate(levels):
        values = [
            float(
                next(
                    row.role_rate
                    for row in result.role_seniority
                    if row.role_group_code == role.role_group_code
                    and row.seniority_code == code
                )
            )
            for role in roles
        ]
        bars = axes.bar(
            [role.role_group_label for role in roles],
            values,
            bottom=bottoms,
            color=SERIES[index % len(SERIES)],
            label=label,
        )
        axes.bar_label(
            bars,
            labels=[_percent_label(value) if value >= 0.08 else "" for value in values],
            label_type="center",
            fontsize=8,
        )
        bottoms = [
            bottom + value for bottom, value in zip(bottoms, values, strict=True)
        ]
    classified_counts = {
        row.role_group_code: row.role_job_count for row in result.role_seniority
    }
    for index, role in enumerate(roles):
        if classified_counts.get(role.role_group_code, 0) == 0:
            axes.text(
                index,
                0.5,
                "No classified\ndata",
                ha="center",
                va="center",
                color=MUTED,
                fontsize=9,
            )
    axes.set_title("Seniority Split by Role", pad=16, fontweight="bold")
    axes.set_xlabel("Role group")
    axes.set_ylabel("Share of classified role advertisements")
    axes.set_ylim(0, 1)
    axes.tick_params(axis="x", rotation=20)
    axes.legend(title="Seniority level", frameon=False, ncol=4, loc="upper center")
    _save(figure, path, alt_text)
    return alt_text


def _render_tile_map(result: AnalyticsRunResult, path: Path) -> str:
    """Render an intentionally schematic Australian state demand tile map."""
    alt_text = "Schematic Australian tile map showing included job counts and demand bands by state."
    figure = _figure(10, 7)
    axes = figure.subplots()
    axes.set_facecolor("white")
    values = {row.dimension_code: row.job_count for row in result.state_distribution}
    maximum = max((values.get(code, 0) for code in STATE_TILE_POSITIONS), default=0)
    for code, (column, row) in STATE_TILE_POSITIONS.items():
        count = values.get(code, 0)
        ratio = count / maximum if maximum else 0
        if count == 0:
            color = "#E5E7EB"
        elif ratio >= 0.75:
            color = PRIMARY
        elif ratio >= 0.5:
            color = SECONDARY
        elif ratio >= 0.25:
            color = TERTIARY
        else:
            color = "#CDEBB0"
        axes.add_patch(
            Rectangle(
                (column, -row),
                0.9,
                0.9,
                facecolor=color,
                edgecolor="white",
                linewidth=3,
            )
        )
        axes.text(
            column + 0.45,
            -row + 0.57,
            code,
            ha="center",
            va="center",
            fontweight="bold",
            color="white" if color in {PRIMARY, SECONDARY} else FOREGROUND,
        )
        axes.text(
            column + 0.45,
            -row + 0.30,
            f"{count:,}" if count else "No data",
            ha="center",
            va="center",
            fontsize=9,
            color="white" if color in {PRIMARY, SECONDARY} else FOREGROUND,
        )
    axes.set_xlim(-0.2, 4.1)
    axes.set_ylim(-3.2, 1.2)
    axes.set_aspect("equal")
    axes.axis("off")
    axes.set_title(
        "Australia Job Demand Map", pad=16, fontweight="bold", color=FOREGROUND
    )
    axes.legend(
        handles=(
            Patch(color=PRIMARY, label="Very high"),
            Patch(color=SECONDARY, label="High"),
            Patch(color=TERTIARY, label="Moderate"),
            Patch(color="#CDEBB0", label="Lower"),
            Patch(color="#E5E7EB", label="No data"),
        ),
        title="Demand band",
        frameon=False,
        loc="lower left",
    )
    _save(figure, path, alt_text)
    return alt_text


def _render_priority_matrix(reference_workbook: Path, path: Path) -> str:
    """Render the approved synthetic/provisional demand-difficulty matrix."""
    rows = read_reference_sheet(reference_workbook, "vw_pathway_skill_priorities")
    pathway = next((row["pathway_name"] for row in rows if row["pathway_name"]), "")
    selected = [row for row in rows if row["pathway_name"] == pathway][:12]
    alt_text = f"Synthetic priority matrix for {pathway or 'the reference pathway'} comparing demand and expert difficulty."
    figure = _figure(11, 7)
    axes = figure.subplots()
    _style_axes(axes)
    if not selected:
        _no_data(axes, "Skill Priority Matrix - Synthetic Reference")
        _save(figure, path, alt_text)
        return alt_text
    x_values = [float(row["difficulty_score"]) for row in selected]
    y_values = [float(row["role_demand_rate"]) for row in selected]
    axes.axvline(3, color=MUTED, linestyle="--", linewidth=1)
    axes.axhline(0.5, color=MUTED, linestyle="--", linewidth=1)
    axes.scatter(
        x_values, y_values, s=85, color=PRIMARY, label="Synthetic pathway skill"
    )
    label_offsets = {
        "Stakeholder Management": (5, 18),
        "Statistics": (5, -12),
    }
    for row, x_value, y_value in zip(selected, x_values, y_values, strict=True):
        axes.annotate(
            row["skill_name"],
            (x_value, y_value),
            xytext=label_offsets.get(row["skill_name"], (5, 5)),
            textcoords="offset points",
            fontsize=8,
            bbox={"facecolor": BACKGROUND, "edgecolor": "none", "pad": 0.5},
        )
    axes.text(1.1, 0.93, "Learn First", color=PRIMARY, fontweight="bold")
    axes.text(4.1, 0.93, "Build Next", color=PRIMARY, fontweight="bold")
    axes.text(1.1, 0.08, "Nice to Have", color=MUTED, fontweight="bold")
    axes.text(4.1, 0.08, "Advanced", color=MUTED, fontweight="bold")
    axes.set_xlim(1, 5)
    axes.set_ylim(0, 1.05)
    axes.set_xlabel("Learning difficulty (lower to higher)")
    axes.set_ylabel("Demand (low to high)")
    axes.set_title(
        f"Skill Priority Matrix - {pathway} (Synthetic Reference)",
        pad=16,
        fontweight="bold",
    )
    axes.legend(frameon=False)
    _save(figure, path, alt_text)
    return alt_text


def _render_combinations(result: AnalyticsRunResult, path: Path) -> str:
    """Render the top graduate-friendly role pair combinations."""
    rows = [
        row
        for row in result.skill_combinations
        if row.scope_code == "data_analyst"
        and row.graduate_friendly_flag
        and row.combination_size == 2
    ][:10]
    if not rows:
        rows = [
            row
            for row in result.skill_combinations
            if row.scope_code == "all" and row.combination_size == 2
        ][:10]
    alt_text = f"Top {len(rows)} skill pairs ranked by distinct-job prevalence in the selected cohort."
    _horizontal_bar(
        labels=[row.combination_label for row in rows],
        values=[float(row.job_percentage) for row in rows],
        title="Top Skill Combinations",
        axis_title="Share of cohort advertisements (%)",
        path=path,
        alt_text=alt_text,
        percentage=True,
    )
    return alt_text


def _render_roadmap(reference_workbook: Path, path: Path) -> str:
    """Render four connected synthetic learning-roadmap stage cards."""
    rows = read_reference_sheet(reference_workbook, "vw_roadmap_stages")
    pathway = next((row["pathway_name"] for row in rows if row["pathway_name"]), "")
    selected = [row for row in rows if row["pathway_name"] == pathway]
    grouped: dict[int, dict[str, object]] = {}
    for row in selected:
        stage_number = int(float(row["stage_number"]))
        stage = grouped.setdefault(
            stage_number,
            {
                "name": row["stage_name"],
                "purpose": row["stage_purpose"],
                "skills": [],
            },
        )
        stage["skills"].append(row["skill_name"])
    alt_text = f"Synthetic four-stage learning roadmap for {pathway or 'the reference pathway'}."
    figure = _figure(14, 5.5)
    axes = figure.subplots()
    axes.set_xlim(0, 4)
    axes.set_ylim(0, 1)
    axes.axis("off")
    axes.set_title(
        f"Learning Roadmap - {pathway} (Synthetic Reference)",
        pad=20,
        fontweight="bold",
        color=FOREGROUND,
    )
    for index in range(1, 5):
        stage = grouped.get(
            index, {"name": f"Stage {index}", "purpose": "No metadata", "skills": []}
        )
        x_value = index - 1 + 0.05
        axes.add_patch(
            Rectangle(
                (x_value, 0.2),
                0.82,
                0.6,
                facecolor="white",
                edgecolor=PRIMARY,
                linewidth=2,
            )
        )
        axes.text(
            x_value + 0.08,
            0.70,
            f"0{index}  {stage['name']}",
            color=PRIMARY,
            fontweight="bold",
            fontsize=11,
        )
        axes.text(
            x_value + 0.08,
            0.57,
            str(stage["purpose"]),
            color=FOREGROUND,
            fontsize=9,
            wrap=True,
        )
        axes.text(
            x_value + 0.08,
            0.31,
            "\n".join(stage["skills"][:4]),
            color=MUTED,
            fontsize=8,
            va="bottom",
        )
        if index < 4:
            axes.annotate(
                "",
                xy=(x_value + 1.00, 0.5),
                xytext=(x_value + 0.84, 0.5),
                arrowprops={"arrowstyle": "->", "color": SECONDARY, "lw": 2},
            )
    _save(figure, path, alt_text)
    return alt_text


def _render_workflow(path: Path) -> str:
    """Render the approved six-stage implemented methodology workflow."""
    stages = (
        "Raw Job\nAdvertisements",
        "Data\nCleaning",
        "Skill\nExtraction",
        "Data\nAnalysis",
        "Dashboard\nVisuals",
        "Graduate\nRoadmap",
    )
    alt_text = "Six-stage workflow from raw job advertisements through cleaning, extraction, analysis, dashboard visuals, and graduate roadmap."
    figure = _figure(14, 4.5)
    axes = figure.subplots()
    axes.set_xlim(0, 6)
    axes.set_ylim(0, 1)
    axes.axis("off")
    axes.set_title(
        "Data Analysis Workflow", pad=20, fontweight="bold", color=FOREGROUND
    )
    for index, stage in enumerate(stages):
        x_value = index + 0.06
        axes.add_patch(
            Rectangle(
                (x_value, 0.3),
                0.78,
                0.45,
                facecolor="white",
                edgecolor=SERIES[index],
                linewidth=2,
            )
        )
        axes.text(
            x_value + 0.39,
            0.60,
            f"0{index + 1}",
            ha="center",
            va="center",
            fontweight="bold",
            color=SERIES[index],
        )
        axes.text(
            x_value + 0.39,
            0.43,
            stage,
            ha="center",
            va="center",
            color=FOREGROUND,
            fontsize=9,
        )
        if index < len(stages) - 1:
            axes.annotate(
                "",
                xy=(x_value + 0.98, 0.52),
                xytext=(x_value + 0.80, 0.52),
                arrowprops={"arrowstyle": "->", "color": MUTED, "lw": 1.8},
            )
    axes.legend(
        handles=(
            Patch(
                color=PRIMARY,
                label="Implemented local pipeline and static visual demonstration",
            ),
        ),
        frameon=False,
        loc="lower center",
    )
    _save(figure, path, alt_text)
    return alt_text


# =============================================================================
# Complete approved visual inventory
# =============================================================================


def generate_dashboard_visuals(
    result: AnalyticsRunResult,
    output_dir: Path,
    reference_workbook: Path,
) -> tuple[DashboardVisualSummary, ...]:
    """Generate all 22 approved primary visual artifacts and their manifest."""
    summaries: list[DashboardVisualSummary] = []

    def add(
        page: int,
        page_name: str,
        name: str,
        kind: str,
        filename: str,
        source: str,
        alt: str,
    ) -> None:
        summaries.append(
            DashboardVisualSummary(
                page,
                page_name,
                name,
                kind,
                output_dir / f"page_{page}" / filename,
                source,
                alt,
            )
        )

    top = _top_skills(result)
    path = output_dir / "page_1/top_10_in_demand_skills.png"
    alt = f"Top {len(top)} skills ranked by advertisement mention rate among included jobs."
    _horizontal_bar(
        labels=[row.requirement_name for row in top],
        values=[float(row.demand_rate) for row in top],
        title="Top 10 In-Demand Skills",
        axis_title="Demand rate (%)",
        path=path,
        alt_text=alt,
        percentage=True,
    )
    add(
        1,
        "Executive Summary",
        "Top 10 In-Demand Skills",
        "Horizontal bar",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    roles = sorted(
        result.role_summary, key=lambda row: (-row.job_count, row.sort_order)
    )
    path = output_dir / "page_1/job_ads_by_role_category.png"
    alt = "Role-category share among included jobs with a governed dashboard role."
    _donut(
        labels=[row.role_group_label for row in roles],
        values=[row.job_count for row in roles],
        title="Job Ads by Role Category",
        path=path,
        alt_text=alt,
    )
    add(
        1,
        "Executive Summary",
        "Job Ads by Role Category",
        "Donut",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    seniority = result.seniority_distribution
    seniority_counts = {row.dimension_code: row.job_count for row in seniority}
    seniority_labels = {row.dimension_code: row.dimension_label for row in seniority}
    path = output_dir / "page_1/seniority_level_breakdown.png"
    alt = "Job advertisement counts in the governed Entry-level, Junior, Mid-level, and Senior order."
    _column_chart(
        labels=[seniority_labels.get(code, code) for code in SENIORITY_ORDER],
        values=[seniority_counts.get(code, 0) for code in SENIORITY_ORDER],
        title="Seniority Level Breakdown",
        y_axis_title="Job advertisements",
        path=path,
        alt_text=alt,
    )
    add(
        1,
        "Executive Summary",
        "Seniority Level Breakdown",
        "Column",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    states = result.state_distribution
    path = output_dir / "page_1/jobs_by_state.png"
    alt = "Included job advertisement counts ranked by Australian state or territory."
    _horizontal_bar(
        labels=[row.dimension_label for row in states],
        values=[row.job_count for row in states],
        title="Jobs by State",
        axis_title="Job advertisements",
        path=path,
        alt_text=alt,
    )
    add(
        1,
        "Executive Summary",
        "Jobs by State",
        "Horizontal bar",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    employment = result.employment_type_distribution
    path = output_dir / "page_1/employment_type_distribution.png"
    alt = "Primary employment-type distribution among included jobs."
    _donut(
        labels=[row.dimension_label for row in employment],
        values=[row.job_count for row in employment],
        title="Employment Type Distribution",
        path=path,
        alt_text=alt,
    )
    add(
        1,
        "Executive Summary",
        "Employment Type Distribution",
        "Donut",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    technical = tuple(
        row
        for row in result.skill_demand
        if row.dashboard_group == "Technical Skills" and row.supporting_job_count
    )[:12]
    soft = tuple(
        row
        for row in result.skill_demand
        if row.dashboard_group == "Soft Skills" and row.supporting_job_count
    )[:12]
    for rows, name, filename in (
        (technical, "Technical Skills - Demand %", "technical_skills_demand.png"),
        (soft, "Soft Skills - Demand %", "soft_skills_demand.png"),
    ):
        path = output_dir / "page_2" / filename
        alt = f"{name} ranked by distinct included-job mention rate."
        _horizontal_bar(
            labels=[row.requirement_name for row in rows],
            values=[float(row.demand_rate) for row in rows],
            title=name,
            axis_title="Demand rate (%)",
            path=path,
            alt_text=alt,
            percentage=True,
        )
        add(
            2,
            "Skills Analysis",
            name,
            "Horizontal bar",
            path.name,
            "National Feature 8 analytics",
            alt,
        )
    row_labels, column_labels, matrix = _matrix_data(result)
    path = output_dir / "page_2/skill_role_matrix.png"
    alt = "Heatmap of top-skill demand rates within each governed role population."
    _heatmap(
        row_labels=row_labels,
        column_labels=column_labels,
        matrix=matrix,
        title="Skill x Role Matrix",
        path=path,
        alt_text=alt,
    )
    add(
        2,
        "Skills Analysis",
        "Skill x Role Matrix",
        "Heatmap matrix",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_2/skill_ranking_table.png"
    alt = _render_skill_table(result, path)
    add(
        2,
        "Skills Analysis",
        "Skill Ranking Table",
        "Table",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    path = output_dir / "page_3/role_skill_matrix_and_profiles.png"
    alt = _render_role_profiles(result, path)
    add(
        3,
        "Role Analysis",
        "Role x Skill Matrix + Role Profiles",
        "Heatmap and text panel",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_3/job_ads_by_role.png"
    alt = "Governed role groups ranked by included job advertisement count."
    _horizontal_bar(
        labels=[row.role_group_label for row in roles],
        values=[row.job_count for row in roles],
        title="Job Ads by Role",
        axis_title="Job advertisements",
        path=path,
        alt_text=alt,
    )
    add(
        3,
        "Role Analysis",
        "Job Ads by Role",
        "Horizontal bar",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    ordered_roles = sorted(result.role_summary, key=lambda row: row.sort_order)
    path = output_dir / "page_3/average_skills_required_by_role.png"
    alt = (
        "Average distinct detected skills per included advertisement by governed role."
    )
    _column_chart(
        labels=[row.role_group_label for row in ordered_roles],
        values=[float(row.average_distinct_skills) for row in ordered_roles],
        title="Average Skills Required by Role",
        y_axis_title="Average detected skills per advertisement",
        path=path,
        alt_text=alt,
    )
    add(
        3,
        "Role Analysis",
        "Average Skills Required by Role",
        "Column",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_3/seniority_split.png"
    alt = _render_seniority_split(result, path)
    add(
        3,
        "Role Analysis",
        "Seniority Split",
        "100% stacked column",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    path = output_dir / "page_4/australia_job_demand_map.png"
    alt = _render_tile_map(result, path)
    add(
        4,
        "Location Insights",
        "Australia Job Demand Map",
        "Tile map",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_4/jobs_by_state.png"
    alt = "Included job advertisement counts ranked by state or territory."
    _horizontal_bar(
        labels=[row.dimension_label for row in states],
        values=[row.job_count for row in states],
        title="Jobs by State",
        axis_title="Job advertisements",
        path=path,
        alt_text=alt,
    )
    add(
        4,
        "Location Insights",
        "Jobs by State",
        "Horizontal bar",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    cities = result.city_distribution[:12]
    path = output_dir / "page_4/jobs_by_city.png"
    alt = "Top cities ranked by included job advertisement count."
    _column_chart(
        labels=[row.dimension_label for row in cities],
        values=[row.job_count for row in cities],
        title="Jobs by City",
        y_axis_title="Job advertisements",
        path=path,
        alt_text=alt,
    )
    add(
        4,
        "Location Insights",
        "Jobs by City",
        "Column",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    work_modes = result.work_mode_distribution
    path = output_dir / "page_4/work_arrangement.png"
    alt = "Work arrangement distribution among included jobs."
    _donut(
        labels=[row.dimension_label for row in work_modes],
        values=[row.job_count for row in work_modes],
        title="Work Arrangement",
        path=path,
        alt_text=alt,
    )
    add(
        4,
        "Location Insights",
        "Work Arrangement",
        "Donut",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_4/employment_type.png"
    alt = "Primary employment-type distribution among included jobs."
    _donut(
        labels=[row.dimension_label for row in employment],
        values=[row.job_count for row in employment],
        title="Employment Type",
        path=path,
        alt_text=alt,
    )
    add(
        4,
        "Location Insights",
        "Employment Type",
        "Donut",
        path.name,
        "National Feature 8 analytics",
        alt,
    )

    path = output_dir / "page_5/skill_priority_matrix.png"
    alt = _render_priority_matrix(reference_workbook, path)
    add(
        5,
        "Graduate Roadmap",
        "Skill Priority Matrix",
        "Quadrant scatter",
        path.name,
        "Synthetic Power BI reference metadata",
        alt,
    )
    path = output_dir / "page_5/top_skill_combinations.png"
    alt = _render_combinations(result, path)
    add(
        5,
        "Graduate Roadmap",
        "Top Skill Combinations",
        "Horizontal bar",
        path.name,
        "National Feature 8 analytics",
        alt,
    )
    path = output_dir / "page_5/learning_roadmap.png"
    alt = _render_roadmap(reference_workbook, path)
    add(
        5,
        "Graduate Roadmap",
        "Learning Roadmap",
        "Stage cards",
        path.name,
        "Synthetic Power BI reference metadata",
        alt,
    )

    path = output_dir / "page_6/data_analysis_workflow.png"
    alt = _render_workflow(path)
    add(
        6,
        "Methodology",
        "Data Analysis Workflow",
        "Process flow",
        path.name,
        "Implemented project workflow",
        alt,
    )

    manifest_path = output_dir / "dashboard_visual_manifest.json"
    manifest_path.write_text(
        json.dumps(
            [{**asdict(summary), "path": str(summary.path)} for summary in summaries],
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return tuple(summaries)
