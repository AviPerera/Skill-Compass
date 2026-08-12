"""Load and validate a versioned requirement-and-alias dictionary.

This configuration layer accepts literal CSV values only and must not compile
dictionary regular expressions, execute code, inspect jobs, or write outputs.
"""

from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

from pydantic import ValidationError

from skill_compass.extraction.errors import ExtractionConfigurationError
from skill_compass.extraction.hashing import canonical_sha256
from skill_compass.schemas.extraction import (
    ExtractionProfile,
    RequirementAlias,
    RequirementDefinition,
    RequirementDictionary,
)

# =============================================================================
# Dictionary field validation
# =============================================================================


REQUIRED_COLUMNS = (
    "requirement_code",
    "requirement_name",
    "requirement_type",
    "category_code",
    "category_name",
    "dashboard_group",
    "alias_text",
    "match_type",
    "case_sensitive",
    "require_word_boundary",
    "negative_context_terms",
    "active",
    "sort_order",
    "dictionary_version",
    "notes",
)
SUPPORTED_MATCH_TYPES = frozenset({"token", "phrase", "exact"})
CODE_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*$")


def parse_boolean(value: str, field_name: str, row_number: int) -> bool:
    """Parse an explicit lower-case-insensitive true or false CSV value."""
    normalized = value.strip().casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ExtractionConfigurationError(
        f"dictionary row {row_number} has invalid Boolean {field_name}: {value!r}"
    )


def parse_alias_row(
    row: dict[str, str], row_number: int, profile: ExtractionProfile
) -> RequirementAlias:
    """Validate and convert one literal CSV alias row to a typed contract."""
    requirement_code = row["requirement_code"].strip()
    category_code = row["category_code"].strip()
    requirement_type = row["requirement_type"].strip()
    match_type = row["match_type"].strip().casefold()
    alias_text = row["alias_text"].strip()

    if CODE_PATTERN.fullmatch(requirement_code) is None:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has invalid requirement_code"
        )
    if CODE_PATTERN.fullmatch(category_code) is None:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has invalid category_code"
        )
    if requirement_type not in profile.supported_requirement_types:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has unsupported requirement_type"
        )
    if match_type not in SUPPORTED_MATCH_TYPES:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has invalid match_type"
        )
    if not alias_text:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has an empty alias_text"
        )
    if not row["requirement_name"].strip():
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has an empty requirement_name"
        )
    if not row["category_name"].strip() or not row["dashboard_group"].strip():
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has invalid category metadata"
        )
    try:
        sort_order = int(row["sort_order"])
    except ValueError as error:
        raise ExtractionConfigurationError(
            f"dictionary row {row_number} has invalid sort_order"
        ) from error

    negative_terms = tuple(
        term.strip()
        for term in row["negative_context_terms"].split("|")
        if term.strip()
    )
    try:
        return RequirementAlias(
            requirement_code=requirement_code,
            requirement_name=row["requirement_name"].strip(),
            requirement_type=requirement_type,
            category_code=category_code,
            category_name=row["category_name"].strip(),
            dashboard_group=row["dashboard_group"].strip(),
            alias_text=alias_text,
            match_type=match_type,
            case_sensitive=parse_boolean(
                row["case_sensitive"], "case_sensitive", row_number
            ),
            require_word_boundary=parse_boolean(
                row["require_word_boundary"],
                "require_word_boundary",
                row_number,
            ),
            negative_context_terms=negative_terms,
            active=parse_boolean(row["active"], "active", row_number),
            sort_order=sort_order,
            dictionary_version=row["dictionary_version"].strip(),
            notes=row["notes"].strip() or None,
        )
    except ValidationError as error:
        raise ExtractionConfigurationError(
            f"invalid dictionary row {row_number}: {error}"
        ) from error


