from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.resume import JobAnalysisResponse, NormalizedRequirements, TypedJobRequirement
from app.services.skill_evidence_index import (
    SKILL_EVIDENCE_INDEX_VERSION,
    SkillEvidenceIndex,
    SkillEvidenceSummary,
)
from app.services.skill_registry import (
    REGISTERED_SKILLS,
    SKILL_REGISTRY_CATEGORIES,
    SKILL_REGISTRY_VERSION,
    SkillDefinition,
    get_skill_definition,
    is_supported_directional_match,
    match_skills,
    normalize_skill_name,
    skill_lookup_key,
)


SKILLS_PLANNER_VERSION = "skills-planner-v1"

SKILLS_PLANNER_UNSUPPORTED_INCLUDED_SKILL = "SKILLS_PLANNER_UNSUPPORTED_INCLUDED_SKILL"
SKILLS_PLANNER_INVALID_EVIDENCE_ID = "SKILLS_PLANNER_INVALID_EVIDENCE_ID"
SKILLS_PLANNER_INVALID_REQUIREMENT_ID = "SKILLS_PLANNER_INVALID_REQUIREMENT_ID"
SKILLS_PLANNER_DUPLICATE_CANONICAL_SKILL = "SKILLS_PLANNER_DUPLICATE_CANONICAL_SKILL"
SKILLS_PLANNER_UNSAFE_DIRECTIONAL_MATCH = "SKILLS_PLANNER_UNSAFE_DIRECTIONAL_MATCH"
SKILLS_PLANNER_PROFILE_ONLY_PRIMARY = "SKILLS_PLANNER_PROFILE_ONLY_PRIMARY"
SKILLS_PLANNER_UNKNOWN_SKILL_INCLUDED = "SKILLS_PLANNER_UNKNOWN_SKILL_INCLUDED"
SKILLS_PLANNER_INVALID_CATEGORY = "SKILLS_PLANNER_INVALID_CATEGORY"
SKILLS_PLANNER_SCORE_OUT_OF_RANGE = "SKILLS_PLANNER_SCORE_OUT_OF_RANGE"
SKILLS_PLANNER_TIER_SCORE_CONFLICT = "SKILLS_PLANNER_TIER_SCORE_CONFLICT"
SKILLS_PLANNER_NONDETERMINISTIC_ORDER = "SKILLS_PLANNER_NONDETERMINISTIC_ORDER"
SKILLS_PLANNER_MISSING_EXCLUSION = "SKILLS_PLANNER_MISSING_EXCLUSION"
SKILLS_PLANNER_METADATA_LEAKAGE = "SKILLS_PLANNER_METADATA_LEAKAGE"

SkillTier = Literal["primary", "secondary", "supporting", "excluded"]
SkillDecision = Literal["included", "excluded"]
SkillPlanValidationStatus = Literal["valid", "valid_with_warnings", "invalid"]


class SkillScoreBreakdown(BaseModel):
    jd_priority: int = Field(alias="jdPriority")
    evidence_strength: int = Field(alias="evidenceStrength")
    recency: int
    frequency: int
    role_relevance: int = Field(alias="roleRelevance")
    exact_match_bonus: int = Field(alias="exactMatchBonus")
    partial_match_penalty: int = Field(alias="partialMatchPenalty")
    profile_only_penalty: int = Field(alias="profileOnlyPenalty")
    generic_skill_penalty: int = Field(alias="genericSkillPenalty")
    final_score: int = Field(alias="finalScore")

    model_config = ConfigDict(populate_by_name=True)


class PlannedSkill(BaseModel):
    skill_id: str = Field(alias="skillId")
    canonical_name: str = Field(alias="canonicalName")
    normalized_value: str = Field(alias="normalizedValue")
    display_name: str = Field(alias="displayName")
    category: str
    tier: SkillTier
    decision: SkillDecision
    match_type: str = Field(alias="matchType")
    match_strength: str = Field(alias="matchStrength")
    score: int
    score_breakdown: SkillScoreBreakdown = Field(alias="scoreBreakdown")
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    evidence_strength: str = Field(alias="evidenceStrength")
    recency: str
    profile_only: bool = Field(alias="profileOnly")
    inclusion_reason: str | None = Field(default=None, alias="inclusionReason")
    exclusion_reason: str | None = Field(default=None, alias="exclusionReason")
    warnings: list[str] = Field(default_factory=list)
    order: int

    model_config = ConfigDict(populate_by_name=True)


