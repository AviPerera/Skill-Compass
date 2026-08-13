"""Test the demo-only synthetic Power BI workbook adapter."""

from pathlib import Path

from skill_compass.adapters.reference_workbook import read_reference_sheet

WORKBOOK = Path(
    "powerbi/reference/Skill_Compass_Final_Synthetic_PowerBI_Dataset_100_Jobs.xlsx"
)


def test_reference_reader_exposes_governed_roadmap_metadata() -> None:
    priorities = read_reference_sheet(WORKBOOK, "vw_pathway_skill_priorities")
    stages = read_reference_sheet(WORKBOOK, "vw_roadmap_stages")

    assert priorities
    assert stages
    assert {
        "pathway_name",
        "skill_name",
        "role_demand_rate",
        "difficulty_score",
    }.issubset(priorities[0])
    assert {"pathway_name", "stage_number", "stage_name", "skill_name"}.issubset(
        stages[0]
    )
