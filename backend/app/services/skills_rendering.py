from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.services.skill_registry import SKILL_REGISTRY_CATEGORIES, get_skill_definition
from app.services.skills_planner import PlannedSkill, SkillsIntelligence


SKILLS_RENDERING_POLICY_VERSION = "skills-rendering-v1"

SKILLS_RENDER_UNKNOWN_SKILL = "SKILLS_RENDER_UNKNOWN_SKILL"
SKILLS_RENDER_EXCLUDED_SKILL = "SKILLS_RENDER_EXCLUDED_SKILL"
SKILLS_RENDER_DUPLICATE_SKILL = "SKILLS_RENDER_DUPLICATE_SKILL"
SKILLS_RENDER_INVALID_CATEGORY = "SKILLS_RENDER_INVALID_CATEGORY"
SKILLS_RENDER_TOTAL_LIMIT_EXCEEDED = "SKILLS_RENDER_TOTAL_LIMIT_EXCEEDED"
SKILLS_RENDER_CATEGORY_LIMIT_EXCEEDED = "SKILLS_RENDER_CATEGORY_LIMIT_EXCEEDED"
SKILLS_RENDER_PER_CATEGORY_LIMIT_EXCEEDED = "SKILLS_RENDER_PER_CATEGORY_LIMIT_EXCEEDED"
SKILLS_RENDER_SUPPORTING_LIMIT_EXCEEDED = "SKILLS_RENDER_SUPPORTING_LIMIT_EXCEEDED"
SKILLS_RENDER_PROFILE_ONLY_LIMIT_EXCEEDED = "SKILLS_RENDER_PROFILE_ONLY_LIMIT_EXCEEDED"
SKILLS_RENDER_PRIMARY_OMITTED = "SKILLS_RENDER_PRIMARY_OMITTED"
SKILLS_RENDER_ORDER_CHANGED = "SKILLS_RENDER_ORDER_CHANGED"
SKILLS_RENDER_METADATA_LEAKAGE = "SKILLS_RENDER_METADATA_LEAKAGE"
SKILLS_RENDER_NONDETERMINISTIC_OUTPUT = "SKILLS_RENDER_NONDETERMINISTIC_OUTPUT"

SkillRenderValidationStatus = Literal["valid", "valid_with_warnings", "invalid"]


class SkillsRenderingPolicy(BaseModel):
    maximum_total_skills: int = Field(default=24, alias="maximumTotalSkills")
    maximum_categories: int = Field(default=7, alias="maximumCategories")
    maximum_skills_per_category: int = Field(default=6, alias="maximumSkillsPerCategory")
    maximum_supporting_skills: int = Field(default=5, alias="maximumSupportingSkills")
    maximum_profile_only_skills: int = Field(default=1, alias="maximumProfileOnlySkills")
    include_primary: bool = Field(default=True, alias="includePrimary")
    include_secondary: bool = Field(default=True, alias="includeSecondary")
    include_supporting: bool = Field(default=True, alias="includeSupporting")
    omit_empty_categories: bool = Field(default=True, alias="omitEmptyCategories")
    merge_sparse_categories: bool = Field(default=False, alias="mergeSparseCategories")
    minimum_skills_for_standalone_category: int = Field(default=1, alias="minimumSkillsForStandaloneCategory")
    preserve_planner_category_order: bool = Field(default=True, alias="preservePlannerCategoryOrder")
    preserve_planner_skill_order: bool = Field(default=True, alias="preservePlannerSkillOrder")
    policy_version: str = Field(default=SKILLS_RENDERING_POLICY_VERSION, alias="policyVersion")

    model_config = ConfigDict(populate_by_name=True)


class RenderedSkillGroup(BaseModel):
    category: str
    items: list[str] = Field(default_factory=list)
    source_skill_ids: list[str] = Field(default_factory=list, alias="sourceSkillIds")
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")
    rendering_policy_version: str = Field(default=SKILLS_RENDERING_POLICY_VERSION, alias="renderingPolicyVersion")
    planner_version: str = Field(default="", alias="plannerVersion")

    model_config = ConfigDict(populate_by_name=True)


class SkillsRenderingValidationResult(BaseModel):
    validation_status: SkillRenderValidationStatus = Field(alias="validationStatus")
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    rendered_skill_count: int = Field(default=0, alias="renderedSkillCount")
    rendered_category_count: int = Field(default=0, alias="renderedCategoryCount")

    model_config = ConfigDict(populate_by_name=True)