class SkillCategoryPlan(BaseModel):
    category: str
    order: int
    skills: list[PlannedSkill] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class ExcludedSkillDecision(BaseModel):
    canonical_name: str | None = Field(default=None, alias="canonicalName")
    original_requirement_value: str = Field(alias="originalRequirementValue")
    requirement_ids: list[str] = Field(default_factory=list, alias="requirementIds")
    exclusion_code: str = Field(alias="exclusionCode")
    reason: str

    model_config = ConfigDict(populate_by_name=True)


class SkillsIntelligence(BaseModel):
    categories: list[SkillCategoryPlan] = Field(default_factory=list)
    included_skills: list[PlannedSkill] = Field(default_factory=list, alias="includedSkills")
    excluded_skills: list[ExcludedSkillDecision] = Field(default_factory=list, alias="excludedSkills")
    planner_version: str = Field(default=SKILLS_PLANNER_VERSION, alias="plannerVersion")
    skill_registry_version: str = Field(default=SKILL_REGISTRY_VERSION, alias="skillRegistryVersion")
    skill_evidence_index_version: str = Field(default=SKILL_EVIDENCE_INDEX_VERSION, alias="skillEvidenceIndexVersion")
    role_family: str = Field(default="General Software Engineering", alias="roleFamily")
    target_role: str = Field(default="", alias="targetRole")
    target_company: str = Field(default="", alias="targetCompany")
    level: str = ""
    validation_status: SkillPlanValidationStatus = Field(alias="validationStatus")
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), alias="createdAt")

    model_config = ConfigDict(populate_by_name=True)


@dataclass(frozen=True)
class ScoreConfig:
    priority_scores: dict[str, int]
    evidence_scores: dict[str, int]
    recency_scores: dict[str, int]
    exact_match_scores: dict[str, int]
    role_relevance_scores: dict[str, int]
    profile_only_penalty: int = -15
    generic_skill_penalty: int = -6
    partial_match_penalty: int = -10
    inclusion_threshold: int = 20


DEFAULT_SCORE_CONFIG = ScoreConfig(
    priority_scores={"critical": 40, "high": 30, "medium": 18, "low": 8, "none": 0},
    evidence_scores={"strong": 25, "medium": 16, "weak": 7},
    recency_scores={"current": 15, "recent": 10, "older": 4, "unknown": 1},
    exact_match_scores={"exact": 10, "alias": 9, "narrower": 6, "broader": 2, "related": 0, "no_match": 0},
    role_relevance_scores={"core": 10, "adjacent": 5, "none": 0},
)

GENERIC_SKILLS = {"Agile", "Scrum", "Software Development Life Cycle", "Code Review", "Technical Leadership"}

ROLE_FAMILY_SKILLS: dict[str, tuple[str, ...]] = {
    ".NET Application Development": ("C#", ".NET", "ASP.NET Core", "ASP.NET MVC", "Entity Framework", "LINQ", "REST APIs", "Web APIs", "SQL Server", "Azure", "React", "TypeScript"),
    "Full Stack Development": ("C#", ".NET", "ASP.NET Core", "REST APIs", "Web APIs", "SQL Server", "React", "Angular", "JavaScript", "TypeScript", "Azure", "Docker"),
    "Production Support / Application Maintenance": ("SQL Server", "SQL", "REST APIs", "Web APIs", "Azure DevOps", "Git", "Jenkins", "Docker", "Postman", "Swagger", "SonarQube"),
    "Data Engineering": ("Python", "SQL", "Azure Data Factory", "Azure Databricks", "Apache Spark", "ETL", "Data Pipelines", "Azure Data Lake", "Azure Synapse Analytics", "SSIS", "SQL Server"),
    "AI / Generative AI Engineering": ("Python", "FastAPI", "Generative AI", "Large Language Models", "Retrieval-Augmented Generation", "LangChain", "Prompt Engineering", "AI Agents", "REST APIs"),
    "Java Backend Development": ("Java", "Spring Boot", "REST APIs", "SQL", "PostgreSQL", "MySQL", "Docker", "Kubernetes", "Git"),
    "Cloud / DevOps": ("Azure", "AWS", "Google Cloud", "Azure DevOps", "CI/CD", "Jenkins", "Docker", "Kubernetes", "Git", "GitHub"),
    "Database Development": ("SQL", "SQL Server", "PostgreSQL", "MySQL", "Oracle", "SSIS", "SSRS"),
}

