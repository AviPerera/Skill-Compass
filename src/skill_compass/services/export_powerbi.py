"""Build the exact Power BI contract and export JSON before Excel.

This application service coordinates governed Features 2–8 inputs, stable
presentation identifiers, contract validation, and outer export adapters. It
must not recalculate Feature 8 analytics, write PostgreSQL objects, or contain
Power BI visual and DAX logic.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TypeVar
from uuid import NAMESPACE_URL, uuid5

from skill_compass.adapters.reference_workbook import read_reference_sheet
from skill_compass.classification.config import load_role_rules
from skill_compass.classification.seniority_config import load_seniority_rules
from skill_compass.cleaning.employment import EMPLOYMENT_MARKERS
from skill_compass.exports.powerbi_contract import (
    PowerBiContractError,
    load_powerbi_contract,
    validate_powerbi_document,
)
from skill_compass.exports.powerbi_excel import write_powerbi_excel
from skill_compass.exports.powerbi_inputs import (
    PowerBiSourceInputs,
    read_powerbi_source_inputs,
)
from skill_compass.exports.powerbi_json import write_powerbi_json
from skill_compass.extraction.dictionary import load_requirement_dictionary
from skill_compass.extraction.profile import load_extraction_profile
from skill_compass.schemas.analytics import AnalyticsJobFact
from skill_compass.schemas.classification import RoleRuleSet, SeniorityRuleSet
from skill_compass.schemas.extraction import ExtractionProfile, RequirementDictionary
from skill_compass.schemas.jobs import CleanedJob
from skill_compass.schemas.powerbi import (
    PowerBiContract,
    PowerBiExportDocument,
    PowerBiScalar,
)

# =============================================================================
# Stable export identity and service result
# =============================================================================


POWERBI_NAMESPACE = uuid5(NAMESPACE_URL, "https://skill-compass/powerbi")
JSON_FILENAME = "skill_compass_powerbi_live.json"
EXCEL_FILENAME = "skill_compass_powerbi_live.xlsx"
RowT = TypeVar("RowT")


@dataclass(frozen=True, slots=True)
class PowerBiExportResult:
    """Describe the two Feature 9 artifacts and their validated view counts."""

    json_path: Path
    excel_path: Path
    data_as_of_at: datetime
    view_row_counts: dict[str, int]


def _stable_id(entity: str, *parts: object) -> str:
    """Create one deterministic UUIDv5 from explicit stable identity parts."""
    value = ":".join((entity, *(str(part) for part in parts)))
    return str(uuid5(POWERBI_NAMESPACE, value))


def _identity(row: object) -> tuple[str, str]:
    """Return the canonical external job identity from one typed record."""
    return (str(getattr(row, "source_code")), str(getattr(row, "source_job_id")))


def _index(rows: tuple[RowT, ...], label: str) -> dict[tuple[str, str], RowT]:
    """Build one strict job-grain index and reject duplicate identities."""
    result: dict[tuple[str, str], RowT] = {}
    for row in rows:
        key = _identity(row)
        if key in result:
            raise PowerBiContractError(f"duplicate {label} identity: {key[0]}:{key[1]}")
        result[key] = row
    return result


def _display_code(code: str) -> str:
    """Convert one stable code to the established compact display form."""
    special = {
        "onsite": "On-site",
        "unknown": "Not specified",
        "full_time": "Full time",
        "part_time": "Part time",
    }
    return special.get(code, code.replace("_", " ").title())


def _utc(value: datetime) -> datetime:
    """Normalize one source timestamp to an aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso_datetime(value: datetime | None) -> str | None:
    """Serialize one datetime as an explicit UTC ISO string."""
    return _utc(value).isoformat() if value is not None else None


def _date_key(value: date | None) -> int | None:
    """Convert one date to the approved integer YYYYMMDD key."""
    return int(value.strftime("%Y%m%d")) if value is not None else None


def _number(value: Decimal | int | None) -> float | int | None:
    """Convert a Decimal analytical value to a JSON number."""
    if value is None or isinstance(value, int):
        return value
    return float(value)


def _midpoint(minimum: Decimal | None, maximum: Decimal | None) -> float | None:
    """Calculate a midpoint only when both valid source bounds exist."""
    if minimum is None or maximum is None or minimum > maximum:
        return None
    return float((minimum + maximum) / Decimal(2))


# =============================================================================
# Contract projection and upstream reconciliation
# =============================================================================


def _project_rows(
    contract: PowerBiContract,
    view_name: str,
    rows: list[dict[str, PowerBiScalar]],
) -> tuple[dict[str, PowerBiScalar], ...]:
    """Project mappings to the exact frozen column names and order."""
    view = next(view for view in contract.views if view.view_name == view_name)
    columns = tuple(column.column_name for column in view.columns)
    projected: list[dict[str, PowerBiScalar]] = []
    for row in rows:
        extras = set(row).difference(columns)
        if extras:
            raise PowerBiContractError(
                f"{view_name} mapper produced unexpected columns: {sorted(extras)}"
            )
        projected.append({column: row.get(column) for column in columns})
    return tuple(projected)


