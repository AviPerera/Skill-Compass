"""Validate the tracked 26-view Power BI contract metadata.

These tests inspect only the synthetic workbook's schema metadata. They must
not treat synthetic fact rows as market evidence or modify the workbook.
"""

from pathlib import Path

from skill_compass.exports.powerbi_contract import (
    EXPECTED_POWERBI_VIEW_NAMES,
    load_powerbi_contract,
)

WORKBOOK = Path(
    "powerbi/reference/Skill_Compass_Final_Synthetic_PowerBI_Dataset_100_Jobs.xlsx"
)


def test_reference_workbook_exposes_exact_frozen_contract() -> None:
    contract = load_powerbi_contract(WORKBOOK)

    assert contract.view_order == EXPECTED_POWERBI_VIEW_NAMES
    assert len(contract.views) == 26
    assert sum(len(view.columns) for view in contract.views) == 314
    assert len(contract.relationships) == 20
    assert all(
        view.postgresql_view == f"pbi.{view.view_name}" for view in contract.views
    )


def test_jobs_and_skill_bridge_column_order_matches_approved_contract() -> None:
    contract = load_powerbi_contract(WORKBOOK)
    views = {view.view_name: view for view in contract.views}

    assert len(views["vw_jobs"].columns) == 63
    assert tuple(column.column_name for column in views["vw_jobs"].columns[:9]) == (
        "analysis_period_id",
        "period_code",
        "period_name",
        "period_start_date",
        "period_end_date",
        "data_as_of_at",
        "profile_id",
        "profile_code",
        "job_id",
    )
    assert len(views["vw_job_skills"].columns) == 18