CATEGORY_ORDER_BY_ROLE: dict[str, tuple[str, ...]] = {
    "Data Engineering": ("Languages", "Data Engineering", "Cloud Platforms", "Databases", "DevOps & CI/CD", "APIs & Integration", "Tools"),
    ".NET Application Development": ("Languages", "Frameworks", "APIs & Integration", "Databases", "Frontend", "Cloud Platforms", "DevOps & CI/CD", "Testing", "Architecture & Practices", "Tools"),
    "Full Stack Development": ("Languages", "Frameworks", "Frontend", "APIs & Integration", "Databases", "Cloud Platforms", "DevOps & CI/CD", "Testing", "Architecture & Practices", "Tools"),
    "AI / Generative AI Engineering": ("Languages", "AI & Machine Learning", "Frameworks", "APIs & Integration", "Data Engineering", "Databases", "Cloud Platforms", "DevOps & CI/CD", "Tools"),
}


def build_skills_intelligence(
    *,
    skill_evidence_index: SkillEvidenceIndex,
    typed_requirements: NormalizedRequirements,
    job_analysis: JobAnalysisResponse | None = None,
    target_context: dict[str, str] | None = None,
    registry: Iterable[SkillDefinition] = REGISTERED_SKILLS,
) -> SkillsIntelligence:
    context = target_context or {}
    target_role = context.get("targetRole") or context.get("target_role") or getattr(getattr(job_analysis, "role_information", None), "title", "")
    target_company = context.get("targetCompany") or context.get("target_company") or ""
    level = context.get("level") or "Senior"
    role_family = classify_skill_role_family(target_role, typed_requirements)
    requirements = _skill_requirements(typed_requirements)
    requirements_by_canonical = _requirements_by_canonical(requirements)
    planned: list[PlannedSkill] = []
    excluded: list[ExcludedSkillDecision] = []

    for summary in skill_evidence_index.summaries:
        skill = _plan_supported_skill(summary, requirements, role_family)
        if skill:
            planned.append(skill)

    covered_requirement_ids = {
        requirement_id
        for item in planned
        if item.decision == "included"
        for requirement_id in item.supported_requirement_ids
    }
    for canonical_name, reqs in sorted(requirements_by_canonical.items()):
        uncovered = [item for item in reqs if item.requirement_id not in covered_requirement_ids]
        if uncovered:
            excluded.append(
                ExcludedSkillDecision(
                    canonicalName=canonical_name,
                    originalRequirementValue=uncovered[0].canonical_term,
                    requirementIds=sorted({item.requirement_id for item in uncovered}),
                    exclusionCode="NO_CANDIDATE_EVIDENCE",
                    reason=f"{canonical_name} is present in the job requirements, but no safe candidate skill evidence supports it.",
                )
            )

    included = _order_planned_skills([item for item in planned if item.decision == "included"], role_family)
    categories = _build_category_plans(included, role_family)
    warnings = _validate_skills_intelligence(included, excluded, skill_evidence_index, requirements, role_family)
    validation_status: SkillPlanValidationStatus = "valid"
    if warnings:
        validation_status = "invalid" if _has_invalid_warning(warnings) else "valid_with_warnings"
    return SkillsIntelligence(
        categories=categories,
        includedSkills=included,
        excludedSkills=excluded,
        roleFamily=role_family,
        targetRole=target_role,
        targetCompany=target_company,
        level=level,
        validationStatus=validation_status,
        warnings=warnings,
    )


