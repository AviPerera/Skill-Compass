"""Calculate reconciled channel-neutral job-market facts and aggregates.

This analytics-layer service consumes existing typed canonical outputs. It must
not read files, render graphs, implement source mapping, or persist databases.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations

from skill_compass.schemas.analytics import (
    AnalyticsJobFact,
    AnalyticsJobSkillFact,
    AnalyticsQualityMetric,
    AnalyticsRunResult,
    DistributionMetric,
    RoleSeniorityMetric,
    RoleSummaryMetric,
    SkillCombinationMetric,
    SkillDemandMetric,
    SkillRoleDemandMetric,
)
from skill_compass.schemas.classification import (
    JobProfileRelevance,
    JobRoleClassification,
    JobSeniorityClassification,
    RoleRuleSet,
    SeniorityRuleSet,
)
from skill_compass.schemas.extraction import JobRequirementMatch, RequirementDictionary
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Errors and deterministic numeric helpers
# =============================================================================


class AnalyticsInputError(ValueError):
    """Report an unreconciled or duplicate upstream analytical contract."""


ZERO = Decimal("0")
RATE_QUANTUM = Decimal("0.000001")
AVERAGE_QUANTUM = Decimal("0.01")


def _ratio(numerator: int | Decimal, denominator: int | Decimal) -> Decimal:
    """Return a bounded six-decimal ratio with an explicit zero denominator."""
    if denominator == 0:
        return ZERO
    return (Decimal(numerator) / Decimal(denominator)).quantize(
        RATE_QUANTUM, rounding=ROUND_HALF_UP
    )


def _identity(row: object) -> tuple[str, str]:
    """Return the canonical external identity from a typed upstream record."""
    return (str(getattr(row, "source_code")), str(getattr(row, "source_job_id")))


def _unique_index(
    rows: tuple[object, ...], label: str
) -> dict[tuple[str, str], object]:
    """Index one-row-per-job inputs and reject duplicate canonical identities."""
    indexed: dict[tuple[str, str], object] = {}
    for row in rows:
        key = _identity(row)
        if key in indexed:
            raise AnalyticsInputError(f"duplicate {label} row for {key[0]}:{key[1]}")
        indexed[key] = row
    return indexed


def _require_same_keys(
    expected: set[tuple[str, str]],
    actual: set[tuple[str, str]],
    label: str,
) -> None:
    """Require an exact classifier-grain join and report safe counts only."""
    if actual != expected:
        raise AnalyticsInputError(
            f"{label} does not reconcile to profile relevance: "
            f"{len(expected - actual)} missing, {len(actual - expected)} extra"
        )


def _display_code(code: str) -> str:
    """Convert a stable code to a compact fallback display label."""
    special = {"onsite": "On-site", "unknown": "Not specified"}
    return special.get(code, code.replace("_", " ").title())


# =============================================================================
# Fact construction and input reconciliation
# =============================================================================


def _build_facts(
    *,
    cleaned_jobs: tuple[CleanedJob, ...],
    role_classifications: tuple[JobRoleClassification, ...],
    seniority_classifications: tuple[JobSeniorityClassification, ...],
    relevance_classifications: tuple[JobProfileRelevance, ...],
    requirement_matches: tuple[JobRequirementMatch, ...],
) -> tuple[
    tuple[AnalyticsJobFact, ...],
    tuple[AnalyticsJobSkillFact, ...],
    dict[tuple[str, str], frozenset[str]],
]:
    """Reconcile upstream contracts and construct privacy-safe included facts."""
    cleaned = _unique_index(tuple(cleaned_jobs), "cleaned job")
    roles = _unique_index(tuple(role_classifications), "role classification")
    seniorities = _unique_index(
        tuple(seniority_classifications), "seniority classification"
    )
    relevance = _unique_index(tuple(relevance_classifications), "profile relevance")
    classifier_keys = set(relevance)
    _require_same_keys(classifier_keys, set(roles), "role classification")
    _require_same_keys(classifier_keys, set(seniorities), "seniority classification")
    missing_cleaned = classifier_keys - set(cleaned)
    if missing_cleaned:
        raise AnalyticsInputError(
            f"cleaned jobs are missing {len(missing_cleaned)} classifier identities"
        )

    matches_by_job: dict[tuple[str, str], list[JobRequirementMatch]] = defaultdict(list)
    match_keys: set[tuple[str, str, str]] = set()
    for match in requirement_matches:
        job_key = _identity(match)
        if job_key not in classifier_keys:
            raise AnalyticsInputError(
                "requirement matches contain jobs outside the classifier population"
            )
        match_key = (*job_key, match.requirement_code)
        if match_key in match_keys:
            raise AnalyticsInputError(
                "duplicate job-requirement row for "
                f"{job_key[0]}:{job_key[1]}:{match.requirement_code}"
            )
        match_keys.add(match_key)
        matches_by_job[job_key].append(match)

    included_keys = sorted(
        key for key, row in relevance.items() if row.relevance_status == "included"
    )
    job_facts: list[AnalyticsJobFact] = []
    skill_facts: list[AnalyticsJobSkillFact] = []
    skill_codes_by_job: dict[tuple[str, str], frozenset[str]] = {}
    for key in included_keys:
        job = cleaned[key]
        role = roles[key]
        seniority = seniorities[key]
        decision = relevance[key]
        matches = sorted(
            matches_by_job[key],
            key=lambda row: (row.requirement_code, row.requirement_name),
        )
        skill_codes_by_job[key] = frozenset(
            match.requirement_code
            for match in matches
            if match.requirement_type == "skill"
        )
        job_facts.append(
            AnalyticsJobFact(
                source_code=job.source_code,
                source_job_id=job.source_job_id,
                content_hash=job.content_hash,
                title_clean=job.title_clean,
                state_code=job.state_code,
                state_name=job.state_name,
                city_name=job.city_name,
                primary_employment_type_code=(
                    job.employment_type_codes[0]
                    if job.employment_type_codes
                    else "not_specified"
                ),
                work_mode_code=job.work_mode_code,
                role_group_code=role.role_group_code,
                role_group_label=role.role_group_label,
                role_confidence_score=role.role_confidence_score,
                seniority_code=seniority.seniority_code,
                seniority_label=seniority.seniority_label,
                seniority_rank=seniority.seniority_rank,
                graduate_level_flag=seniority.graduate_level_flag,
                relevance_score=decision.relevance_score,
                distinct_skill_count=len(skill_codes_by_job[key]),
            )
        )
        skill_facts.extend(
            AnalyticsJobSkillFact(
                source_code=match.source_code,
                source_job_id=match.source_job_id,
                requirement_code=match.requirement_code,
                requirement_name=match.requirement_name,
                category_code=match.category_code,
                category_name=match.category_name,
                dashboard_group=match.dashboard_group,
                mention_count=match.evidence_count,
                weighted_match_score=match.extraction_score,
                confidence_level=match.confidence_level,
            )
            for match in matches
            if match.requirement_type == "skill"
        )
    return tuple(job_facts), tuple(skill_facts), skill_codes_by_job


# =============================================================================
# Demand, distribution, and cross-tabulation aggregates
# =============================================================================


def _skill_demand(
    jobs: tuple[AnalyticsJobFact, ...],
    skills: tuple[AnalyticsJobSkillFact, ...],
    dictionary: RequirementDictionary,
) -> tuple[SkillDemandMetric, ...]:
    """Calculate overall distinct-job skill demand including governed zeroes."""
    counts = Counter(row.requirement_code for row in skills)
    denominator = len(jobs)
    ordered = sorted(
        (
            (definition, counts[definition.requirement_code])
            for definition in dictionary.requirements
            if definition.requirement_type == "skill"
        ),
        key=lambda item: (-item[1], item[0].sort_order, item[0].requirement_code),
    )
    return tuple(
        SkillDemandMetric(
            requirement_code=definition.requirement_code,
            requirement_name=definition.requirement_name,
            category_code=definition.category_code,
            category_name=definition.category_name,
            dashboard_group=definition.dashboard_group,
            supporting_job_count=count,
            eligible_job_count=denominator,
            demand_rate=_ratio(count, denominator),
            rank_overall=rank,
        )
        for rank, (definition, count) in enumerate(ordered, start=1)
    )


def _distribution(
    *,
    dimension_name: str,
    values: tuple[tuple[str, str], ...],
    ordered_codes: tuple[str, ...] | None = None,
) -> tuple[DistributionMetric, ...]:
    """Calculate one single-valued categorical distribution."""
    counts = Counter(code for code, _ in values)
    labels = {code: label for code, label in values}
    denominator = len(values)
    codes = (
        tuple(code for code in ordered_codes if code in counts)
        if ordered_codes is not None
        else tuple(sorted(counts, key=lambda code: (-counts[code], labels[code], code)))
    )
    return tuple(
        DistributionMetric(
            dimension_name=dimension_name,
            dimension_code=code,
            dimension_label=labels[code],
            sort_order=index,
            job_count=counts[code],
            eligible_job_count=denominator,
            job_rate=_ratio(counts[code], denominator),
        )
        for index, code in enumerate(codes, start=1)
    )


def _role_metrics(
    jobs: tuple[AnalyticsJobFact, ...],
    roles: RoleRuleSet,
    seniority: SeniorityRuleSet,
) -> tuple[
    tuple[RoleSummaryMetric, ...],
    tuple[RoleSeniorityMetric, ...],
    tuple[DistributionMetric, ...],
]:
    """Calculate governed role and role-seniority analytical outputs."""
    role_rules = {row.role_group_code: row for row in roles.roles}
    approved_jobs = tuple(job for job in jobs if job.role_group_code in role_rules)
    role_denominator = len(approved_jobs)
    summaries: list[RoleSummaryMetric] = []
    cross_tabs: list[RoleSeniorityMetric] = []
    seniority_levels = tuple(sorted(seniority.levels, key=lambda row: row.rank_order))
    for role in sorted(roles.roles, key=lambda row: row.sort_order):
        role_jobs = tuple(
            job for job in approved_jobs if job.role_group_code == role.role_group_code
        )
        role_count = len(role_jobs)
        classified_seniority_count = sum(
            job.seniority_rank is not None for job in role_jobs
        )
        skill_total = sum(job.distinct_skill_count for job in role_jobs)
        graduate_count = sum(job.graduate_level_flag for job in role_jobs)
        summaries.append(
            RoleSummaryMetric(
                role_group_code=role.role_group_code,
                role_group_label=role.role_group_label,
                sort_order=role.sort_order,
                job_count=role_count,
                eligible_job_count=role_denominator,
                job_share=_ratio(role_count, role_denominator),
                average_distinct_skills=(
                    (Decimal(skill_total) / Decimal(role_count)).quantize(
                        AVERAGE_QUANTUM, rounding=ROUND_HALF_UP
                    )
                    if role_count
                    else ZERO
                ),
                graduate_level_count=graduate_count,
                graduate_level_rate=_ratio(graduate_count, role_count),
            )
        )
        for level in seniority_levels:
            count = sum(job.seniority_code == level.seniority_code for job in role_jobs)
            cross_tabs.append(
                RoleSeniorityMetric(
                    role_group_code=role.role_group_code,
                    role_group_label=role.role_group_label,
                    role_sort_order=role.sort_order,
                    seniority_code=level.seniority_code,
                    seniority_label=level.seniority_label,
                    seniority_rank=level.rank_order,
                    job_count=count,
                    role_job_count=classified_seniority_count,
                    role_rate=_ratio(count, classified_seniority_count),
                )
            )
    seniority_values = tuple(
        (job.seniority_code, job.seniority_label)
        for job in jobs
        if job.seniority_rank is not None
    )
    seniority_distribution = _distribution(
        dimension_name="seniority",
        values=seniority_values,
        ordered_codes=tuple(level.seniority_code for level in seniority_levels),
    )
    return tuple(summaries), tuple(cross_tabs), seniority_distribution


def _skill_role_demand(
    jobs: tuple[AnalyticsJobFact, ...],
    skills: tuple[AnalyticsJobSkillFact, ...],
    dictionary: RequirementDictionary,
    roles: RoleRuleSet,
) -> tuple[SkillRoleDemandMetric, ...]:
    """Calculate each governed skill's demand within each governed role."""
    job_role = {_identity(job): job.role_group_code for job in jobs}
    counts = Counter(
        (job_role[_identity(skill)], skill.requirement_code)
        for skill in skills
        if _identity(skill) in job_role
    )
    role_counts = Counter(job.role_group_code for job in jobs)
    rows: list[SkillRoleDemandMetric] = []
    for role in sorted(roles.roles, key=lambda row: row.sort_order):
        denominator = role_counts[role.role_group_code]
        for definition in sorted(
            dictionary.requirements, key=lambda row: row.sort_order
        ):
            if definition.requirement_type != "skill":
                continue
            count = counts[(role.role_group_code, definition.requirement_code)]
            rows.append(
                SkillRoleDemandMetric(
                    role_group_code=role.role_group_code,
                    role_group_label=role.role_group_label,
                    role_sort_order=role.sort_order,
                    requirement_code=definition.requirement_code,
                    requirement_name=definition.requirement_name,
                    category_code=definition.category_code,
                    dashboard_group=definition.dashboard_group,
                    supporting_job_count=count,
                    eligible_job_count=denominator,
                    demand_rate=_ratio(count, denominator),
                )
            )
    return tuple(rows)


