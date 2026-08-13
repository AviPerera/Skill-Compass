"""Load and validate the frozen Power BI workbook contract.

This export-layer module treats the tracked workbook metadata as a controlled
interface. It must not read synthetic fact values, calculate analytics, or
write JSON and Excel artifacts.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from uuid import UUID

from pydantic import ValidationError

from skill_compass.adapters.reference_workbook import read_reference_sheet
from skill_compass.schemas.powerbi import (
    PowerBiColumnContract,
    PowerBiContract,
    PowerBiExportDocument,
    PowerBiRelationshipContract,
    PowerBiViewContract,
)

# =============================================================================
# Frozen view inventory and row grains
# =============================================================================


EXPECTED_POWERBI_VIEW_NAMES = (
    "vw_dim_analysis_period",
    "vw_dim_profile",
    "vw_dim_date",
    "vw_dim_roles",
    "vw_dim_seniority",
    "vw_dim_geography",
    "vw_dim_employment_types",
    "vw_dim_work_modes",
    "vw_dim_skills",
    "vw_dim_pathways",
    "vw_jobs",
    "vw_job_skills",
    "vw_job_locations",
    "vw_job_employment_types",
    "vw_job_work_modes",
    "vw_pathway_skill_priorities",
    "vw_skill_combinations",
    "vw_role_profiles",
    "vw_roadmap_stages",
    "vw_methodology_steps",
    "vw_pipeline_metrics",
    "vw_data_quality_metrics",
    "vw_validation_metrics",
    "vw_technology_tools",
    "vw_limitations",
    "vw_project_metadata",
)
EXPECTED_COLUMN_COUNT = 314
EXPECTED_RELATIONSHIP_COUNT = 20
UNIQUE_GRAINS = {
    "vw_dim_analysis_period": ("analysis_period_id",),
    "vw_dim_profile": ("profile_id",),
    "vw_dim_date": ("date_key",),
    "vw_dim_roles": ("role_group_id",),
    "vw_dim_seniority": ("seniority_level_id",),
    "vw_dim_geography": ("geography_id",),
    "vw_dim_employment_types": ("employment_type_id",),
    "vw_dim_work_modes": ("work_mode_id",),
    "vw_dim_skills": ("skill_id",),
    "vw_dim_pathways": ("pathway_id",),
    "vw_jobs": ("job_id",),
    "vw_job_skills": ("analysis_period_id", "job_version_id", "skill_id"),
    "vw_job_locations": ("analysis_period_id", "job_version_id", "geography_id"),
    "vw_job_employment_types": (
        "analysis_period_id",
        "job_version_id",
        "employment_type_id",
    ),
    "vw_job_work_modes": (
        "analysis_period_id",
        "job_version_id",
        "work_mode_id",
    ),
    "vw_pathway_skill_priorities": (
        "analysis_period_id",
        "pathway_id",
        "skill_id",
    ),
    "vw_skill_combinations": (
        "analysis_period_id",
        "pathway_id",
        "combination_label",
    ),
    "vw_role_profiles": ("profile_id", "role_group_id"),
    "vw_roadmap_stages": ("profile_id", "roadmap_stage_id", "skill_id"),
    "vw_methodology_steps": ("profile_id", "step_code"),
    "vw_pipeline_metrics": ("run_id", "step_code"),
    "vw_data_quality_metrics": (
        "run_id",
        "metric_code",
        "dimension_name",
        "dimension_value",
    ),
    "vw_validation_metrics": ("profile_id", "component_name", "metric_name"),
    "vw_technology_tools": ("profile_id", "tool_name"),
    "vw_limitations": ("profile_id", "limitation_code"),
    "vw_project_metadata": ("profile_id",),
}


class PowerBiContractError(ValueError):
    """Report a frozen-contract or exported-data mismatch."""


def _yes_no(value: str, label: str) -> bool:
    """Parse an explicit Yes/No workbook metadata value."""
    if value == "Yes":
        return True
    if value == "No":
        return False
    raise PowerBiContractError(f"invalid {label} value in Data_Dictionary")


# =============================================================================
# Contract loading
# =============================================================================


def load_powerbi_contract(path: Path) -> PowerBiContract:
    """Load exactly the approved 26-view workbook metadata contract."""
    dictionary_rows = read_reference_sheet(path, "Data_Dictionary")
    summary_rows = read_reference_sheet(path, "Model_Summary")
    relationship_rows = read_reference_sheet(path, "Model_Relationships")
    if len(dictionary_rows) != EXPECTED_COLUMN_COUNT:
        raise PowerBiContractError("Power BI contract must contain 314 columns")
    if len(relationship_rows) != EXPECTED_RELATIONSHIP_COUNT:
        raise PowerBiContractError("Power BI contract must contain 20 relationships")

    summary_by_name = {row["excel_table_name"]: row for row in summary_rows}
    if set(summary_by_name) != set(EXPECTED_POWERBI_VIEW_NAMES):
        raise PowerBiContractError("Power BI workbook view inventory has changed")

    columns_by_view: dict[str, list[PowerBiColumnContract]] = {
        name: [] for name in EXPECTED_POWERBI_VIEW_NAMES
    }
    for row in dictionary_rows:
        view_name = row["excel_table_name"]
        if view_name not in columns_by_view:
            raise PowerBiContractError(f"unexpected Power BI view: {view_name}")
        columns_by_view[view_name].append(
            PowerBiColumnContract(
                view_name=view_name,
                column_name=row["column_name"],
                power_bi_type=row["power_bi_type"],
                postgresql_type=row["postgresql_type"],
                description=row["description"],
                relationship_key=_yes_no(row["relationship_key"], "relationship_key"),
                nullable=_yes_no(row["nullable"], "nullable"),
            )
        )

    try:
        return PowerBiContract(
            contract_version="1.0.0",
            reference_workbook_name=path.name,
            view_order=EXPECTED_POWERBI_VIEW_NAMES,
            views=tuple(
                PowerBiViewContract(
                    view_name=name,
                    postgresql_view=summary_by_name[name]["postgresql_target"],
                    primary_use=summary_by_name[name]["primary_use"],
                    columns=tuple(columns_by_view[name]),
                )
                for name in EXPECTED_POWERBI_VIEW_NAMES
            ),
            relationships=tuple(
                PowerBiRelationshipContract(
                    from_table=row["from_table"],
                    from_column=row["from_column"],
                    cardinality=row["cardinality"],
                    to_table=row["to_table"],
                    to_column=row["to_column"],
                    filter_direction=row["filter_direction"],
                    purpose=row["purpose"],
                )
                for row in relationship_rows
            ),
        )
    except ValidationError as error:
        raise PowerBiContractError("Power BI workbook metadata is invalid") from error


# =============================================================================
# Live document validation
# =============================================================================


def _validate_scalar(value: object, column: PowerBiColumnContract) -> None:
    """Validate one JSON scalar against its semantic Power BI type."""
    if value is None:
        if not column.nullable:
            raise PowerBiContractError(
                f"{column.view_name}.{column.column_name} must not be null"
            )
        return
    if column.power_bi_type == "Text":
        if not isinstance(value, str):
            raise PowerBiContractError(
                f"{column.view_name}.{column.column_name} must be a JSON string"
            )
        if column.postgresql_type == "uuid":
            try:
                UUID(value)
            except ValueError as error:
                raise PowerBiContractError(
                    f"invalid UUID in {column.view_name}.{column.column_name}"
                ) from error
    elif column.power_bi_type == "Boolean":
        if not isinstance(value, bool):
            raise PowerBiContractError(
                f"{column.view_name}.{column.column_name} must be a JSON Boolean"
            )
    elif column.power_bi_type == "Whole Number":
        if not isinstance(value, int) or isinstance(value, bool):
            raise PowerBiContractError(
                f"{column.view_name}.{column.column_name} must be a JSON integer"
            )
    elif column.power_bi_type == "Decimal":
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PowerBiContractError(
                f"{column.view_name}.{column.column_name} must be a JSON number"
            )
    elif column.power_bi_type == "Date":
        if not isinstance(value, str):
            raise PowerBiContractError("Power BI dates must use ISO JSON strings")
        try:
            date.fromisoformat(value)
        except ValueError as error:
            raise PowerBiContractError("Power BI dates must use ISO format") from error
    elif column.power_bi_type == "Date/Time":
        if not isinstance(value, str):
            raise PowerBiContractError("Power BI datetimes must use ISO JSON strings")
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as error:
            raise PowerBiContractError(
                "Power BI datetimes must use ISO format"
            ) from error
        if column.postgresql_type == "timestamptz" and parsed.tzinfo is None:
            raise PowerBiContractError("Power BI timestamptz values must be UTC-aware")


def _validate_rows(document: PowerBiExportDocument) -> None:
    """Validate row shape, values, nullability, and per-view uniqueness."""
    views_by_name = {view.view_name: view for view in document.contract.views}
    for view_name in document.contract.view_order:
        contract = views_by_name[view_name]
        expected_columns = tuple(column.column_name for column in contract.columns)
        seen: set[tuple[object, ...]] = set()
        grain = UNIQUE_GRAINS[view_name]
        for row in document.views[view_name]:
            if tuple(row) != expected_columns:
                raise PowerBiContractError(
                    f"{view_name} columns do not match the frozen order"
                )
            for column in contract.columns:
                _validate_scalar(row[column.column_name], column)
            key = tuple(row[column] for column in grain)
            if key in seen:
                raise PowerBiContractError(f"duplicate {view_name} grain: {key}")
            seen.add(key)


def _validate_relationships(document: PowerBiExportDocument) -> None:
    """Validate one-side uniqueness and non-null foreign-key coverage."""
    for relationship in document.contract.relationships:
        one_values = {
            row[relationship.from_column]
            for row in document.views[relationship.from_table]
        }
        if None in one_values:
            raise PowerBiContractError(
                f"relationship key {relationship.from_table}."
                f"{relationship.from_column} contains null"
            )
        if len(one_values) != len(document.views[relationship.from_table]):
            raise PowerBiContractError(
                f"relationship one-side is not unique: {relationship.from_table}."
                f"{relationship.from_column}"
            )
        missing = {
            row[relationship.to_column]
            for row in document.views[relationship.to_table]
            if row[relationship.to_column] is not None
        }.difference(one_values)
        if missing:
            raise PowerBiContractError(
                f"relationship contains {len(missing)} orphan keys: "
                f"{relationship.to_table}.{relationship.to_column}"
            )


def validate_powerbi_document(document: PowerBiExportDocument) -> None:
    """Apply the complete frozen column, grain, and relationship contract."""
    if document.contract.view_order != EXPECTED_POWERBI_VIEW_NAMES:
        raise PowerBiContractError("Power BI JSON view inventory has changed")
    if sum(len(view.columns) for view in document.contract.views) != 314:
        raise PowerBiContractError("Power BI JSON must contain 314 columns")
    _validate_rows(document)
    _validate_relationships(document)