def validate_alias_collection(
    aliases: tuple[RequirementAlias, ...], profile: ExtractionProfile
) -> None:
    """Reject version, ownership, metadata, and deterministic ordering conflicts."""
    versions = {alias.dictionary_version for alias in aliases}
    if versions != {profile.requirement_dictionary_version}:
        raise ExtractionConfigurationError(
            "active dictionary aliases must use the profile dictionary version"
        )

    alias_owners: dict[str, str] = {}
    requirement_metadata: dict[str, tuple[object, ...]] = {}
    sort_owners: dict[int, str] = {}
    for alias in aliases:
        normalized_alias = " ".join(alias.alias_text.casefold().split())
        prior_owner = alias_owners.get(normalized_alias)
        if prior_owner == alias.requirement_code:
            raise ExtractionConfigurationError(
                f"duplicate active alias definition: {alias.alias_text}"
            )
        if prior_owner is not None:
            raise ExtractionConfigurationError(
                f"conflicting active alias ownership: {alias.alias_text}"
            )
        alias_owners[normalized_alias] = alias.requirement_code

        metadata = (
            alias.requirement_name,
            alias.requirement_type,
            alias.category_code,
            alias.category_name,
            alias.dashboard_group,
            alias.sort_order,
        )
        prior_metadata = requirement_metadata.setdefault(
            alias.requirement_code, metadata
        )
        if prior_metadata != metadata:
            raise ExtractionConfigurationError(
                f"inconsistent metadata for requirement {alias.requirement_code}"
            )

        sort_owner = sort_owners.setdefault(alias.sort_order, alias.requirement_code)
        if sort_owner != alias.requirement_code:
            raise ExtractionConfigurationError(
                f"sort_order {alias.sort_order} belongs to multiple requirements"
            )


# =============================================================================
# Stable dictionary assembly and hashing
# =============================================================================


def canonical_alias_values(alias: RequirementAlias) -> dict[str, object]:
    """Return the documented active fields used for dictionary hashing."""
    return alias.model_dump(mode="python")


def load_requirement_dictionary(
    path: Path, profile: ExtractionProfile
) -> RequirementDictionary:
    """Load active aliases, validate ownership, and calculate a stable hash."""
    try:
        input_file = path.open("r", encoding="utf-8-sig", newline="")
    except OSError as error:
        raise ExtractionConfigurationError(
            f"requirement dictionary could not be read: {path}"
        ) from error

    with input_file:
        reader = csv.DictReader(input_file)
        headers = tuple(reader.fieldnames or ())
        missing_columns = set(REQUIRED_COLUMNS).difference(headers)
        if missing_columns:
            missing = ", ".join(sorted(missing_columns))
            raise ExtractionConfigurationError(
                f"requirement dictionary is missing columns: {missing}"
            )
        rows = tuple(reader)

    parsed_aliases = tuple(
        parse_alias_row(dict(row), row_number, profile)
        for row_number, row in enumerate(rows, start=2)
    )
    active_aliases = tuple(
        sorted(
            (alias for alias in parsed_aliases if alias.active),
            key=lambda alias: (
                alias.sort_order,
                alias.requirement_code,
                alias.alias_text.casefold(),
                alias.alias_text,
            ),
        )
    )
    if not active_aliases:
        raise ExtractionConfigurationError(
            "requirement dictionary must contain active aliases"
        )
    validate_alias_collection(active_aliases, profile)

    aliases_by_requirement: dict[str, list[RequirementAlias]] = defaultdict(list)
    for alias in active_aliases:
        aliases_by_requirement[alias.requirement_code].append(alias)

    requirements = tuple(
        RequirementDefinition(
            requirement_code=aliases[0].requirement_code,
            requirement_name=aliases[0].requirement_name,
            requirement_type=aliases[0].requirement_type,
            category_code=aliases[0].category_code,
            category_name=aliases[0].category_name,
            dashboard_group=aliases[0].dashboard_group,
            sort_order=aliases[0].sort_order,
            dictionary_version=aliases[0].dictionary_version,
            aliases=tuple(aliases),
        )
        for aliases in aliases_by_requirement.values()
    )
    dictionary_hash = canonical_sha256(
        [canonical_alias_values(alias) for alias in active_aliases]
    )
    return RequirementDictionary(
        dictionary_version=profile.requirement_dictionary_version,
        dictionary_hash=dictionary_hash,
        requirements=requirements,
        active_aliases=active_aliases,
        category_codes=tuple(sorted({alias.category_code for alias in active_aliases})),
    )