class RenderedSkillsResult(BaseModel):
    groups: list[RenderedSkillGroup] = Field(default_factory=list)
    policy: SkillsRenderingPolicy
    validation: SkillsRenderingValidationResult
    supporting_evidence_ids: list[str] = Field(default_factory=list, alias="supportingEvidenceIds")
    supported_requirement_ids: list[str] = Field(default_factory=list, alias="supportedRequirementIds")

    model_config = ConfigDict(populate_by_name=True)


DEFAULT_SKILLS_RENDERING_POLICY = SkillsRenderingPolicy()


def render_skills_intelligence(
    skills_intelligence: SkillsIntelligence,
    policy: SkillsRenderingPolicy | None = None,
) -> RenderedSkillsResult:
    active_policy = policy or DEFAULT_SKILLS_RENDERING_POLICY
    selected = _select_renderable_skills(skills_intelligence, active_policy)
    groups = _groups_from_selected(selected, skills_intelligence.planner_version)
    validation = validate_rendered_skill_groups(skills_intelligence, groups, active_policy, selected)
    return RenderedSkillsResult(
        groups=groups,
        policy=active_policy,
        validation=validation,
        supportingEvidenceIds=_dedupe([evidence_id for skill in selected for evidence_id in skill.supporting_evidence_ids]),
        supportedRequirementIds=_dedupe([requirement_id for skill in selected for requirement_id in skill.supported_requirement_ids]),
    )


def build_rendered_skill_groups(
    skills_intelligence: SkillsIntelligence,
    policy: SkillsRenderingPolicy | None = None,
) -> list[dict]:
    result = render_skills_intelligence(skills_intelligence, policy)
    return [group.model_dump(mode="json", by_alias=True) for group in result.groups]


def validate_rendered_skill_groups(
    skills_intelligence: SkillsIntelligence,
    groups: list[RenderedSkillGroup],
    policy: SkillsRenderingPolicy | None = None,
    selected_skills: list[PlannedSkill] | None = None,
) -> SkillsRenderingValidationResult:
    active_policy = policy or DEFAULT_SKILLS_RENDERING_POLICY
    errors: list[str] = []
    warnings: list[str] = []
    selected = selected_skills or _skills_from_groups(skills_intelligence, groups)
    rendered_names = [item for group in groups for item in group.items]
    rendered_categories = [group.category for group in groups]
    rendered_skill_count = len(rendered_names)
    supporting_count = sum(1 for skill in selected if skill.tier == "supporting")
    profile_only_count = sum(1 for skill in selected if skill.profile_only)

    if skills_intelligence.validation_status == "invalid":
        errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
    source_errors, source_warnings = _validate_source_skills_intelligence(skills_intelligence)
    errors.extend(source_errors)
    warnings.extend(source_warnings)
    if rendered_skill_count > active_policy.maximum_total_skills:
        errors.append(SKILLS_RENDER_TOTAL_LIMIT_EXCEEDED)
    if len(groups) > active_policy.maximum_categories:
        errors.append(SKILLS_RENDER_CATEGORY_LIMIT_EXCEEDED)
    if supporting_count > active_policy.maximum_supporting_skills:
        errors.append(SKILLS_RENDER_SUPPORTING_LIMIT_EXCEEDED)
    if profile_only_count > active_policy.maximum_profile_only_skills:
        errors.append(SKILLS_RENDER_PROFILE_ONLY_LIMIT_EXCEEDED)
    if len({name.casefold() for name in rendered_names}) != len(rendered_names):
        errors.append(SKILLS_RENDER_DUPLICATE_SKILL)
    if any(category not in SKILL_REGISTRY_CATEGORIES for category in rendered_categories):
        errors.append(SKILLS_RENDER_INVALID_CATEGORY)
    if any(len(group.items) > active_policy.maximum_skills_per_category for group in groups):
        errors.append(SKILLS_RENDER_PER_CATEGORY_LIMIT_EXCEEDED)
    if any(not get_skill_definition(skill.canonical_name) for skill in selected):
        errors.append(SKILLS_RENDER_UNKNOWN_SKILL)
    if _rendered_items_do_not_match_sources(groups, selected):
        errors.append(SKILLS_RENDER_UNKNOWN_SKILL)
    if any(skill.decision != "included" or skill.tier == "excluded" for skill in selected):
        errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
    if any(not skill.supporting_evidence_ids for skill in selected):
        errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
    if any(skill.match_type in {"broader", "related"} and not skill.supported_requirement_ids for skill in selected):
        errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
    if any(_contains_metadata_leakage(value) for value in rendered_names):
        errors.append(SKILLS_RENDER_METADATA_LEAKAGE)
    if _rendered_order_changed(skills_intelligence, selected):
        errors.append(SKILLS_RENDER_ORDER_CHANGED)
    if _lower_tier_selected_after_primary_omission(skills_intelligence, selected):
        warnings.append(SKILLS_RENDER_PRIMARY_OMITTED)
    if [group.model_dump(mode="json", by_alias=True) for group in groups] != build_rendered_skill_groups_from_selected(selected, skills_intelligence.planner_version):
        errors.append(SKILLS_RENDER_NONDETERMINISTIC_OUTPUT)

    errors = _dedupe(errors)
    warnings = _dedupe(warnings)
    return SkillsRenderingValidationResult(
        validationStatus="invalid" if errors else "valid_with_warnings" if warnings else "valid",
        errors=errors,
        warnings=warnings,
        renderedSkillCount=rendered_skill_count,
        renderedCategoryCount=len(groups),
    )