def classify_skill_role_family(target_role: str, typed_requirements: NormalizedRequirements) -> str:
    role_text = target_role.casefold()
    text = " ".join([target_role, *[item.canonical_term for item in _all_requirements(typed_requirements)]]).casefold()
    if any(term in role_text for term in ("production support", "application maintenance", "maintain production")):
        return "Production Support / Application Maintenance"
    if "data engineer" in role_text:
        return "Data Engineering"
    if "ai engineer" in role_text or "generative ai" in role_text:
        return "AI / Generative AI Engineering"
    if "full stack" in role_text and any(term in role_text for term in (".net", "asp.net", "c#")):
        return "Full Stack Development"
    if any(term in role_text for term in (".net", "asp.net", "c#")):
        return ".NET Application Development"
    if "java" in role_text:
        return "Java Backend Development"
    if any(term in text for term in ("generative ai", "large language model", "langchain", "rag", "ai engineer")):
        return "AI / Generative AI Engineering"
    if any(term in text for term in ("data engineer", "data factory", "databricks", "spark", "etl", "data pipeline")):
        return "Data Engineering"
    if any(term in text for term in ("production support", "application maintenance", "maintain production", "defect", "troubleshoot")):
        return "Production Support / Application Maintenance"
    if "java" in text or "spring boot" in text:
        return "Java Backend Development"
    if any(term in text for term in (".net", "asp.net", "c#")):
        return ".NET Application Development" if "full stack" not in text else "Full Stack Development"
    if any(term in text for term in ("cloud", "devops", "ci/cd", "docker", "kubernetes")):
        return "Cloud / DevOps"
    if any(term in text for term in ("database", "sql server", "stored procedure")):
        return "Database Development"
    return "General Software Engineering"


def _plan_supported_skill(
    summary: SkillEvidenceSummary,
    requirements: list[TypedJobRequirement],
    role_family: str,
    config: ScoreConfig = DEFAULT_SCORE_CONFIG,
) -> PlannedSkill | None:
    if not summary.canonical_name or not summary.allowed_for_skill_selection:
        return None
    definition = get_skill_definition(summary.canonical_name)
    if not definition:
        return None
    best = _best_requirement_match(summary.canonical_name, requirements)
    match = best[0]
    matched_requirements = best[1]
    jd_priority = _priority_score(matched_requirements)
    role_relevance_kind = _role_relevance(summary.canonical_name, role_family)
    role_relevance = config.role_relevance_scores[role_relevance_kind]
    frequency = _frequency_score(summary)
    exact_bonus = config.exact_match_scores.get(match.match_type, 0)
    partial_penalty = config.partial_match_penalty if match.match_type == "broader" else 0
    profile_penalty = config.profile_only_penalty if summary.profile_only else 0
    generic_penalty = config.generic_skill_penalty if summary.canonical_name in GENERIC_SKILLS and not matched_requirements else 0
    final = _clamp(
        jd_priority
        + config.evidence_scores.get(summary.strongest_evidence, 0)
        + config.recency_scores.get(summary.most_recent_evidence, 0)
        + frequency
        + role_relevance
        + exact_bonus
        + profile_penalty
        + generic_penalty
        + partial_penalty
    )
    breakdown = SkillScoreBreakdown(
        jdPriority=jd_priority,
        evidenceStrength=config.evidence_scores.get(summary.strongest_evidence, 0),
        recency=config.recency_scores.get(summary.most_recent_evidence, 0),
        frequency=frequency,
        roleRelevance=role_relevance,
        exactMatchBonus=exact_bonus,
        partialMatchPenalty=partial_penalty,
        profileOnlyPenalty=profile_penalty,
        genericSkillPenalty=generic_penalty,
        finalScore=final,
    )
    tier = _tier_for_score(final, summary, matched_requirements, match.match_type)
    if tier == "excluded":
        return None
    supported_requirement_ids = sorted({item.requirement_id for item in matched_requirements})
    return PlannedSkill(
        skillId=f"skill-{skill_lookup_key(summary.canonical_name).replace(' ', '-')}",
        canonicalName=summary.canonical_name,
        normalizedValue=summary.normalized_value,
        displayName=summary.canonical_name,
        category=definition.category,
        tier=tier,
        decision="included",
        matchType=match.match_type,
        matchStrength=match.strength,
        score=final,
        scoreBreakdown=breakdown,
        supportingEvidenceIds=summary.evidence_ids,
        supportedRequirementIds=supported_requirement_ids,
        evidenceStrength=summary.strongest_evidence,
        recency=summary.most_recent_evidence,
        profileOnly=summary.profile_only,
        inclusionReason=_inclusion_reason(summary, tier, matched_requirements, role_family),
        exclusionReason=None,
        warnings=summary.warnings,
        order=0,
    )


