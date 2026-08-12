"""Classify cleaned jobs into governed seniority levels with bounded evidence.

This engine consumes only typed canonical jobs and declarative rules; it must
not read files, infer roles or relevance, persist data, or know actor fields.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from skill_compass.classification.errors import SeniorityReconciliationError
from skill_compass.classification.seniority_config import APPROVED_SAFETY_LABELS
from skill_compass.schemas.classification import (
    JobSeniorityClassification,
    SeniorityClassificationEvidence,
    SeniorityClassificationQuality,
    SeniorityClassificationRunResult,
    SeniorityDistributionSummary,
    SeniorityReviewQueueItem,
    SeniorityRule,
    SeniorityRuleSet,
)
from skill_compass.schemas.jobs import CleanedJob

# =============================================================================
# Deterministic text and experience parsing
# =============================================================================


SCORE_QUANTUM = Decimal("0.0001")
CONTEXT_SECTION_ORDER = (
    "summary_text_clean",
    "bullet_points_clean",
    "description_text_clean",
)
NORMALIZATION_PATTERN = re.compile(r"[^a-z0-9]+")
EXPERIENCE_PATTERN = re.compile(
    r"\b(?P<minimum>\d{1,2})\s*"
    r"(?:(?P<plus>\+)|(?:-|–|—|to)\s*(?P<maximum>\d{1,2}))?\s*"
    r"(?:years?|yrs?)\b[\u2019']?(?:\s+of)?"
    r"(?:\s+(?:relevant|professional|industry|commercial|practical|work))*"
    r"\s+experience\b",
    re.IGNORECASE,
)


def _normalize(value: str | None) -> str:
    """Normalize configured phrases and canonical text for boundary matching."""
    return NORMALIZATION_PATTERN.sub(" ", (value or "").casefold()).strip()


def _contains_phrase(text: str, term: str) -> bool:
    """Match a complete normalized phrase without substring false positives."""
    normalized_text = _normalize(text)
    normalized_term = _normalize(term)
    if not normalized_text or not normalized_term:
        return False
    return f" {normalized_term} " in f" {normalized_text} "


def _longest_match(text: str, terms: tuple[str, ...]) -> str | None:
    """Choose one deterministic longest matching term from a term group."""
    matches = [term for term in terms if _contains_phrase(text, term)]
    if not matches:
        return None
    return sorted(matches, key=lambda term: (-len(_normalize(term)), _normalize(term)))[
        0
    ]


def _bounded_score(value: Decimal) -> Decimal:
    """Clamp one evidence-strength score to 0-1 and four decimal places."""
    return min(Decimal("1"), max(Decimal("0"), value)).quantize(
        SCORE_QUANTUM, rounding=ROUND_HALF_UP
    )


def _weighted_value(base: Decimal, multiplier: Decimal = Decimal("1")) -> Decimal:
    """Return one stable signed evidence contribution."""
    return (base * multiplier).quantize(SCORE_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True, slots=True)
class _ExperienceMatch:
    """Keep one bounded years-of-experience phrase and numeric interval."""

    section: str
    term: str
    minimum_years: int
    maximum_years: int | None
    section_multiplier: Decimal


def _experience_matches(
    job: CleanedJob, rules: SeniorityRuleSet
) -> tuple[_ExperienceMatch, ...]:
    """Extract distinct experience intervals at their strongest matching section."""
    section_values = {
        "summary_text_clean": job.summary_text_clean or "",
        "bullet_points_clean": " ".join(job.bullet_points_clean),
        "description_text_clean": job.description_text_clean or "",
    }
    matches_by_key: dict[tuple[int, int | None, str], _ExperienceMatch] = {}
    for section in CONTEXT_SECTION_ORDER:
        multiplier = rules.section_multipliers[section]
        for match in EXPERIENCE_PATTERN.finditer(section_values[section]):
            minimum = int(match.group("minimum"))
            maximum_text = match.group("maximum")
            maximum = (
                None
                if match.group("plus") is not None
                else int(maximum_text)
                if maximum_text is not None
                else minimum
            )
            if minimum > 50 or (
                maximum is not None and (maximum < minimum or maximum > 50)
            ):
                continue
            term = " ".join(match.group(0).split())
            key = (minimum, maximum, _normalize(term))
            candidate = _ExperienceMatch(
                section=section,
                term=term,
                minimum_years=minimum,
                maximum_years=maximum,
                section_multiplier=multiplier,
            )
            previous = matches_by_key.get(key)
            if (
                previous is None
                or candidate.section_multiplier > previous.section_multiplier
            ):
                matches_by_key[key] = candidate
    return tuple(
        sorted(
            matches_by_key.values(),
            key=lambda item: (
                -item.section_multiplier,
                item.minimum_years,
                item.maximum_years if item.maximum_years is not None else 51,
                _normalize(item.term),
            ),
        )
    )


def _year_in_level(years: int, level_code: str, rules: SeniorityRuleSet) -> bool:
    """Return whether a parsed year endpoint belongs to one configured band."""
    band = next(
        item for item in rules.experience_bands if item.seniority_code == level_code
    )
    return years >= band.minimum_years and (
        band.maximum_years is None or years <= band.maximum_years
    )


# =============================================================================
# Candidate evidence collection and scoring
# =============================================================================


@dataclass(frozen=True, slots=True)
class _SeniorityCandidate:
    """Keep one internal seniority candidate and its evidence."""

    rule: SeniorityRule
    score: Decimal
    positive_score: Decimal
    evidence: tuple[SeniorityClassificationEvidence, ...]


def _evidence(
    *,
    job: CleanedJob,
    rule: SeniorityRule,
    section: str,
    term: str,
    evidence_type: str,
    weight: Decimal,
    effect: str,
    max_length: int,
    experience_minimum: int | None = None,
    experience_maximum: int | None = None,
) -> SeniorityClassificationEvidence:
    """Build one bounded typed evidence record."""
    return SeniorityClassificationEvidence.model_validate(
        {
            "source_code": job.source_code,
            "source_job_id": job.source_job_id,
            "seniority_code": rule.seniority_code,
            "evidence_section": section,
            "evidence_term": " ".join(term.split())[:max_length],
            "evidence_type": evidence_type,
            "evidence_weight": weight,
            "evidence_effect": effect,
            "experience_years_min": experience_minimum,
            "experience_years_max": experience_maximum,
        }
    )


def _title_evidence(
    job: CleanedJob, rule: SeniorityRule, rules: SeniorityRuleSet
) -> list[SeniorityClassificationEvidence]:
    """Apply one positive and at most one conflicting title contribution."""
    rows: list[SeniorityClassificationEvidence] = []
    strong_match = _longest_match(job.title_clean, rule.strong_title_terms)
    supporting_match = None
    if strong_match is None:
        supporting_match = _longest_match(job.title_clean, rule.supporting_title_terms)
    if strong_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=strong_match,
                evidence_type="strong_title",
                weight=rules.weights.strong_title,
                effect="positive",
                max_length=rules.evidence_term_max_length,
            )
        )
    elif supporting_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=supporting_match,
                evidence_type="supporting_title",
                weight=rules.weights.supporting_title,
                effect="supporting",
                max_length=rules.evidence_term_max_length,
            )
        )

    conflicting_match = _longest_match(job.title_clean, rule.conflicting_title_terms)
    if conflicting_match is not None:
        rows.append(
            _evidence(
                job=job,
                rule=rule,
                section="title_clean",
                term=conflicting_match,
                evidence_type="conflicting_title",
                weight=-rules.weights.conflicting_title,
                effect="conflicting",
                max_length=rules.evidence_term_max_length,
            )
        )
    return rows


def _context_evidence(
    job: CleanedJob, rule: SeniorityRule, rules: SeniorityRuleSet
) -> list[SeniorityClassificationEvidence]:
    """Count each configured context phrase once at its strongest section."""
    section_values = {
        "summary_text_clean": job.summary_text_clean or "",
        "bullet_points_clean": " ".join(job.bullet_points_clean),
        "description_text_clean": job.description_text_clean or "",
    }
    matches: list[tuple[Decimal, str, str]] = []
    for term in rule.context_terms:
        matching_sections = [
            section
            for section in CONTEXT_SECTION_ORDER
            if _contains_phrase(section_values[section], term)
        ]
        if not matching_sections:
            continue
        section = sorted(
            matching_sections,
            key=lambda name: (
                -rules.section_multipliers[name],
                CONTEXT_SECTION_ORDER.index(name),
            ),
        )[0]
        weight = _weighted_value(
            rules.weights.context_term, rules.section_multipliers[section]
        )
        matches.append((weight, term, section))
    selected = sorted(
        matches, key=lambda item: (-item[0], _normalize(item[1]), item[2])
    )[: rules.max_context_terms_per_level]
    return [
        _evidence(
            job=job,
            rule=rule,
            section=section,
            term=term,
            evidence_type="context_term",
            weight=weight,
            effect="supporting",
            max_length=rules.evidence_term_max_length,
        )
        for weight, term, section in selected
    ]


def _experience_evidence(
    job: CleanedJob,
    rule: SeniorityRule,
    rules: SeniorityRuleSet,
    matches: tuple[_ExperienceMatch, ...],
) -> list[SeniorityClassificationEvidence]:
    """Map exact or range endpoints to configured seniority experience bands."""
    selected = [
        match
        for match in matches
        if _year_in_level(match.minimum_years, rule.seniority_code, rules)
        or (
            match.maximum_years is not None
            and _year_in_level(match.maximum_years, rule.seniority_code, rules)
        )
    ][: rules.max_experience_evidence_per_level]
    return [
        _evidence(
            job=job,
            rule=rule,
            section=match.section,
            term=match.term,
            evidence_type="experience",
            weight=_weighted_value(rules.weights.experience, match.section_multiplier),
            effect="supporting",
            max_length=rules.evidence_term_max_length,
            experience_minimum=match.minimum_years,
            experience_maximum=match.maximum_years,
        )
        for match in selected
    ]


def _employment_evidence(
    job: CleanedJob, rule: SeniorityRule, rules: SeniorityRuleSet
) -> list[SeniorityClassificationEvidence]:
    """Use configured canonical employment codes as limited supporting evidence."""
    matches = sorted(
        set(job.employment_type_codes).intersection(rule.employment_type_hints)
    )
    return [
        _evidence(
            job=job,
            rule=rule,
            section="employment_type_codes",
            term=term,
            evidence_type="employment_hint",
            weight=rules.weights.employment_hint,
            effect="supporting",
            max_length=rules.evidence_term_max_length,
        )
        for term in matches[:1]
    ]


def _score_candidate(
    job: CleanedJob,
    rule: SeniorityRule,
    rules: SeniorityRuleSet,
    experience_matches: tuple[_ExperienceMatch, ...],
) -> _SeniorityCandidate:
    """Evaluate one level from bounded title, context, experience, and employment evidence."""
    evidence = [
        *_title_evidence(job, rule, rules),
        *_context_evidence(job, rule, rules),
        *_experience_evidence(job, rule, rules, experience_matches),
        *_employment_evidence(job, rule, rules),
    ]
    positive_score = sum(
        (row.evidence_weight for row in evidence if row.evidence_weight > 0),
        Decimal("0"),
    )
    score = sum((row.evidence_weight for row in evidence), Decimal("0"))
    return _SeniorityCandidate(
        rule=rule,
        score=_bounded_score(score),
        positive_score=_bounded_score(positive_score),
        evidence=tuple(evidence),
    )


# =============================================================================
# Final decision and run aggregation
# =============================================================================


def _confidence_level(score: Decimal, rules: SeniorityRuleSet) -> str:
    """Convert a strength score into one configured display band."""
    if score >= rules.thresholds.high_confidence_min:
        return "high"
    if score >= rules.thresholds.medium_confidence_min:
        return "medium"
    return "low"


def _material_conflict(
    candidates: tuple[_SeniorityCandidate, ...], rules: SeniorityRuleSet
) -> bool:
    """Detect incompatible title markers or distant title/experience evidence."""
    title_candidates = [
        candidate
        for candidate in candidates
        if any(
            row.evidence_type in {"strong_title", "supporting_title"}
            and row.evidence_weight > 0
            for row in candidate.evidence
        )
    ]
    strong_title_candidates = [
        candidate
        for candidate in title_candidates
        if any(row.evidence_type == "strong_title" for row in candidate.evidence)
    ]
    if len(strong_title_candidates) > 1:
        return True
    experience_candidates = [
        candidate
        for candidate in candidates
        if any(row.evidence_type == "experience" for row in candidate.evidence)
    ]
    return any(
        title.rule.seniority_code != experience.rule.seniority_code
        and abs(title.rule.rank_order - experience.rule.rank_order)
        >= rules.thresholds.experience_conflict_rank_gap
        for title in title_candidates
        for experience in experience_candidates
    )


def classify_job_seniority(
    job: CleanedJob, rules: SeniorityRuleSet
) -> tuple[JobSeniorityClassification, tuple[SeniorityClassificationEvidence, ...]]:
    """Classify one canonical job and return bounded relevant evidence."""
    experience_matches = _experience_matches(job, rules)
    candidates = tuple(
        sorted(
            (
                _score_candidate(job, level, rules, experience_matches)
                for level in rules.levels
            ),
            key=lambda candidate: (-candidate.score, candidate.rule.rank_order),
        )
    )
    top, second = candidates[:2]
    meaningful = top.positive_score >= rules.thresholds.meaningful_evidence_score
    second_meaningful = (
        second.positive_score >= rules.thresholds.meaningful_evidence_score
    )
    close_competitor = (
        second_meaningful
        and top.score - second.score <= rules.thresholds.ambiguity_margin
    )
    conflict_flag = _material_conflict(candidates, rules)

    if not meaningful:
        final_code = "unknown"
        final_label = APPROVED_SAFETY_LABELS[final_code]
        final_rank = None
        graduate_flag = False
        review_flag = False
        reason = "No seniority level has meaningful positive evidence."
    elif conflict_flag:
        final_code = "review"
        final_label = APPROVED_SAFETY_LABELS[final_code]
        final_rank = None
        graduate_flag = False
        review_flag = True
        reason = "Seniority evidence contains a material conflict."
    elif close_competitor:
        final_code = "review"
        final_label = APPROVED_SAFETY_LABELS[final_code]
        final_rank = None
        graduate_flag = False
        review_flag = True
        reason = "Leading seniority candidates are inside the ambiguity margin."
    elif top.score < rules.thresholds.minimum_classification_score:
        final_code = "review"
        final_label = APPROVED_SAFETY_LABELS[final_code]
        final_rank = None
        graduate_flag = False
        review_flag = True
        reason = "Meaningful seniority evidence is below the classification threshold."
    else:
        final_code = top.rule.seniority_code
        final_label = top.rule.seniority_label
        final_rank = top.rule.rank_order
        graduate_flag = top.rule.graduate_level_flag
        review_flag = False
        reason = "Clear seniority evidence exceeds the classification threshold."

    first_code = top.rule.seniority_code if meaningful else None
    first_score = top.score if meaningful else None
    second_code = second.rule.seniority_code if second_meaningful else None
    second_score = second.score if second_meaningful else None
    relevant_codes = {code for code in (first_code, second_code) if code is not None}
    if not relevant_codes:
        relevant_codes = {
            candidate.rule.seniority_code
            for candidate in candidates
            if candidate.positive_score > 0
        }
    if conflict_flag:
        relevant_codes.update(
            candidate.rule.seniority_code
            for candidate in candidates
            if any(
                row.evidence_type in {"strong_title", "supporting_title", "experience"}
                for row in candidate.evidence
            )
        )
    relevant_evidence = tuple(
        row
        for candidate in candidates
        if candidate.rule.seniority_code in relevant_codes
        for row in candidate.evidence
    )
    result = JobSeniorityClassification(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        seniority_code=final_code,
        seniority_label=final_label,
        seniority_rank=final_rank,
        graduate_level_flag=graduate_flag,
        seniority_confidence_score=top.score,
        seniority_confidence_level=_confidence_level(top.score, rules),
        seniority_review_flag=review_flag,
        seniority_conflict_flag=conflict_flag,
        seniority_reason=reason,
        candidate_seniority_1_code=first_code,
        candidate_seniority_1_score=first_score,
        candidate_seniority_2_code=second_code,
        candidate_seniority_2_score=second_score,
        seniority_classifier_version=rules.seniority_classifier_version,
        seniority_rules_version=rules.seniority_rules_version,
        seniority_rules_hash=rules.seniority_rules_hash,
    )
    return result, relevant_evidence


def _build_review_item(
    job: CleanedJob,
    result: JobSeniorityClassification,
    evidence: tuple[SeniorityClassificationEvidence, ...],
    rules: SeniorityRuleSet,
) -> SeniorityReviewQueueItem:
    """Build one privacy-safe Review row with bounded evidence terms."""
    compact = "; ".join(
        f"{row.seniority_code}:{row.evidence_section}:{row.evidence_term}"
        for row in evidence
    )
    return SeniorityReviewQueueItem(
        source_code=job.source_code,
        source_job_id=job.source_job_id,
        title_clean=" ".join(job.title_clean.split())[:160],
        candidate_seniority_1_code=result.candidate_seniority_1_code,
        candidate_seniority_1_score=result.candidate_seniority_1_score,
        candidate_seniority_2_code=result.candidate_seniority_2_code,
        candidate_seniority_2_score=result.candidate_seniority_2_score,
        seniority_reason=result.seniority_reason,
        bounded_evidence=compact[: rules.review_evidence_max_length],
    )


def classify_seniority(
    jobs: tuple[CleanedJob, ...], rules: SeniorityRuleSet
) -> SeniorityClassificationRunResult:
    """Classify all cleaned jobs and construct reconciled seniority outputs."""
    classifications: list[JobSeniorityClassification] = []
    evidence_rows: list[SeniorityClassificationEvidence] = []
    review_rows: list[SeniorityReviewQueueItem] = []
    for job in jobs:
        result, evidence = classify_job_seniority(job, rules)
        classifications.append(result)
        evidence_rows.extend(evidence)
        if result.seniority_review_flag:
            review_rows.append(_build_review_item(job, result, evidence, rules))

    counts = Counter(row.seniority_code for row in classifications)
    level_lookup = {level.seniority_code: level for level in rules.levels}
    ordered_codes = [level.seniority_code for level in rules.levels] + [
        "unknown",
        "review",
    ]
    denominator = len(jobs)
    distribution = tuple(
        SeniorityDistributionSummary(
            seniority_code=code,
            seniority_label=(
                level_lookup[code].seniority_label
                if code in level_lookup
                else APPROVED_SAFETY_LABELS[code]
            ),
            seniority_rank=(
                level_lookup[code].rank_order if code in level_lookup else None
            ),
            graduate_level_flag=(
                level_lookup[code].graduate_level_flag
                if code in level_lookup
                else False
            ),
            job_count=counts[code],
            job_share=(
                _bounded_score(Decimal(counts[code]) / Decimal(denominator))
                if denominator
                else Decimal("0")
            ),
        )
        for code in ordered_codes
    )
    classified_count = sum(counts[code] for code in ordered_codes[:4])
    graduate_count = counts["entry_level"] + counts["junior"]
    unknown_count = counts["unknown"]
    review_count = counts["review"]
    confidence_counts = Counter(
        row.seniority_confidence_level for row in classifications
    )
    quality = SeniorityClassificationQuality(
        total_jobs_received=denominator,
        classified_into_dashboard_level=classified_count,
        graduate_level_count=graduate_count,
        graduate_level_rate=(
            _bounded_score(Decimal(graduate_count) / Decimal(denominator))
            if denominator
            else Decimal("0")
        ),
        unknown_count=unknown_count,
        unknown_rate=(
            _bounded_score(Decimal(unknown_count) / Decimal(denominator))
            if denominator
            else Decimal("0")
        ),
        review_count=review_count,
        review_rate=(
            _bounded_score(Decimal(review_count) / Decimal(denominator))
            if denominator
            else Decimal("0")
        ),
        high_confidence_count=confidence_counts["high"],
        medium_confidence_count=confidence_counts["medium"],
        low_confidence_count=confidence_counts["low"],
        missing_title_count=sum(not job.title_clean.strip() for job in jobs),
        missing_description_count=sum(not job.description_text_clean for job in jobs),
        jobs_without_seniority_evidence=sum(
            row.seniority_code == "unknown" and row.seniority_confidence_score == 0
            for row in classifications
        ),
        jobs_with_conflicting_evidence=sum(
            row.seniority_conflict_flag for row in classifications
        ),
        reconciliation_status=(
            "pass" if sum(counts.values()) == denominator else "fail"
        ),
        denominator_definition=(
            "All cleaned jobs received; four levels, Unknown, and Review included."
        ),
    )
    reconciliation_passed = (
        len(classifications) == denominator
        and sum(row.job_count for row in distribution) == denominator
        and len(review_rows) == review_count
        and quality.reconciliation_status == "pass"
    )
    if not reconciliation_passed:
        raise SeniorityReconciliationError(
            "seniority classifications, distribution, or review queue did not reconcile"
        )
    return SeniorityClassificationRunResult(
        rules=rules,
        input_job_count=denominator,
        classifications=tuple(classifications),
        evidence=tuple(evidence_rows),
        distribution=distribution,
        quality=quality,
        review_queue=tuple(review_rows),
        reconciliation_passed=True,
    )