def build_rendered_skill_groups_from_selected(selected: list[PlannedSkill], planner_version: str) -> list[dict]:
    return [
        group.model_dump(mode="json", by_alias=True)
        for group in _groups_from_selected(selected, planner_version)
    ]


def _select_renderable_skills(skills_intelligence: SkillsIntelligence, policy: SkillsRenderingPolicy) -> list[PlannedSkill]:
    selected: list[PlannedSkill] = []
    category_counts: dict[str, int] = defaultdict(int)
    category_order: list[str] = []
    supporting_count = 0
    profile_only_count = 0

    for tier in ("primary", "secondary", "supporting"):
        if tier == "primary" and not policy.include_primary:
            continue
        if tier == "secondary" and not policy.include_secondary:
            continue
        if tier == "supporting" and not policy.include_supporting:
            continue
        for skill in _iter_planner_skills_by_tier(skills_intelligence, tier):
            if not _is_renderable_skill(skill):
                continue
            if len(selected) >= policy.maximum_total_skills:
                return selected
            if category_counts[skill.category] == 0 and len(category_order) >= policy.maximum_categories:
                continue
            if category_counts[skill.category] >= policy.maximum_skills_per_category:
                continue
            if skill.tier == "supporting" and supporting_count >= policy.maximum_supporting_skills:
                continue
            if skill.profile_only and profile_only_count >= policy.maximum_profile_only_skills:
                continue
            selected.append(skill)
            if category_counts[skill.category] == 0:
                category_order.append(skill.category)
            category_counts[skill.category] += 1
            if skill.tier == "supporting":
                supporting_count += 1
            if skill.profile_only:
                profile_only_count += 1
    return selected


def _iter_planner_skills_by_tier(skills_intelligence: SkillsIntelligence, tier: str) -> Iterable[PlannedSkill]:
    for category in sorted(skills_intelligence.categories, key=lambda item: item.order):
        for skill in sorted(category.skills, key=lambda item: item.order):
            if skill.tier == tier:
                yield skill


def _is_renderable_skill(skill: PlannedSkill) -> bool:
    if skill.decision != "included" or skill.tier == "excluded":
        return False
    if not skill.supporting_evidence_ids:
        return False
    if skill.category not in SKILL_REGISTRY_CATEGORIES:
        return False
    if not get_skill_definition(skill.canonical_name):
        return False
    if skill.match_type in {"broader", "related"} and not skill.supported_requirement_ids:
        return False
    if any("METADATA_LEAKAGE" in warning for warning in skill.warnings):
        return False
    return True


def _validate_source_skills_intelligence(skills_intelligence: SkillsIntelligence) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    seen_canonical: set[str] = set()
    excluded_canonical = {
        (item.canonical_name or "").casefold()
        for item in skills_intelligence.excluded_skills
        if item.canonical_name
    }
    included_ids = {skill.skill_id for skill in skills_intelligence.included_skills}
    category_skill_ids: set[str] = set()

    for category in skills_intelligence.categories:
        if category.category not in SKILL_REGISTRY_CATEGORIES:
            errors.append(SKILLS_RENDER_INVALID_CATEGORY)
        for skill in category.skills:
            category_skill_ids.add(skill.skill_id)
            canonical_key = skill.canonical_name.casefold()
            if canonical_key in seen_canonical:
                errors.append(SKILLS_RENDER_DUPLICATE_SKILL)
            seen_canonical.add(canonical_key)
            if canonical_key in excluded_canonical:
                errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
            if skill.decision != "included" or skill.tier == "excluded":
                errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
            if not skill.supporting_evidence_ids:
                errors.append(SKILLS_RENDER_EXCLUDED_SKILL)
            if not get_skill_definition(skill.canonical_name):
                errors.append(SKILLS_RENDER_UNKNOWN_SKILL)
            if skill.category not in SKILL_REGISTRY_CATEGORIES:
                errors.append(SKILLS_RENDER_INVALID_CATEGORY)
            if skill.score < 0 or skill.score > 100 or skill.score != skill.score_breakdown.final_score:
                errors.append(SKILLS_RENDER_TOTAL_LIMIT_EXCEEDED)
            if skill.tier == "primary" and skill.score < 70:
                errors.append(SKILLS_RENDER_PRIMARY_OMITTED)
            if skill.tier == "secondary" and not 45 <= skill.score <= 100:
                errors.append(SKILLS_RENDER_ORDER_CHANGED)
            if skill.profile_only and skill.tier == "primary":
                errors.append(SKILLS_RENDER_PROFILE_ONLY_LIMIT_EXCEEDED)
            if any("METADATA_LEAKAGE" in warning for warning in skill.warnings):
                errors.append(SKILLS_RENDER_METADATA_LEAKAGE)
            if skill.match_type in {"broader", "related"} and not skill.supported_requirement_ids:
                warnings.append(SKILLS_RENDER_EXCLUDED_SKILL)
    if included_ids and category_skill_ids and included_ids != category_skill_ids:
        errors.append(SKILLS_RENDER_NONDETERMINISTIC_OUTPUT)
    return _dedupe(errors), _dedupe(warnings)


