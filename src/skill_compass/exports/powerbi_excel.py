"""Convert the canonical Power BI JSON document to the contract workbook.

This outer export adapter owns Excel typing, named tables, and template style
preservation. It must read only the JSON document for live values and must not
join upstream pipeline files or implement analytical calculations.
"""

from __future__ import annotations

import warnings
from copy import copy
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table

from skill_compass.exports.powerbi_contract import PowerBiContractError
from skill_compass.exports.powerbi_json import read_powerbi_json
from skill_compass.schemas.powerbi import (
    PowerBiColumnContract,
    PowerBiExportDocument,
    PowerBiScalar,
)

# =============================================================================
# JSON-to-Excel value conversion
# =============================================================================


def _excel_datetime(value: str) -> datetime:
    """Convert an ISO timestamptz value to Excel's UTC-naive datetime type."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _excel_value(value: PowerBiScalar, column: PowerBiColumnContract) -> object:
    """Convert one validated JSON scalar to its semantic Excel cell type."""
    if value is None:
        return None
    if column.power_bi_type == "Date":
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    if column.power_bi_type == "Date/Time":
        return _excel_datetime(str(value))
    return value


def _number_format(column: PowerBiColumnContract) -> str:
    """Return an Excel-invariant format for one semantic contract type."""
    if column.power_bi_type == "Date":
        return "yyyy-mm-dd"
    if column.power_bi_type == "Date/Time":
        return "yyyy-mm-dd hh:mm:ss"
    if column.power_bi_type == "Whole Number":
        return "0"
    if column.power_bi_type == "Decimal":
        if "salary" in column.column_name:
            return "#,##0.00"
        return "0.0000"
    if column.power_bi_type == "Text":
        return "@"
    return "General"


# =============================================================================
# Template-preserving table replacement
# =============================================================================


def _table(worksheet: object, table_name: str) -> Table:
    """Return one expected named table or fail the frozen workbook contract."""
    try:
        return worksheet.tables[table_name]  # type: ignore[attr-defined,no-any-return]
    except KeyError as error:
        raise PowerBiContractError(
            f"reference workbook is missing named table {table_name}"
        ) from error


def _replace_table(
    *,
    worksheet: object,
    table_name: str,
    columns: tuple[PowerBiColumnContract, ...],
    rows: tuple[dict[str, PowerBiScalar], ...],
) -> None:
    """Replace one table's values while retaining its existing sheet styling."""
    expected_headers = tuple(column.column_name for column in columns)
    actual_headers = tuple(
        worksheet.cell(row=1, column=index).value  # type: ignore[attr-defined]
        for index in range(1, len(columns) + 1)
    )
    if actual_headers != expected_headers:
        raise PowerBiContractError(f"template headers changed for {table_name}")

    template_styles = []
    for index in range(1, len(columns) + 1):
        cell = worksheet.cell(row=2, column=index)  # type: ignore[attr-defined]
        template_styles.append(
            (
                copy(cell._style),
                copy(cell.alignment),
                copy(cell.protection),
            )
        )
    if worksheet.max_row > 1:  # type: ignore[attr-defined]
        worksheet.delete_rows(2, worksheet.max_row - 1)  # type: ignore[attr-defined]

    for row in rows:
        worksheet.append(  # type: ignore[attr-defined]
            [_excel_value(row[column.column_name], column) for column in columns]
        )

    for row_index in range(2, len(rows) + 2):
        for column_index, column in enumerate(columns, start=1):
            cell = worksheet.cell(row=row_index, column=column_index)  # type: ignore[attr-defined]
            style, alignment, protection = template_styles[column_index - 1]
            cell._style = copy(style)
            cell.alignment = copy(alignment)
            cell.protection = copy(protection)
            cell.number_format = _number_format(column)

    table = _table(worksheet, table_name)
    final_row = max(1, len(rows) + 1)
    table.ref = f"A1:{get_column_letter(len(columns))}{final_row}"
    worksheet.freeze_panes = "A2"  # type: ignore[attr-defined]


def _metadata_column(name: str, type_name: str = "Text") -> PowerBiColumnContract:
    """Create an internal column descriptor for workbook metadata tables."""
    return PowerBiColumnContract(
        view_name="workbook_metadata",
        column_name=name,
        power_bi_type=type_name,
        postgresql_type="text",
        description="Workbook contract metadata.",
        relationship_key=False,
        nullable=False,
    )