# =============================================================================
# Skill-combination analytics
# =============================================================================


def _combination_scope(
    *,
    scope_code: str,
    scope_label: str,
    graduate_friendly_flag: bool,
    job_keys: tuple[tuple[str, str], ...],
    skill_codes_by_job: Mapping[tuple[str, str], frozenset[str]],
    skill_names: Mapping[str, str],
    minimum_sample_size: int,
) -> tuple[SkillCombinationMetric, ...]:
    """Calculate deterministic pair/triple association metrics for one cohort."""
    denominator = len(job_keys)
    individual_counts = Counter(
        skill for key in job_keys for skill in skill_codes_by_job.get(key, frozenset())
    )
    rows: list[SkillCombinationMetric] = []
    for size in (2, 3):
        counts: Counter[tuple[str, ...]] = Counter()
        for key in job_keys:
            counts.update(combinations(sorted(skill_codes_by_job.get(key, ())), size))
        ordered = sorted(
            counts.items(),
            key=lambda item: (
                -item[1],
                tuple(skill_names.get(code, code) for code in item[0]),
            ),
        )
        for rank, (codes, count) in enumerate(ordered, start=1):
            support = _ratio(count, denominator)
            minimum_item_count = min(individual_counts[code] for code in codes)
            confidence = _ratio(count, minimum_item_count)
            independent_support = Decimal("1")
            for code in codes:
                independent_support *= _ratio(individual_counts[code], denominator)
            lift = (
                (support / independent_support).quantize(
                    RATE_QUANTUM, rounding=ROUND_HALF_UP
                )
                if independent_support
                else ZERO
            )
            rows.append(
                SkillCombinationMetric(
                    scope_code=scope_code,
                    scope_label=scope_label,
                    graduate_friendly_flag=graduate_friendly_flag,
                    combination_size=size,
                    requirement_codes=codes,
                    combination_label=" + ".join(
                        skill_names.get(code, code) for code in codes
                    ),
                    supporting_job_count=count,
                    eligible_job_count=denominator,
                    job_percentage=support,
                    support=support,
                    confidence=confidence,
                    lift=lift,
                    combination_rank=rank,
                    sample_size_warning_flag=denominator < minimum_sample_size,
                )
            )
    return tuple(rows)