def _best_requirement_match(canonical_name: str, requirements: list[TypedJobRequirement]):
    matched: list[tuple[Any, TypedJobRequirement]] = []
    no_match = match_skills(canonical_name, "__no_requirement__")
    for requirement in requirements:
        result = match_skills(canonical_name, requirement.canonical_term)
        if result.match_type != "no_match":
            matched.append((result, requirement))
    if not matched:
        return no_match, []
    matched.sort(
        key=lambda item: (
            _match_rank(item[0].match_type),
            _typed_priority_score(item[1]),
            item[1].canonical_term.casefold(),
        ),
        reverse=True,
    )
    best_result = matched[0][0]
    supported_requirements = [
        requirement
        for result, requirement in matched
        if result.allowed_for_evidence_support
    ]
    return best_result, supported_requirements


def _skill_requirements(requirements: NormalizedRequirements) -> list[TypedJobRequirement]:
    candidates = [
        *requirements.technical_requirements,
        *requirements.inferred_requirements,
    ]
    return [item for item in candidates if normalize_skill_name(item.canonical_term).canonical_name]


def _all_requirements(requirements: NormalizedRequirements) -> list[TypedJobRequirement]:
    return [
        *requirements.technical_requirements,
        *requirements.responsibility_requirements,
        *requirements.experience_requirements,
        *requirements.education_requirements,
        *requirements.certification_requirements,
        *requirements.leadership_requirements,
        *requirements.soft_skill_requirements,
        *requirements.domain_requirements,
        *requirements.inferred_requirements,
    ]


def _requirements_by_canonical(requirements: list[TypedJobRequirement]) -> dict[str, list[TypedJobRequirement]]:
    grouped: dict[str, list[TypedJobRequirement]] = {}
    for requirement in requirements:
        canonical = normalize_skill_name(requirement.canonical_term).canonical_name
        if canonical:
            grouped.setdefault(canonical, []).append(requirement)
    return grouped


def _priority_score(requirements: list[TypedJobRequirement], config: ScoreConfig = DEFAULT_SCORE_CONFIG) -> int:
    return max((_typed_priority_score(item, config) for item in requirements), default=0)


def _typed_priority_score(requirement: TypedJobRequirement, config: ScoreConfig = DEFAULT_SCORE_CONFIG) -> int:
    return config.priority_scores.get(str(requirement.priority).split(".")[-1], 0)


def _frequency_score(summary: SkillEvidenceSummary) -> int:
    experience_count = len(summary.experience_ids)
    project_count = len(summary.project_ids)
    if summary.profile_only:
        return 0
    if experience_count >= 2:
        return 10
    if experience_count and project_count:
        return 8
    if experience_count:
        return 6
    if project_count:
        return 4
    return min(3, max(0, len(summary.evidence_ids) - 1))


def _role_relevance(canonical_name: str, role_family: str) -> Literal["core", "adjacent", "none"]:
    core = set(ROLE_FAMILY_SKILLS.get(role_family, ()))
    if canonical_name in core:
        return "core"
    if any(is_supported_directional_match(canonical_name, item) or is_supported_directional_match(item, canonical_name) for item in core):
        return "adjacent"
    return "none"


