"""Write and read the single canonical Power BI JSON export.

This outer adapter serializes an already constructed presentation document. It
must not join upstream files, calculate live rows, or create Excel workbooks.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from skill_compass.exports.powerbi_contract import (
    PowerBiContractError,
    validate_powerbi_document,
)
from skill_compass.schemas.powerbi import PowerBiExportDocument

# =============================================================================
# Canonical JSON boundary
# =============================================================================


def write_powerbi_json(path: Path, document: PowerBiExportDocument) -> None:
    """Validate and write one deterministic UTF-8 Power BI export document."""
    validate_powerbi_document(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = document.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_powerbi_json(path: Path) -> PowerBiExportDocument:
    """Read and fully revalidate one canonical Power BI JSON export."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        document = PowerBiExportDocument.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValidationError) as error:
        raise PowerBiContractError(
            f"Power BI JSON could not be read: {path}"
        ) from error
    validate_powerbi_document(document)
    return document