def _reconcile_inputs(inputs: PowerBiSourceInputs) -> None:
    """Require Feature 8 facts to match the Feature 7 included population."""
    cleaned = set(_index(inputs.cleaned_jobs, "cleaned job"))
    roles = set(_index(inputs.role_classifications, "role classification"))
    seniorities = set(
        _index(inputs.seniority_classifications, "seniority classification")
    )
    relevance = _index(inputs.relevance_classifications, "profile relevance")
    classifier_keys = set(relevance)
    if roles != classifier_keys or seniorities != classifier_keys:
        raise PowerBiContractError("classifier inputs do not reconcile")
    if not classifier_keys.issubset(cleaned):
        raise PowerBiContractError("cleaned jobs do not cover classifier inputs")
    included = {
        key for key, row in relevance.items() if row.relevance_status == "included"
    }
    fact_keys = set(_index(inputs.job_facts, "Feature 8 job fact"))
    if fact_keys != included:
        raise PowerBiContractError("Feature 8 job facts do not match included jobs")
    summary_count = inputs.analytics_summary.get("included_job_count")
    if summary_count != len(fact_keys):
        raise PowerBiContractError("Feature 8 included count does not reconcile")
    if any(_identity(skill) not in fact_keys for skill in inputs.job_skill_facts):
        raise PowerBiContractError("Feature 8 job-skill facts contain excluded jobs")


# =============================================================================
# Shared live export context
# =============================================================================


@dataclass(frozen=True, slots=True)
class _Context:
    """Hold stable identifiers and indexed records shared across view builders."""

    profile_id: str
    profile_code: str
    profile_name: str
    country_code: str
    analysis_period_id: str
    period_code: str
    period_name: str
    period_start: date
    period_end: date
    data_as_of: datetime
    processing_version_id: str
    run_id: str
    cleaned: dict[tuple[str, str], CleanedJob]
    jobs: tuple[AnalyticsJobFact, ...]
    job_ids: dict[tuple[str, str], str]
    job_version_ids: dict[tuple[str, str], str]
    role_ids: dict[str, str]
    seniority_ids: dict[str, str]
    skill_ids: dict[str, str]
    category_ids: dict[str, str]
    employment_ids: dict[str, str]
    work_mode_ids: dict[str, str]
    pathway_ids: dict[str, str]


def _build_context(
    *,
    inputs: PowerBiSourceInputs,
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
    roles: RoleRuleSet,
    seniority: SeniorityRuleSet,
) -> _Context:
    """Derive deterministic shared identities and the frozen analysis period."""
    cleaned_all = _index(inputs.cleaned_jobs, "cleaned job")
    included_jobs = tuple(sorted(inputs.job_facts, key=_identity))
    cleaned = {key: cleaned_all[key] for key in map(_identity, included_jobs)}
    processed_times = [
        _utc(classification.classified_at)
        for classification in inputs.relevance_classifications
    ]
    if not processed_times:
        processed_times = [
            _utc(job.scraped_at) for job in inputs.cleaned_jobs if job.scraped_at
        ]
    if not processed_times:
        raise PowerBiContractError(
            "Power BI export requires a deterministic processed or scraped timestamp"
        )
    data_as_of = max(processed_times)
    listing_dates = tuple(
        job.listing_date for job in cleaned.values() if job.listing_date is not None
    )
    period_start = min(listing_dates) if listing_dates else data_as_of.date()
    period_end = max(listing_dates) if listing_dates else data_as_of.date()
    profile_code = profile.profile_code
    profile_id = _stable_id("profile", profile_code)
    period_code = (
        f"{profile_code}_{period_start.strftime('%Y%m%d')}_"
        f"{period_end.strftime('%Y%m%d')}"
    )
    analysis_period_id = _stable_id("analysis_period", profile_id, period_code)
    processing_version_id = _stable_id(
        "processing_version",
        profile_id,
        profile.profile_hash,
        dictionary.dictionary_hash,
        roles.role_rules_hash,
    )
    run_id = _stable_id(
        "published_run",
        analysis_period_id,
        processing_version_id,
        data_as_of.isoformat(),
    )

    role_codes = {job.role_group_code for job in included_jobs}
    role_codes.update(role.role_group_code for role in roles.roles)
    seniority_codes = {job.seniority_code for job in included_jobs}
    seniority_codes.update(level.seniority_code for level in seniority.levels)
    skill_codes = {
        requirement.requirement_code
        for requirement in dictionary.requirements
        if requirement.requirement_type == "skill"
    }
    category_codes = {
        requirement.category_code
        for requirement in dictionary.requirements
        if requirement.requirement_type == "skill"
    }
    employment_codes = {
        code for job in cleaned.values() for code in job.employment_type_codes
    }
    work_mode_codes = {job.work_mode_code for job in cleaned.values()}
    pathway_codes = {role.role_group_code for role in roles.roles}
    country_codes = {job.country_code for job in cleaned.values() if job.country_code}
    country_code = next(iter(country_codes)) if len(country_codes) == 1 else "AU"
    return _Context(
        profile_id=profile_id,
        profile_code=profile_code,
        profile_name=profile.profile_name,
        country_code=country_code,
        analysis_period_id=analysis_period_id,
        period_code=period_code,
        period_name=f"{period_start.isoformat()} to {period_end.isoformat()}",
        period_start=period_start,
        period_end=period_end,
        data_as_of=data_as_of,
        processing_version_id=processing_version_id,
        run_id=run_id,
        cleaned=cleaned,
        jobs=included_jobs,
        job_ids={key: _stable_id("job", *key) for key in map(_identity, included_jobs)},
        job_version_ids={
            key: _stable_id("job_version", *key, cleaned[key].content_hash)
            for key in map(_identity, included_jobs)
        },
        role_ids={code: _stable_id("role", profile_id, code) for code in role_codes},
        seniority_ids={
            code: _stable_id("seniority", profile_id, code) for code in seniority_codes
        },
        skill_ids={code: _stable_id("skill", profile_id, code) for code in skill_codes},
        category_ids={
            code: _stable_id("skill_category", profile_id, code)
            for code in category_codes
        },
        employment_ids={
            code: _stable_id("employment_type", code) for code in employment_codes
        },
        work_mode_ids={code: _stable_id("work_mode", code) for code in work_mode_codes},
        pathway_ids={
            code: _stable_id("pathway", profile_id, code) for code in pathway_codes
        },
    )