def _tier_for_score(score: int, summary: SkillEvidenceSummary, matched_requirements: list[TypedJobRequirement], match_type: str) -> SkillTier:
    direct_priority = max((_typed_priority_score(item) for item in matched_requirements), default=0)
    if score >= 70 and summary.strongest_evidence in {"strong", "medium"} and direct_priority >= 30 and match_type in {"exact", "alias", "narrower"} and not summary.profile_only:
        return "primary"
    if score >= 45:
        return "secondary"
    if score >= 20:
        return "supporting"
    return "excluded"


def _order_planned_skills(skills: list[PlannedSkill], role_family: str) -> list[PlannedSkill]:
    ordered = sorted(skills, key=lambda item: _planned_sort_key(item, role_family))
    return [item.model_copy(update={"order": index + 1}) for index, item in enumerate(ordered)]


def _planned_sort_key(skill: PlannedSkill, role_family: str) -> tuple[int, int, int, int, str]:
    return (
        {"primary": 0, "secondary": 1, "supporting": 2, "excluded": 3}[skill.tier],
        -skill.score,
        -{"strong": 2, "medium": 1, "weak": 0}.get(skill.evidence_strength, 0),
        -{"current": 3, "recent": 2, "older": 1, "unknown": 0}.get(skill.recency, 0),
        skill.display_name.casefold(),
    )


def _build_category_plans(skills: list[PlannedSkill], role_family: str) -> list[SkillCategoryPlan]:
    category_order = _category_order(role_family)
    by_category: dict[str, list[PlannedSkill]] = {}
    for skill in skills:
        by_category.setdefault(skill.category, []).append(skill)
    plans: list[SkillCategoryPlan] = []
    for category in sorted(by_category, key=lambda item: (category_order.get(item, 999), item.casefold())):
        plans.append(SkillCategoryPlan(category=category, order=len(plans) + 1, skills=by_category[category]))
    return plans


def _category_order(role_family: str) -> dict[str, int]:
    ordered = CATEGORY_ORDER_BY_ROLE.get(role_family, tuple(SKILL_REGISTRY_CATEGORIES))
    return {category: index for index, category in enumerate(ordered)}


def _validate_skills_intelligence(
    included: list[PlannedSkill],
    excluded: list[ExcludedSkillDecision],
    skill_evidence_index: SkillEvidenceIndex,
    requirements: list[TypedJobRequirement],
    role_family: str,
) -> list[str]:
    warnings: list[str] = []
    evidence_ids = {record.evidence_id for record in skill_evidence_index.records}
    requirement_ids = {item.requirement_id for item in requirements}
    seen: set[str] = set()
    for skill in included:
        if skill.canonical_name in seen:
            warnings.append(SKILLS_PLANNER_DUPLICATE_CANONICAL_SKILL)
        seen.add(skill.canonical_name)
        if not skill.supporting_evidence_ids:
            warnings.append(SKILLS_PLANNER_UNSUPPORTED_INCLUDED_SKILL)
        if any(evidence_id not in evidence_ids for evidence_id in skill.supporting_evidence_ids):
            warnings.append(SKILLS_PLANNER_INVALID_EVIDENCE_ID)
        if any(requirement_id not in requirement_ids for requirement_id in skill.supported_requirement_ids):
            warnings.append(SKILLS_PLANNER_INVALID_REQUIREMENT_ID)
        if skill.match_type in {"broader", "related"} and skill.supported_requirement_ids:
            warnings.append(SKILLS_PLANNER_UNSAFE_DIRECTIONAL_MATCH)
        if skill.profile_only and skill.tier == "primary":
            warnings.append(SKILLS_PLANNER_PROFILE_ONLY_PRIMARY)
        if not get_skill_definition(skill.canonical_name):
            warnings.append(SKILLS_PLANNER_UNKNOWN_SKILL_INCLUDED)
        if skill.category not in SKILL_REGISTRY_CATEGORIES:
            warnings.append(SKILLS_PLANNER_INVALID_CATEGORY)
        if skill.score < 0 or skill.score > 100 or skill.score != skill.score_breakdown.final_score:
            warnings.append(SKILLS_PLANNER_SCORE_OUT_OF_RANGE)
        if skill.tier == "primary" and skill.score < 70 or skill.tier == "secondary" and not 45 <= skill.score <= 100:
            warnings.append(SKILLS_PLANNER_TIER_SCORE_CONFLICT)
        if "SKILL_EVIDENCE_METADATA_LEAKAGE" in skill.warnings:
            warnings.append(SKILLS_PLANNER_METADATA_LEAKAGE)
    if [skill.order for skill in included] != sorted(skill.order for skill in included):
        warnings.append(SKILLS_PLANNER_NONDETERMINISTIC_ORDER)
    excluded_ids = {requirement_id for item in excluded for requirement_id in item.requirement_ids}
    included_ids = {requirement_id for item in included for requirement_id in item.supported_requirement_ids}
    missing_exclusions = {item.requirement_id for item in requirements} - included_ids - excluded_ids
    if missing_exclusions:
        warnings.append(SKILLS_PLANNER_MISSING_EXCLUSION)
    return _dedupe(warnings)