def _skill_combinations(
    jobs: tuple[AnalyticsJobFact, ...],
    skill_codes_by_job: Mapping[tuple[str, str], frozenset[str]],
    dictionary: RequirementDictionary,
    roles: RoleRuleSet,
    minimum_sample_size: int,
) -> tuple[SkillCombinationMetric, ...]:
    """Calculate overall and graduate-friendly role/pathway combinations."""
    names = {
        row.requirement_code: row.requirement_name for row in dictionary.requirements
    }
    all_keys = tuple(_identity(job) for job in jobs)
    rows = list(
        _combination_scope(
            scope_code="all",
            scope_label="All Included Jobs",
            graduate_friendly_flag=False,
            job_keys=all_keys,
            skill_codes_by_job=skill_codes_by_job,
            skill_names=names,
            minimum_sample_size=minimum_sample_size,
        )
    )
    for role in sorted(roles.roles, key=lambda row: row.sort_order):
        keys = tuple(
            _identity(job)
            for job in jobs
            if job.role_group_code == role.role_group_code and job.graduate_level_flag
        )
        rows.extend(
            _combination_scope(
                scope_code=role.role_group_code,
                scope_label=f"{role.role_group_label} - Graduate Friendly",
                graduate_friendly_flag=True,
                job_keys=keys,
                skill_codes_by_job=skill_codes_by_job,
                skill_names=names,
                minimum_sample_size=minimum_sample_size,
            )
        )
    return tuple(rows)