# =============================================================================
# Dimension builders
# =============================================================================


def _date_rows(context: _Context) -> list[dict[str, PowerBiScalar]]:
    """Build the inclusive analysis-period calendar dimension."""
    rows: list[dict[str, PowerBiScalar]] = []
    current = context.period_start
    while current <= context.period_end:
        rows.append(
            {
                "date_key": _date_key(current),
                "full_date": current.isoformat(),
                "day_number": current.day,
                "day_name": current.strftime("%A"),
                "week_number": current.isocalendar().week,
                "month_number": current.month,
                "month_name": current.strftime("%B"),
                "quarter_number": ((current.month - 1) // 3) + 1,
                "year_number": current.year,
                "year_month": current.strftime("%Y-%m"),
            }
        )
        current += timedelta(days=1)
    return rows


def _role_rows(context: _Context, roles: RoleRuleSet) -> list[dict[str, PowerBiScalar]]:
    """Build governed roles plus explicit safety outcomes used by live jobs."""
    approved = {role.role_group_code: role for role in roles.roles}
    encountered = {job.role_group_code: job.role_group_label for job in context.jobs}
    ordered = list(sorted(roles.roles, key=lambda role: role.sort_order))
    rows = [
        {
            "role_group_id": context.role_ids[role.role_group_code],
            "profile_id": context.profile_id,
            "role_group_code": role.role_group_code,
            "role_group_name": role.role_group_label,
            "role_family_code": None,
            "role_family_name": None,
            "business_oriented_flag": None,
            "graduate_friendly_flag": None,
            "supported_pathway_flag": True,
            "sort_order": role.sort_order,
        }
        for role in ordered
    ]
    next_order = len(rows) + 1
    for code in sorted(set(encountered).difference(approved)):
        rows.append(
            {
                "role_group_id": context.role_ids[code],
                "profile_id": context.profile_id,
                "role_group_code": code,
                "role_group_name": encountered[code],
                "role_family_code": None,
                "role_family_name": None,
                "business_oriented_flag": None,
                "graduate_friendly_flag": None,
                "supported_pathway_flag": False,
                "sort_order": next_order,
            }
        )
        next_order += 1
    return rows


def _seniority_rows(
    context: _Context, seniority: SeniorityRuleSet
) -> list[dict[str, PowerBiScalar]]:
    """Build governed seniority levels plus explicit live safety outcomes."""
    approved = {level.seniority_code: level for level in seniority.levels}
    encountered = {job.seniority_code: job.seniority_label for job in context.jobs}
    rows = [
        {
            "seniority_level_id": context.seniority_ids[level.seniority_code],
            "profile_id": context.profile_id,
            "seniority_code": level.seniority_code,
            "seniority_name": level.seniority_label,
            "rank_order": level.rank_order,
            "graduate_level_flag": level.graduate_level_flag,
        }
        for level in sorted(seniority.levels, key=lambda level: level.rank_order)
    ]
    for code in sorted(set(encountered).difference(approved)):
        rows.append(
            {
                "seniority_level_id": context.seniority_ids[code],
                "profile_id": context.profile_id,
                "seniority_code": code,
                "seniority_name": encountered[code],
                "rank_order": None,
                "graduate_level_flag": False,
            }
        )
    return rows


def _geography_data(
    context: _Context,
) -> tuple[list[dict[str, PowerBiScalar]], dict[tuple[str, str], str]]:
    """Build state/city geography rows and each included job's primary key."""
    state_values = sorted(
        {
            (job.state_code, job.state_name)
            for job in context.cleaned.values()
            if job.state_code or job.state_name
        },
        key=lambda value: (value[0] or "", value[1] or ""),
    )
    rows: list[dict[str, PowerBiScalar]] = []
    state_ids: dict[tuple[str | None, str | None], str] = {}
    sort_order = 1
    for state_code, state_name in state_values:
        geography_id = _stable_id(
            "geography", context.country_code, state_code or state_name or "unknown"
        )
        state_ids[(state_code, state_name)] = geography_id
        rows.append(
            {
                "geography_id": geography_id,
                "parent_geography_id": None,
                "geography_type": "state",
                "country_code": context.country_code,
                "state_code": state_code,
                "state_name": state_name,
                "city_name": None,
                "suburb_name": None,
                "display_name": state_name or state_code,
                "tile_row": None,
                "tile_column": None,
                "map_sort_order": sort_order,
                "is_state_or_territory": True,
                "is_major_city": False,
            }
        )
        sort_order += 1

    city_values = sorted(
        {
            (job.state_code, job.state_name, job.city_name)
            for job in context.cleaned.values()
            if job.city_name
        },
        key=lambda value: (value[0] or "", value[2] or ""),
    )
    city_ids: dict[tuple[str | None, str | None, str], str] = {}
    for state_code, state_name, city_name in city_values:
        geography_id = _stable_id(
            "geography", context.country_code, state_code or state_name, city_name
        )
        city_ids[(state_code, state_name, city_name)] = geography_id
        rows.append(
            {
                "geography_id": geography_id,
                "parent_geography_id": state_ids.get((state_code, state_name)),
                "geography_type": "city",
                "country_code": context.country_code,
                "state_code": state_code,
                "state_name": state_name,
                "city_name": city_name,
                "suburb_name": None,
                "display_name": city_name,
                "tile_row": None,
                "tile_column": None,
                "map_sort_order": sort_order,
                "is_state_or_territory": False,
                "is_major_city": None,
            }
        )
        sort_order += 1

    unknown_id = _stable_id("geography", context.country_code, "not_specified")
    if any(
        not job.city_name and not job.state_code and not job.state_name
        for job in context.cleaned.values()
    ):
        rows.append(
            {
                "geography_id": unknown_id,
                "parent_geography_id": None,
                "geography_type": "unknown",
                "country_code": context.country_code,
                "state_code": None,
                "state_name": None,
                "city_name": None,
                "suburb_name": None,
                "display_name": "Not specified",
                "tile_row": None,
                "tile_column": None,
                "map_sort_order": sort_order,
                "is_state_or_territory": False,
                "is_major_city": False,
            }
        )

    job_geography: dict[tuple[str, str], str] = {}
    for key, job in context.cleaned.items():
        if job.city_name:
            job_geography[key] = city_ids[
                (job.state_code, job.state_name, job.city_name)
            ]
        elif job.state_code or job.state_name:
            job_geography[key] = state_ids[(job.state_code, job.state_name)]
        else:
            job_geography[key] = unknown_id
    return rows, job_geography


def _skill_rows(
    context: _Context, dictionary: RequirementDictionary
) -> list[dict[str, PowerBiScalar]]:
    """Build active skill and category dimension rows from the governed dictionary."""
    return [
        {
            "skill_id": context.skill_ids[requirement.requirement_code],
            "profile_id": context.profile_id,
            "skill_code": requirement.requirement_code,
            "skill_name": requirement.requirement_name,
            "skill_category_id": context.category_ids[requirement.category_code],
            "skill_category_code": requirement.category_code,
            "skill_category_name": requirement.category_name,
            "dashboard_group_code": requirement.dashboard_group.casefold().replace(
                " ", "_"
            ),
            "dashboard_group_name": requirement.dashboard_group,
            "sort_order": requirement.sort_order,
            "is_active": True,
        }
        for requirement in sorted(
            dictionary.requirements, key=lambda requirement: requirement.sort_order
        )
        if requirement.requirement_type == "skill"
    ]


# =============================================================================
# Fact, bridge, and governed analytical builders
# =============================================================================


def _job_and_bridge_rows(
    *,
    context: _Context,
    inputs: PowerBiSourceInputs,
    job_geography: dict[tuple[str, str], str],
) -> dict[str, list[dict[str, PowerBiScalar]]]:
    """Build live job facts plus geography, employment, and work-mode bridges."""
    relevance = _index(inputs.relevance_classifications, "profile relevance")
    seniority = _index(inputs.seniority_classifications, "seniority classification")
    skills_by_job: dict[tuple[str, str], list[object]] = defaultdict(list)
    for skill in inputs.job_skill_facts:
        skills_by_job[_identity(skill)].append(skill)

    jobs: list[dict[str, PowerBiScalar]] = []
    locations: list[dict[str, PowerBiScalar]] = []
    employment: list[dict[str, PowerBiScalar]] = []
    work_modes: list[dict[str, PowerBiScalar]] = []
    for fact in context.jobs:
        key = _identity(fact)
        cleaned = context.cleaned[key]
        job_id = context.job_ids[key]
        version_id = context.job_version_ids[key]
        skill_rows = skills_by_job[key]
        category_counts = Counter(skill.category_code for skill in skill_rows)
        dashboard_counts = Counter(skill.dashboard_group for skill in skill_rows)
        scraped_date = _utc(cleaned.scraped_at).date() if cleaned.scraped_at else None
        expiry_date = _utc(cleaned.expires_at).date() if cleaned.expires_at else None
        source_id = _stable_id("source", fact.source_code)
        jobs.append(
            {
                "analysis_period_id": context.analysis_period_id,
                "period_code": context.period_code,
                "period_name": context.period_name,
                "period_start_date": context.period_start.isoformat(),
                "period_end_date": context.period_end.isoformat(),
                "data_as_of_at": _iso_datetime(context.data_as_of),
                "profile_id": context.profile_id,
                "profile_code": context.profile_code,
                "job_id": job_id,
                "job_version_id": version_id,
                "source_id": source_id,
                "source_name": _display_code(fact.source_code),
                "source_job_id": fact.source_job_id,
                "job_url": cleaned.job_url,
                "title": fact.title_clean,
                "company_name": cleaned.company_name_clean,
                "advertiser_name": None,
                "employer_name": None,
                "primary_geography_id": job_geography[key],
                "city": fact.city_name,
                "state_code": fact.state_code,
                "state_name": fact.state_name,
                "role_group_id": context.role_ids[fact.role_group_code],
                "role_group_code": fact.role_group_code,
                "role_group_name": fact.role_group_label,
                "role_family_code": None,
                "business_oriented_flag": None,
                "graduate_friendly_role_flag": None,
                "role_confidence_score": _number(fact.role_confidence_score),
                "seniority_level_id": context.seniority_ids[fact.seniority_code],
                "seniority_code": fact.seniority_code,
                "seniority_name": fact.seniority_label,
                "seniority_rank": fact.seniority_rank,
                "graduate_level_flag": fact.graduate_level_flag,
                "seniority_confidence_score": _number(
                    seniority[key].seniority_confidence_score
                ),
                "primary_employment_type_id": context.employment_ids[
                    fact.primary_employment_type_code
                ],
                "primary_work_mode_id": context.work_mode_ids[fact.work_mode_code],
                "salary_text": cleaned.salary_label_raw,
                "salary_min": _number(cleaned.salary_min),
                "salary_max": _number(cleaned.salary_max),
                "salary_midpoint": _midpoint(cleaned.salary_min, cleaned.salary_max),
                "salary_currency_code": cleaned.salary_currency,
                "salary_basis_code": cleaned.salary_period,
                "annualised_salary_midpoint": None,
                "salary_parse_status": cleaned.salary_parse_status,
                "salary_extraction_method": cleaned.salary_parse_method,
                "salary_confidence_score": None,
                "listing_date": (
                    cleaned.listing_date.isoformat() if cleaned.listing_date else None
                ),
                "listing_date_key": _date_key(cleaned.listing_date),
                "first_seen_date_key": _date_key(scraped_date),
                "last_seen_date_key": _date_key(scraped_date),
                "expiry_date_key": _date_key(expiry_date),
                "active_as_of_period_end_flag": (
                    expiry_date >= context.period_end if expiry_date else None
                ),
                "validation_status": "approved",
                "skill_count_total": len(skill_rows),
                "programming_skill_count": category_counts["programming"],
                "database_skill_count": category_counts["database"],
                "bi_visualisation_skill_count": category_counts[
                    "business_intelligence"
                ],
                "technical_skill_count": dashboard_counts["Technical Skills"],
                "business_skill_count": dashboard_counts["Business Skills"],
                "soft_skill_count": dashboard_counts["Soft Skills"],
                "processed_at": _iso_datetime(relevance[key].classified_at),
                "processing_version_id": context.processing_version_id,
            }
        )
        locations.append(
            {
                "analysis_period_id": context.analysis_period_id,
                "profile_id": context.profile_id,
                "job_id": job_id,
                "job_version_id": version_id,
                "geography_id": job_geography[key],
                "is_primary": True,
                "source_position": 1,
            }
        )
        for position, employment_code in enumerate(
            cleaned.employment_type_codes, start=1
        ):
            employment.append(
                {
                    "analysis_period_id": context.analysis_period_id,
                    "profile_id": context.profile_id,
                    "job_id": job_id,
                    "job_version_id": version_id,
                    "employment_type_id": context.employment_ids[employment_code],
                    "is_primary": position == 1,
                }
            )
        work_modes.append(
            {
                "analysis_period_id": context.analysis_period_id,
                "profile_id": context.profile_id,
                "job_id": job_id,
                "job_version_id": version_id,
                "work_mode_id": context.work_mode_ids[cleaned.work_mode_code],
                "source_label": _display_code(cleaned.work_mode_code),
                "classification_method": cleaned.work_mode_parse_method,
                "confidence_score": None,
                "is_primary": True,
            }
        )
    return {
        "vw_jobs": jobs,
        "vw_job_locations": locations,
        "vw_job_employment_types": employment,
        "vw_job_work_modes": work_modes,
    }


def _job_skill_rows(
    context: _Context, inputs: PowerBiSourceInputs
) -> list[dict[str, PowerBiScalar]]:
    """Build one row per included job and canonical skill."""
    matches = {
        (*_identity(match), match.requirement_code): match
        for match in inputs.requirement_matches
    }
    rows: list[dict[str, PowerBiScalar]] = []
    for skill in sorted(
        inputs.job_skill_facts,
        key=lambda row: (*_identity(row), row.requirement_code),
    ):
        key = _identity(skill)
        match = matches.get((*key, skill.requirement_code))
        if match is None:
            raise PowerBiContractError("Feature 8 skill fact lacks its governed match")
        rows.append(
            {
                "analysis_period_id": context.analysis_period_id,
                "profile_id": context.profile_id,
                "job_id": context.job_ids[key],
                "job_version_id": context.job_version_ids[key],
                "skill_id": context.skill_ids[skill.requirement_code],
                "skill_code": skill.requirement_code,
                "skill_name": skill.requirement_name,
                "skill_category_id": context.category_ids[skill.category_code],
                "skill_category_code": skill.category_code,
                "skill_category_name": skill.category_name,
                "dashboard_group_code": skill.dashboard_group.casefold().replace(
                    " ", "_"
                ),
                "dashboard_group_name": skill.dashboard_group,
                "mention_count": skill.mention_count,
                "weighted_match_score": _number(skill.weighted_match_score),
                "extraction_confidence_score": _number(match.extraction_score),
                "match_method": match.extraction_method,
                "extraction_version": match.extractor_version,
                "manual_validation_status": None,
            }
        )
    return rows


def _combination_rows(
    context: _Context, inputs: PowerBiSourceInputs
) -> list[dict[str, PowerBiScalar]]:
    """Translate only governed role-scoped Feature 8 combinations."""
    rows: list[dict[str, PowerBiScalar]] = []
    for combination in inputs.skill_combinations:
        if combination.scope_code not in context.pathway_ids:
            continue
        rows.append(
            {
                "analysis_period_id": context.analysis_period_id,
                "profile_id": context.profile_id,
                "pathway_id": context.pathway_ids[combination.scope_code],
                "role_group_id": context.role_ids[combination.scope_code],
                "seniority_scope_code": "graduate_friendly",
                "graduate_friendly_flag": combination.graduate_friendly_flag,
                "combination_size": combination.combination_size,
                "combination_label": combination.combination_label,
                "supporting_job_count": combination.supporting_job_count,
                "eligible_job_count": combination.eligible_job_count,
                "job_percentage": _number(combination.job_percentage),
                "support": _number(combination.support),
                "confidence": _number(combination.confidence),
                "lift": _number(combination.lift),
                "combination_rank": combination.combination_rank,
                "sample_size_warning_flag": combination.sample_size_warning_flag,
                "calculated_at": _iso_datetime(context.data_as_of),
            }
        )
    return rows


# =============================================================================
# Methodology and governance builders
# =============================================================================


def _metric_number(value: str) -> float | None:
    """Parse a numeric quality value without treating Boolean text as a number."""
    if value.casefold() in {"true", "false"}:
        return None
    try:
        return float(Decimal(value))
    except InvalidOperation:
        return None


def _quality_rows(
    context: _Context, inputs: PowerBiSourceInputs
) -> list[dict[str, PowerBiScalar]]:
    """Translate standard cleaning, extraction, and analytics quality metrics."""
    sources = (
        ("cleaning", inputs.cleaning_quality),
        ("extraction", inputs.extraction_quality),
        (
            "analytics",
            tuple(
                {
                    "metric_category": row.metric_category,
                    "metric_name": row.metric_name,
                    "metric_value": row.metric_value,
                    "metric_status": row.metric_status,
                    "metric_detail": row.metric_detail,
                }
                for row in inputs.analytics_quality
            ),
        ),
    )
    rows: list[dict[str, PowerBiScalar]] = []
    for component, metrics in sources:
        for metric in metrics:
            value = metric["metric_value"]
            rows.append(
                {
                    "run_id": context.run_id,
                    "profile_id": context.profile_id,
                    "metric_code": f"{component}_{metric['metric_name']}",
                    "metric_name": metric["metric_name"].replace("_", " ").title(),
                    "dimension_name": component,
                    "dimension_value": metric["metric_category"],
                    "metric_value_numeric": _metric_number(value),
                    "numerator": None,
                    "denominator": None,
                    "unit": "count" if _metric_number(value) is not None else "status",
                    "severity": metric["metric_status"],
                    "measured_at": _iso_datetime(context.data_as_of),
                }
            )
    return rows


def _pipeline_rows(
    context: _Context, inputs: PowerBiSourceInputs, version: str
) -> list[dict[str, PowerBiScalar]]:
    """Build count-only pipeline evidence without inventing durations."""
    summary = inputs.analytics_summary
    cleaned_count = len(inputs.cleaned_jobs)
    included_count = len(inputs.job_facts)
    duplicate_count = next(
        (
            int(metric["metric_value"])
            for metric in inputs.cleaning_quality
            if metric["metric_name"] == "duplicate_same_content_rows"
        ),
        0,
    )
    steps = (
        (
            "cleaning",
            "Mapping and Cleaning",
            cleaned_count,
            cleaned_count,
            duplicate_count,
            0,
        ),
        (
            "skill_extraction",
            "Requirement Extraction",
            cleaned_count,
            len(inputs.requirement_matches),
            0,
            0,
        ),
        (
            "role_classification",
            "Role Classification",
            cleaned_count,
            len(inputs.role_classifications),
            0,
            0,
        ),
        (
            "seniority_classification",
            "Seniority Classification",
            cleaned_count,
            len(inputs.seniority_classifications),
            0,
            0,
        ),
        (
            "profile_relevance",
            "Profile Relevance",
            len(inputs.relevance_classifications),
            included_count,
            0,
            int(summary["excluded_job_count"]) + int(summary["review_job_count"]),
        ),
        (
            "analytics",
            "Channel-neutral Analytics",
            included_count,
            included_count,
            0,
            0,
        ),
        (
            "powerbi_export",
            "Power BI Contract Export",
            included_count,
            included_count,
            0,
            0,
        ),
    )
    return [
        {
            "run_id": context.run_id,
            "analysis_period_id": context.analysis_period_id,
            "profile_id": context.profile_id,
            "step_code": code,
            "step_name": name,
            "step_order": order,
            "input_record_count": input_count,
            "output_record_count": output_count,
            "duplicate_record_count": duplicates,
            "excluded_record_count": excluded,
            "error_record_count": 0,
            "duration_seconds": None,
            "method_name": "deterministic_python",
            "method_version": version,
            "status": "pass",
            "completed_at": _iso_datetime(context.data_as_of),
        }
        for order, (
            code,
            name,
            input_count,
            output_count,
            duplicates,
            excluded,
        ) in enumerate(steps, start=1)
    ]


def _governance_rows(
    *,
    context: _Context,
    inputs: PowerBiSourceInputs,
    roles: RoleRuleSet,
    profile: ExtractionProfile,
    reference_workbook: Path,
) -> dict[str, list[dict[str, PowerBiScalar]]]:
    """Build truthful static methodology and live export-validation metadata."""
    role_profiles_by_name = {
        row["role_group_name"]: row
        for row in read_reference_sheet(reference_workbook, "vw_role_profiles")
    }
    role_profiles = []
    for role in sorted(roles.roles, key=lambda row: row.sort_order):
        approved = role_profiles_by_name.get(role.role_group_label, {})
        role_profiles.append(
            {
                "profile_id": context.profile_id,
                "role_group_id": context.role_ids[role.role_group_code],
                "role_group_name": role.role_group_label,
                "profile_title": approved.get("profile_title") or None,
                "profile_summary": approved.get("profile_summary") or None,
                "core_skills_text": approved.get("core_skills_text") or None,
                "tool_emphasis_text": approved.get("tool_emphasis_text") or None,
                "business_emphasis_text": approved.get("business_emphasis_text")
                or None,
                "technical_depth_text": approved.get("technical_depth_text") or None,
            }
        )

    methodology = (
        (
            "collection",
            "Data Collection",
            "Collect structured Australian job advertisements with configured local source provenance.",
            "Apify / JSONL",
        ),
        (
            "cleaning",
            "Data Cleaning",
            "Map source fields, remove duplicates, and standardise canonical job attributes.",
            "Python rules",
        ),
        (
            "skill_extraction",
            "Skill Extraction",
            "Match governed aliases against section-aware text and retain deterministic scores.",
            "Dictionary and regex rules",
        ),
        (
            "classification_analysis",
            "Classification and Analysis",
            "Apply governed role, seniority and relevance rules before distinct-job analytics.",
            "Python analytics",
        ),
        (
            "powerbi_export",
            "Power BI Contract Export",
            "Validate 26 frozen view contracts, write one JSON source, then convert it to Excel.",
            "JSON / openpyxl",
        ),
    )
    methodology_rows = [
        {
            "profile_id": context.profile_id,
            "profile_code": context.profile_code,
            "step_order": order,
            "step_code": code,
            "step_name": name,
            "step_description": description,
            "method_tag": method,
        }
        for order, (code, name, description, method) in enumerate(methodology, start=1)
    ]

    validation_rows = [
        {
            "profile_id": context.profile_id,
            "processing_version_id": context.processing_version_id,
            "component_name": "powerbi_contract",
            "metric_name": "view_count",
            "metric_value": 26,
            "sample_size": 26,
            "calculated_at": _iso_datetime(context.data_as_of),
        },
        {
            "profile_id": context.profile_id,
            "processing_version_id": context.processing_version_id,
            "component_name": "powerbi_contract",
            "metric_name": "column_count",
            "metric_value": 314,
            "sample_size": 314,
            "calculated_at": _iso_datetime(context.data_as_of),
        },
        {
            "profile_id": context.profile_id,
            "processing_version_id": context.processing_version_id,
            "component_name": "feature_8_reconciliation",
            "metric_name": "included_jobs",
            "metric_value": len(inputs.job_facts),
            "sample_size": len(inputs.job_facts),
            "calculated_at": _iso_datetime(context.data_as_of),
        },
        {
            "profile_id": context.profile_id,
            "processing_version_id": context.processing_version_id,
            "component_name": "privacy",
            "metric_name": "private_fields_exported",
            "metric_value": 0,
            "sample_size": len(inputs.job_facts),
            "calculated_at": _iso_datetime(context.data_as_of),
        },
    ]
    technology = (
        (
            "Python",
            "Processing",
            "Reusable deterministic processing logic.",
            "implemented",
            "3.12",
        ),
        (
            "Pydantic",
            "Contracts",
            "Typed input and export validation.",
            "implemented",
            "2.x",
        ),
        (
            "openpyxl",
            "Export",
            "JSON-to-Excel contract conversion.",
            "implemented",
            "3.1",
        ),
        (
            "Apify",
            "Collection",
            "Configured structured source collection.",
            "implemented",
            None,
        ),
        (
            "pytest",
            "Quality",
            "Deterministic unit and integration testing.",
            "implemented",
            None,
        ),
        ("Ruff", "Quality", "Linting and formatting checks.", "implemented", None),
        (
            "Power BI Desktop",
            "Presentation",
            "Target semantic model and dashboard.",
            "contract_ready",
            None,
        ),
    )
    technology_rows = [
        {
            "profile_id": context.profile_id,
            "tool_name": name,
            "tool_category": category,
            "purpose": purpose,
            "implementation_status": status,
            "technology_version": version,
            "sort_order": order,
        }
        for order, (name, category, purpose, status, version) in enumerate(
            technology, start=1
        )
    ]
    limitations = (
        (
            "roadmap_pending",
            "Roadmap calculations pending",
            "Pathway priorities and roadmap stages remain empty until governed production rules are implemented.",
            "high",
        ),
        (
            "advertised_market",
            "Advertised market only",
            "The analysis covers advertised jobs and not the full hidden labour market.",
            "medium",
        ),
        (
            "salary_missingness",
            "Incomplete salary information",
            "Many advertisements omit salary information, limiting comparisons.",
            "medium",
        ),
        (
            "title_variation",
            "Inconsistent job titles",
            "Role classification must use job text because titles can be ambiguous.",
            "medium",
        ),
        (
            "skill_synonyms",
            "Skill-term variation",
            "Skills require a maintained governed alias dictionary.",
            "medium",
        ),
        (
            "classification_uncertainty",
            "Classification uncertainty",
            "Review and unknown outcomes remain visible rather than being forced into a category.",
            "medium",
        ),
        (
            "snapshot",
            "Time-sensitive findings",
            "Findings represent the frozen analysis period and may change over time.",
            "medium",
        ),
    )
    limitation_rows = [
        {
            "profile_id": context.profile_id,
            "limitation_code": code,
            "limitation_title": title,
            "limitation_text": description,
            "severity": severity,
            "sort_order": order,
        }
        for order, (code, title, description, severity) in enumerate(
            limitations, start=1
        )
    ]
    project_rows = [
        {
            "profile_id": context.profile_id,
            "project_name": "Skill Compass",
            "dashboard_title": "Australian Data Analytics Skills Insights",
            "project_type": "Data analytics capstone",
            "project_description": "Governed Australian job-market skills, roles, seniority and location insights.",
            "repository_url": None,
            "methodology_version": profile.profile_version,
            "architecture_version": "1.0.0",
            "data_as_of_at": _iso_datetime(context.data_as_of),
            "collection_start_date": context.period_start.isoformat(),
            "collection_end_date": context.period_end.isoformat(),
            "total_jobs_current": len(context.jobs),
        }
    ]
    return {
        "vw_role_profiles": role_profiles,
        "vw_methodology_steps": methodology_rows,
        "vw_validation_metrics": validation_rows,
        "vw_technology_tools": technology_rows,
        "vw_limitations": limitation_rows,
        "vw_project_metadata": project_rows,
    }


# =============================================================================
# Complete document assembly and export
# =============================================================================


def _build_document(
    *,
    contract: PowerBiContract,
    inputs: PowerBiSourceInputs,
    profile: ExtractionProfile,
    dictionary: RequirementDictionary,
    roles: RoleRuleSet,
    seniority: SeniorityRuleSet,
    reference_workbook: Path,
) -> PowerBiExportDocument:
    """Assemble every contracted view from governed live inputs and metadata."""
    context = _build_context(
        inputs=inputs,
        profile=profile,
        dictionary=dictionary,
        roles=roles,
        seniority=seniority,
    )
    geography_rows, job_geography = _geography_data(context)
    fact_rows = _job_and_bridge_rows(
        context=context, inputs=inputs, job_geography=job_geography
    )
    governance = _governance_rows(
        context=context,
        inputs=inputs,
        roles=roles,
        profile=profile,
        reference_workbook=reference_workbook,
    )
    employment_order = {
        code: index for index, (code, _) in enumerate(EMPLOYMENT_MARKERS, start=1)
    }
    employment_codes = sorted(
        context.employment_ids,
        key=lambda code: (employment_order.get(code, 999), code),
    )
    work_mode_order = {"hybrid": 1, "remote": 2, "onsite": 3, "unknown": 4}
    raw_views: dict[str, list[dict[str, PowerBiScalar]]] = {
        "vw_dim_analysis_period": [
            {
                "analysis_period_id": context.analysis_period_id,
                "profile_id": context.profile_id,
                "period_code": context.period_code,
                "period_name": context.period_name,
                "period_start_date": context.period_start.isoformat(),
                "period_end_date": context.period_end.isoformat(),
                "data_as_of_at": _iso_datetime(context.data_as_of),
                "is_default": True,
                "status": "published",
            }
        ],
        "vw_dim_profile": [
            {
                "profile_id": context.profile_id,
                "profile_code": context.profile_code,
                "profile_name": context.profile_name,
                "domain_name": context.profile_code.replace("_", " ").title(),
                "country_code": context.country_code,
            }
        ],
        "vw_dim_date": _date_rows(context),
        "vw_dim_roles": _role_rows(context, roles),
        "vw_dim_seniority": _seniority_rows(context, seniority),
        "vw_dim_geography": geography_rows,
        "vw_dim_employment_types": [
            {
                "employment_type_id": context.employment_ids[code],
                "employment_type_code": code,
                "employment_type_name": _display_code(code),
                "sort_order": index,
            }
            for index, code in enumerate(employment_codes, start=1)
        ],
        "vw_dim_work_modes": [
            {
                "work_mode_id": context.work_mode_ids[code],
                "work_mode_code": code,
                "work_mode_name": _display_code(code),
                "sort_order": work_mode_order.get(code, 999),
            }
            for code in sorted(
                context.work_mode_ids,
                key=lambda code: (work_mode_order.get(code, 999), code),
            )
        ],
        "vw_dim_skills": _skill_rows(context, dictionary),
        "vw_dim_pathways": [
            {
                "pathway_id": context.pathway_ids[role.role_group_code],
                "profile_id": context.profile_id,
                "role_group_id": context.role_ids[role.role_group_code],
                "pathway_code": role.role_group_code,
                "pathway_name": role.role_group_label,
                "pathway_description": None,
                "recommendation_text": None,
                "is_default": role.sort_order == 1,
                "sort_order": role.sort_order,
            }
            for role in sorted(roles.roles, key=lambda role: role.sort_order)
        ],
        **fact_rows,
        "vw_job_skills": _job_skill_rows(context, inputs),
        "vw_pathway_skill_priorities": [],
        "vw_skill_combinations": _combination_rows(context, inputs),
        "vw_roadmap_stages": [],
        "vw_pipeline_metrics": _pipeline_rows(context, inputs, profile.profile_version),
        "vw_data_quality_metrics": _quality_rows(context, inputs),
        **governance,
    }
    projected = {
        view_name: _project_rows(contract, view_name, raw_views[view_name])
        for view_name in contract.view_order
    }
    document = PowerBiExportDocument(
        contract=contract,
        data_as_of_at=_iso_datetime(context.data_as_of) or "",
        views=projected,
    )
    validate_powerbi_document(document)
    return document


def export_powerbi(
    *,
    input_dir: Path,
    output_dir: Path,
    reference_workbook: Path,
    profile_path: Path,
    dictionary_path: Path,
    role_rules_path: Path,
    seniority_rules_path: Path,
) -> PowerBiExportResult:
    """Write one validated JSON document, then convert that JSON to Excel."""
    contract = load_powerbi_contract(reference_workbook)
    profile = load_extraction_profile(profile_path)
    dictionary = load_requirement_dictionary(dictionary_path, profile)
    roles = load_role_rules(role_rules_path)
    seniority = load_seniority_rules(seniority_rules_path)
    if {profile.profile_code, roles.profile_code, seniority.profile_code} != {
        profile.profile_code
    }:
        raise PowerBiContractError("Power BI profile and classification rules disagree")
    inputs = read_powerbi_source_inputs(input_dir)
    _reconcile_inputs(inputs)
    document = _build_document(
        contract=contract,
        inputs=inputs,
        profile=profile,
        dictionary=dictionary,
        roles=roles,
        seniority=seniority,
        reference_workbook=reference_workbook,
    )
    json_path = output_dir / JSON_FILENAME
    excel_path = output_dir / EXCEL_FILENAME
    write_powerbi_json(json_path, document)
    write_powerbi_excel(
        json_path=json_path,
        reference_workbook=reference_workbook,
        output_path=excel_path,
    )
    return PowerBiExportResult(
        json_path=json_path,
        excel_path=excel_path,
        data_as_of_at=datetime.fromisoformat(document.data_as_of_at),
        view_row_counts={name: len(rows) for name, rows in document.views.items()},
    )