def _has_invalid_warning(warnings: list[str]) -> bool:
    invalid = {
        SKILLS_PLANNER_UNSUPPORTED_INCLUDED_SKILL,
        SKILLS_PLANNER_INVALID_EVIDENCE_ID,
        SKILLS_PLANNER_INVALID_REQUIREMENT_ID,
        SKILLS_PLANNER_DUPLICATE_CANONICAL_SKILL,
        SKILLS_PLANNER_UNSAFE_DIRECTIONAL_MATCH,
        SKILLS_PLANNER_PROFILE_ONLY_PRIMARY,
        SKILLS_PLANNER_UNKNOWN_SKILL_INCLUDED,
        SKILLS_PLANNER_INVALID_CATEGORY,
        SKILLS_PLANNER_SCORE_OUT_OF_RANGE,
        SKILLS_PLANNER_TIER_SCORE_CONFLICT,
        SKILLS_PLANNER_NONDETERMINISTIC_ORDER,
        SKILLS_PLANNER_MISSING_EXCLUSION,
        SKILLS_PLANNER_METADATA_LEAKAGE,
    }
    return any(warning in invalid for warning in warnings)


def _inclusion_reason(summary: SkillEvidenceSummary, tier: SkillTier, requirements: list[TypedJobRequirement], role_family: str) -> str:
    if requirements:
        reqs = ", ".join(sorted({item.canonical_term for item in requirements}))
        return f"{summary.canonical_name} is {tier} because it is supported by candidate evidence and maps to JD requirement(s): {reqs}."
    return f"{summary.canonical_name} is {tier} because it is supported by candidate evidence and relevant to {role_family}."


def _match_rank(match_type: str) -> int:
    return {"exact": 6, "alias": 5, "narrower": 4, "broader": 2, "related": 1, "no_match": 0}.get(match_type, 0)


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def skills_intelligence_stale_reasons(data: dict | None) -> list[str]:
    if not data:
        return ["skills intelligence missing"]
    reasons: list[str] = []
    if (data.get("plannerVersion") or data.get("planner_version")) != SKILLS_PLANNER_VERSION:
        reasons.append("skills planner version changed")
    if (data.get("skillRegistryVersion") or data.get("skill_registry_version")) != SKILL_REGISTRY_VERSION:
        reasons.append("skill registry version changed")
    if (data.get("skillEvidenceIndexVersion") or data.get("skill_evidence_index_version")) != SKILL_EVIDENCE_INDEX_VERSION:
        reasons.append("skill evidence index version changed")
    return reasons


__all__ = [
    "SKILLS_PLANNER_VERSION",
    "SkillScoreBreakdown",
    "PlannedSkill",
    "SkillCategoryPlan",
    "ExcludedSkillDecision",
    "SkillsIntelligence",
    "build_skills_intelligence",
    "classify_skill_role_family",
    "skills_intelligence_stale_reasons",
]