def _groups_from_selected(selected: list[PlannedSkill], planner_version: str) -> list[RenderedSkillGroup]:
    grouped: dict[str, list[PlannedSkill]] = defaultdict(list)
    category_order: list[str] = []
    for skill in selected:
        if skill.category not in grouped:
            category_order.append(skill.category)
        grouped[skill.category].append(skill)
    groups: list[RenderedSkillGroup] = []
    for category in category_order:
        skills = grouped[category]
        groups.append(
            RenderedSkillGroup(
                category=category,
                items=[skill.display_name for skill in skills],
                sourceSkillIds=[skill.skill_id for skill in skills],
                supportingEvidenceIds=_dedupe([evidence_id for skill in skills for evidence_id in skill.supporting_evidence_ids]),
                supportedRequirementIds=_dedupe([requirement_id for skill in skills for requirement_id in skill.supported_requirement_ids]),
                renderingPolicyVersion=SKILLS_RENDERING_POLICY_VERSION,
                plannerVersion=planner_version,
            )
        )
    return groups


def _skills_from_groups(skills_intelligence: SkillsIntelligence, groups: list[RenderedSkillGroup]) -> list[PlannedSkill]:
    by_id = {skill.skill_id: skill for category in skills_intelligence.categories for skill in category.skills}
    selected: list[PlannedSkill] = []
    for group in groups:
        for skill_id in group.source_skill_ids:
            skill = by_id.get(skill_id)
            if skill:
                selected.append(skill)
    return selected


def _rendered_items_do_not_match_sources(groups: list[RenderedSkillGroup], selected: list[PlannedSkill]) -> bool:
    by_id = {skill.skill_id: skill for skill in selected}
    for group in groups:
        expected = [by_id[skill_id].display_name for skill_id in group.source_skill_ids if skill_id in by_id]
        if group.items != expected:
            return True
    return False


def _rendered_order_changed(skills_intelligence: SkillsIntelligence, selected: list[PlannedSkill]) -> bool:
    selected_ids = [skill.skill_id for skill in selected]
    expected_ids = [
        skill.skill_id
        for tier in ("primary", "secondary", "supporting")
        for skill in _iter_planner_skills_by_tier(skills_intelligence, tier)
        if skill.skill_id in selected_ids
    ]
    return selected_ids != expected_ids


def _lower_tier_selected_after_primary_omission(skills_intelligence: SkillsIntelligence, selected: list[PlannedSkill]) -> bool:
    selected_ids = {skill.skill_id for skill in selected}
    omitted_primary = [
        skill
        for skill in _iter_planner_skills_by_tier(skills_intelligence, "primary")
        if _is_renderable_skill(skill) and skill.skill_id not in selected_ids
    ]
    lower_selected = any(skill.tier in {"secondary", "supporting"} for skill in selected)
    return bool(omitted_primary and lower_selected)


def _contains_metadata_leakage(value: str) -> bool:
    lowered = value.casefold()
    return any(token in lowered for token in ("evidence:", "requirement:", "match:", "score:", "validation:"))


def _dedupe(values: Iterable[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = str(value).strip().casefold()
        if key and key not in seen:
            seen.add(key)
            output.append(str(value).strip())
    return output


__all__ = [
    "SKILLS_RENDERING_POLICY_VERSION",
    "SkillsRenderingPolicy",
    "RenderedSkillGroup",
    "RenderedSkillsResult",
    "SkillsRenderingValidationResult",
    "render_skills_intelligence",
    "build_rendered_skill_groups",
    "validate_rendered_skill_groups",
]
