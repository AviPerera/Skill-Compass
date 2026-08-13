"""Define typed JSON contracts for the Power BI presentation export.

This schema module belongs to the presentation-export boundary. It describes
the frozen workbook contract and JSON payload but must not read files, derive
analytics, or create Excel workbooks.
"""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import model_validator

from skill_compass.schemas.jobs import ImmutableModel

# =============================================================================
# Frozen workbook metadata
# =============================================================================


PowerBiType = Literal[
    "Text",
    "Date",
    "Date/Time",
    "Boolean",
    "Decimal",
    "Whole Number",
]
PowerBiScalar: TypeAlias = str | int | float | bool | None


class PowerBiColumnContract(ImmutableModel):
    """Describe one column in one frozen Power BI view contract."""

    view_name: str
    column_name: str
    power_bi_type: PowerBiType
    postgresql_type: str
    description: str
    relationship_key: bool
    nullable: bool


class PowerBiViewContract(ImmutableModel):
    """Describe one workbook table and its matching PostgreSQL view."""

    view_name: str
    postgresql_view: str
    primary_use: str
    columns: tuple[PowerBiColumnContract, ...]


class PowerBiRelationshipContract(ImmutableModel):
    """Describe one approved single-direction model relationship."""

    from_table: str
    from_column: str
    cardinality: Literal["1:*"]
    to_table: str
    to_column: str
    filter_direction: Literal["Single"]
    purpose: str


class PowerBiContract(ImmutableModel):
    """Bundle the exact view, column, and relationship inventory."""

    contract_version: str
    reference_workbook_name: str
    view_order: tuple[str, ...]
    views: tuple[PowerBiViewContract, ...]
    relationships: tuple[PowerBiRelationshipContract, ...]

    @model_validator(mode="after")
    def validate_inventory(self) -> PowerBiContract:
        """Reject duplicate or inconsistent view metadata."""
        names = tuple(view.view_name for view in self.views)
        if names != self.view_order:
            raise ValueError("Power BI views must follow the frozen view order")
        if len(names) != len(set(names)):
            raise ValueError("Power BI view names must be unique")
        for view in self.views:
            columns = tuple(column.column_name for column in view.columns)
            if not columns or len(columns) != len(set(columns)):
                raise ValueError(f"invalid column inventory for {view.view_name}")
            if any(column.view_name != view.view_name for column in view.columns):
                raise ValueError("Power BI column ownership is inconsistent")
        return self


# =============================================================================
# Single JSON export document
# =============================================================================


class PowerBiExportDocument(ImmutableModel):
    """Store the complete contract and all live view rows in one JSON object."""

    contract: PowerBiContract
    data_as_of_at: str
    views: dict[str, tuple[dict[str, PowerBiScalar], ...]]

    @model_validator(mode="after")
    def validate_view_keys(self) -> PowerBiExportDocument:
        """Require one row collection for every contracted view and no others."""
        if tuple(self.views) != self.contract.view_order:
            raise ValueError("JSON view keys must follow the frozen view order")
        return self
