"""Read small tabular sheets from the tracked synthetic Power BI workbook.

This demo-only adapter uses the standard OOXML container format and must not
feed production analytics, modify workbooks, or treat synthetic counts as live
market evidence.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree

# =============================================================================
# Minimal read-only OOXML helpers
# =============================================================================


SPREADSHEET_NAMESPACE = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
RELATIONSHIP_NAMESPACE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
)
PACKAGE_RELATIONSHIP_NAMESPACE = (
    "http://schemas.openxmlformats.org/package/2006/relationships"
)
CELL_REFERENCE = re.compile(r"([A-Z]+)[0-9]+")


class ReferenceWorkbookError(ValueError):
    """Report a missing or malformed synthetic-reference workbook contract."""


def _column_index(reference: str) -> int:
    """Convert an Excel column reference to a zero-based integer index."""
    match = CELL_REFERENCE.fullmatch(reference)
    if match is None:
        raise ReferenceWorkbookError(f"invalid worksheet cell reference: {reference}")
    result = 0
    for character in match.group(1):
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1


def _xml(archive: zipfile.ZipFile, member: str) -> ElementTree.Element:
    """Read one trusted XML member from the local workbook container."""
    try:
        with archive.open(member) as source:
            return ElementTree.parse(source).getroot()
    except (KeyError, ElementTree.ParseError) as error:
        raise ReferenceWorkbookError(
            f"synthetic workbook is missing a valid {member} part"
        ) from error


def _shared_strings(
    archive: zipfile.ZipFile,
) -> tuple[str, ...]:
    """Return the workbook shared-string table in stable index order."""
    root = _xml(archive, "xl/sharedStrings.xml")
    namespace = {"m": SPREADSHEET_NAMESPACE}
    return tuple(
        "".join(node.text or "" for node in item.findall(".//m:t", namespace))
        for item in root.findall("m:si", namespace)
    )


def _sheet_member(archive: zipfile.ZipFile, sheet_name: str) -> str:
    """Resolve one sheet name through workbook relationships."""
    workbook = _xml(archive, "xl/workbook.xml")
    relationships = _xml(archive, "xl/_rels/workbook.xml.rels")
    namespace = {"m": SPREADSHEET_NAMESPACE}
    relationship_id: str | None = None
    for sheet in workbook.findall("m:sheets/m:sheet", namespace):
        if sheet.attrib.get("name") == sheet_name:
            relationship_id = sheet.attrib.get(f"{{{RELATIONSHIP_NAMESPACE}}}id")
            break
    if relationship_id is None:
        raise ReferenceWorkbookError(
            f"synthetic workbook does not contain sheet {sheet_name!r}"
        )
    for relationship in relationships:
        if (
            relationship.tag == f"{{{PACKAGE_RELATIONSHIP_NAMESPACE}}}Relationship"
            and relationship.attrib.get("Id") == relationship_id
        ):
            target = relationship.attrib["Target"].lstrip("/")
            return target if target.startswith("xl/") else f"xl/{target}"
    raise ReferenceWorkbookError(
        f"synthetic workbook relationship is missing for {sheet_name!r}"
    )


def _cell_text(
    cell: ElementTree.Element,
    shared_strings: tuple[str, ...],
) -> str:
    """Decode one inline, shared-string, Boolean, or numeric worksheet cell."""
    namespace = {"m": SPREADSHEET_NAMESPACE}
    if cell.attrib.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//m:t", namespace))
    value = cell.find("m:v", namespace)
    if value is None or value.text is None:
        return ""
    if cell.attrib.get("t") == "s":
        try:
            return shared_strings[int(value.text)]
        except (IndexError, ValueError) as error:
            raise ReferenceWorkbookError("invalid shared-string reference") from error
    return value.text


# =============================================================================
# Public demo metadata reader
# =============================================================================


def read_reference_sheet(path: Path, sheet_name: str) -> tuple[dict[str, str], ...]:
    """Read one synthetic-reference worksheet as header-keyed string rows."""
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as error:
        raise ReferenceWorkbookError(
            f"synthetic workbook could not be read: {path}"
        ) from error
    with archive:
        shared_strings = _shared_strings(archive)
        worksheet = _xml(archive, _sheet_member(archive, sheet_name))
        namespace = {"m": SPREADSHEET_NAMESPACE}
        rows: list[list[str]] = []
        for row in worksheet.findall("m:sheetData/m:row", namespace):
            values: list[str] = []
            for cell in row.findall("m:c", namespace):
                reference = cell.attrib.get("r", "")
                index = _column_index(reference)
                while len(values) <= index:
                    values.append("")
                values[index] = _cell_text(cell, shared_strings)
            rows.append(values)
    if not rows:
        raise ReferenceWorkbookError(f"synthetic sheet {sheet_name!r} is empty")
    headers = tuple(rows[0])
    if not all(headers):
        raise ReferenceWorkbookError(
            f"synthetic sheet {sheet_name!r} has blank headers"
        )
    return tuple(
        {
            header: values[index] if index < len(values) else ""
            for index, header in enumerate(headers)
        }
        for values in rows[1:]
        if any(values)
    )