# =============================================================================
# Public analytics service
# =============================================================================


def build_analytics(
    *,
    cleaned_jobs: tuple[CleanedJob, ...],
    role_classifications: tuple[JobRoleClassification, ...],
    seniority_classifications: tuple[JobSeniorityClassification, ...],
    relevance_classifications: tuple[JobProfileRelevance, ...],
    requirement_matches: tuple[JobRequirementMatch, ...],
    role_rules: RoleRuleSet,
    seniority_rules: SeniorityRuleSet,
    requirement_dictionary: RequirementDictionary,
    minimum_sample_size: int = 20,
) -> AnalyticsRunResult:
    """Build deterministic facts and all currently governed analytics outputs."""
    if minimum_sample_size < 1:
        raise AnalyticsInputError("minimum_sample_size must be at least one")
    profiles = {row.profile_code for row in relevance_classifications}
    if len(profiles) != 1 or profiles != {role_rules.profile_code}:
        raise AnalyticsInputError("profile relevance and analytics rules must agree")
    if seniority_rules.profile_code != role_rules.profile_code:
        raise AnalyticsInputError("role and seniority rules must share one profile")

    job_facts, job_skill_facts, skills_by_job = _build_facts(
        cleaned_jobs=cleaned_jobs,
        role_classifications=role_classifications,
        seniority_classifications=seniority_classifications,
        relevance_classifications=relevance_classifications,
        requirement_matches=requirement_matches,
    )
    skill_demand = _skill_demand(job_facts, job_skill_facts, requirement_dictionary)
    role_summary, role_seniority, seniority_distribution = _role_metrics(
        job_facts, role_rules, seniority_rules
    )
    skill_role_demand = _skill_role_demand(
        job_facts, job_skill_facts, requirement_dictionary, role_rules
    )
    state_values = tuple(
        (job.state_code or "not_specified", job.state_name or "Not specified")
        for job in job_facts
    )
    city_values = tuple(
        (job.city_name or "not_specified", job.city_name or "Not specified")
        for job in job_facts
    )
    employment_values = tuple(
        (
            job.primary_employment_type_code,
            _display_code(job.primary_employment_type_code),
        )
        for job in job_facts
    )
    work_mode_values = tuple(
        (job.work_mode_code, _display_code(job.work_mode_code)) for job in job_facts
    )
    state_distribution = _distribution(dimension_name="state", values=state_values)
    city_distribution = _distribution(dimension_name="city", values=city_values)
    employment_distribution = _distribution(
        dimension_name="employment_type", values=employment_values
    )
    work_mode_distribution = _distribution(
        dimension_name="work_mode", values=work_mode_values
    )
    skill_combinations = _skill_combinations(
        job_facts,
        skills_by_job,
        requirement_dictionary,
        role_rules,
        minimum_sample_size,
    )
    statuses = Counter(row.relevance_status for row in relevance_classifications)
    approved_role_codes = {row.role_group_code for row in role_rules.roles}
    quality = (
        AnalyticsQualityMetric(
            metric_category="reconciliation",
            metric_name="classifier_inputs_reconciled",
            metric_value="true",
            metric_status="pass",
            metric_detail="Role, seniority, and relevance identities reconcile exactly.",
        ),
        AnalyticsQualityMetric(
            metric_category="population",
            metric_name="cleaned_jobs_outside_classifier_population",
            metric_value=str(len(cleaned_jobs) - len(relevance_classifications)),
            metric_status="info",
            metric_detail="Upstream analytically ineligible cleaned jobs remain outside Feature 8.",
        ),
        AnalyticsQualityMetric(
            metric_category="coverage",
            metric_name="included_jobs_without_dashboard_role",
            metric_value=str(
                sum(job.role_group_code not in approved_role_codes for job in job_facts)
            ),
            metric_status="info",
            metric_detail="Included jobs with Other/Review roles remain in overall totals only.",
        ),
        AnalyticsQualityMetric(
            metric_category="privacy",
            metric_name="private_text_exported",
            metric_value="false",
            metric_status="pass",
            metric_detail="No descriptions, evidence snippets, contacts, or tracking values are exported.",
        ),
    )
    return AnalyticsRunResult(
        profile_code=role_rules.profile_code,
        input_cleaned_job_count=len(cleaned_jobs),
        classifier_input_job_count=len(relevance_classifications),
        included_job_count=statuses["included"],
        excluded_job_count=statuses["excluded"],
        review_job_count=statuses["review"],
        job_facts=job_facts,
        job_skill_facts=job_skill_facts,
        skill_demand=skill_demand,
        skill_role_demand=skill_role_demand,
        role_summary=role_summary,
        role_seniority=role_seniority,
        seniority_distribution=seniority_distribution,
        state_distribution=state_distribution,
        city_distribution=city_distribution,
        employment_type_distribution=employment_distribution,
        work_mode_distribution=work_mode_distribution,
        skill_combinations=skill_combinations,
        quality_metrics=quality,
        reconciliation_passed=True,
    )