def _replace_metadata_tables(workbook: object, document: PowerBiExportDocument) -> None:
    """Populate relationship, dictionary, and live row-count tables from JSON."""
    relationships = tuple(
        relationship.model_dump(mode="python")
        for relationship in document.contract.relationships
    )
    relationship_columns = tuple(
        _metadata_column(name)
        for name in (
            "from_table",
            "from_column",
            "cardinality",
            "to_table",
            "to_column",
            "filter_direction",
            "purpose",
        )
    )
    _replace_table(
        worksheet=workbook["Model_Relationships"],  # type: ignore[index]
        table_name="ModelRelationships",
        columns=relationship_columns,
        rows=relationships,
    )

    dictionary_rows = tuple(
        {
            "excel_table_name": view.view_name,
            "postgresql_view": view.postgresql_view,
            "column_name": column.column_name,
            "power_bi_type": column.power_bi_type,
            "postgresql_type": column.postgresql_type,
            "description": column.description,
            "relationship_key": "Yes" if column.relationship_key else "No",
            "nullable": "Yes" if column.nullable else "No",
        }
        for view in document.contract.views
        for column in view.columns
    )
    dictionary_columns = tuple(
        _metadata_column(name)
        for name in (
            "excel_table_name",
            "postgresql_view",
            "column_name",
            "power_bi_type",
            "postgresql_type",
            "description",
            "relationship_key",
            "nullable",
        )
    )
    _replace_table(
        worksheet=workbook["Data_Dictionary"],  # type: ignore[index]
        table_name="DataDictionary",
        columns=dictionary_columns,
        rows=dictionary_rows,
    )

    summary_rows = tuple(
        {
            "excel_table_name": view.view_name,
            "row_count": len(document.views[view.view_name]),
            "postgresql_target": view.postgresql_view,
            "primary_use": view.primary_use,
        }
        for view in document.contract.views
    )
    summary_columns = (
        _metadata_column("excel_table_name"),
        _metadata_column("row_count", "Whole Number"),
        _metadata_column("postgresql_target"),
        _metadata_column("primary_use"),
    )
    _replace_table(
        worksheet=workbook["Model_Summary"],  # type: ignore[index]
        table_name="ModelSummary",
        columns=summary_columns,
        rows=summary_rows,
    )


def _update_readme(workbook: object, document: PowerBiExportDocument) -> None:
    """Replace synthetic warnings with concise live-export provenance."""
    worksheet = workbook["README"]  # type: ignore[index]
    jobs = document.views["vw_jobs"]
    dates = [row["listing_date"] for row in jobs if row["listing_date"] is not None]
    date_range = f"{min(dates)} to {max(dates)}" if dates else "Not available"
    worksheet["A1"] = "Skill Compass — Live Power BI Contract Export"
    values = {
        5: (
            "Purpose",
            "Load governed live pipeline outputs into the frozen Power BI contract.",
        ),
        6: ("Exported jobs", len(jobs)),
        7: ("Listing-date range", date_range),
        8: ("PostgreSQL target", "Neon PostgreSQL pbi schema"),
        9: (
            "Design principle",
            "Each Excel table and column mirrors the final pbi.vw_* contract.",
        ),
        10: (
            "Data status",
            "Live processed export; unsupported roadmap calculations are intentionally empty.",
        ),
        11: (
            "Power BI migration rule",
            "Keep query names, columns, data types and relationships unchanged; replace only the source step.",
        ),
        12: (
            "DAX caveat",
            "Bridge visuals must use distinct job counts and governed measure definitions.",
        ),
        13: ("Generated", _excel_datetime(document.data_as_of_at)),
    }
    for row_number, (label, value) in values.items():
        worksheet.cell(row=row_number, column=1, value=label)
        worksheet.cell(row=row_number, column=2, value=value)
    worksheet["B13"].number_format = "yyyy-mm-dd hh:mm:ss"


# =============================================================================
# Public Excel conversion boundary
# =============================================================================


def write_powerbi_excel(
    *, json_path: Path, reference_workbook: Path, output_path: Path
) -> None:
    """Convert only the validated JSON values into the reference workbook shape."""
    document = read_powerbi_json(json_path)
    try:
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="Unknown extension is not supported and will be removed",
                module="openpyxl.worksheet._reader",
            )
            warnings.filterwarnings(
                "ignore",
                message=(
                    "Conditional Formatting extension is not supported and will be removed"
                ),
                module="openpyxl.worksheet._reader",
            )
            workbook = load_workbook(reference_workbook)
    except OSError as error:
        raise PowerBiContractError(
            f"reference workbook could not be opened: {reference_workbook}"
        ) from error

    expected_sheets = {
        "README",
        "Model_Relationships",
        "Data_Dictionary",
        "Model_Summary",
        *document.contract.view_order,
    }
    if set(workbook.sheetnames) != expected_sheets:
        raise PowerBiContractError("reference workbook sheet inventory has changed")

    _replace_metadata_tables(workbook, document)
    views_by_name = {view.view_name: view for view in document.contract.views}
    for view_name in document.contract.view_order:
        _replace_table(
            worksheet=workbook[view_name],
            table_name=view_name,
            columns=views_by_name[view_name].columns,
            rows=document.views[view_name],
        )
    _update_readme(workbook, document)

    generated_at = _excel_datetime(document.data_as_of_at)
    workbook.properties.title = "Skill Compass Live Power BI Contract Export"
    workbook.properties.subject = "Live JSON-to-Excel Power BI contract export"
    workbook.properties.creator = "Skill Compass"
    workbook.properties.lastModifiedBy = "Skill Compass"
    workbook.properties.created = generated_at
    workbook.properties.modified = generated_at
    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)
