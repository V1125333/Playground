from __future__ import annotations

from app.services.skill_evidence_index import SKILL_EVIDENCE_INDEX_VERSION
from app.services.skill_registry import SKILL_REGISTRY_VERSION
from app.services.skills_planner import SKILLS_PLANNER_VERSION, SkillCategoryPlan, SkillScoreBreakdown, SkillsIntelligence, PlannedSkill
from app.services.skills_rendering import (
    SKILLS_RENDER_EXCLUDED_SKILL,
    SKILLS_RENDER_PRIMARY_OMITTED,
    SKILLS_RENDERING_POLICY_VERSION,
    SkillsRenderingPolicy,
    render_skills_intelligence,
    validate_rendered_skill_groups,
)


def planned_skill(
    name: str,
    *,
    skill_id: str | None = None,
    category: str = "Languages",
    tier: str = "primary",
    match_type: str = "exact",
    evidence_ids: list[str] | None = None,
    requirement_ids: list[str] | None = None,
    profile_only: bool = False,
    order: int = 1,
    decision: str = "included",
) -> PlannedSkill:
    score = 90 if tier == "primary" else 65 if tier == "secondary" else 30
    return PlannedSkill(
        skillId=skill_id or f"skill-{name.casefold().replace('#', 'sharp').replace(' ', '-')}",
        canonicalName=name,
        normalizedValue=name.casefold(),
        displayName=name,
        category=category,
        tier=tier,
        decision=decision,
        matchType=match_type,
        matchStrength="exact" if match_type in {"exact", "alias"} else "partial",
        score=score,
        scoreBreakdown=SkillScoreBreakdown(
            jdPriority=40 if requirement_ids else 0,
            evidenceStrength=25,
            recency=15,
            frequency=5,
            roleRelevance=10,
            exactMatchBonus=10 if match_type == "exact" else 0,
            partialMatchPenalty=0,
            profileOnlyPenalty=-15 if profile_only else 0,
            genericSkillPenalty=0,
            finalScore=score,
        ),
        supportingEvidenceIds=evidence_ids if evidence_ids is not None else [f"evidence-{name.casefold()}"],
        supportedRequirementIds=requirement_ids if requirement_ids is not None else [f"req-{name.casefold()}"],
        evidenceStrength="strong",
        recency="current",
        profileOnly=profile_only,
        inclusionReason=f"{name} is supported.",
        exclusionReason=None,
        warnings=[],
        order=order,
    )


def intelligence(skills: list[PlannedSkill]) -> SkillsIntelligence:
    by_category: dict[str, list[PlannedSkill]] = {}
    for skill in skills:
        by_category.setdefault(skill.category, []).append(skill)
    categories = [
        SkillCategoryPlan(category=category, order=index + 1, skills=items)
        for index, (category, items) in enumerate(by_category.items())
    ]
    return SkillsIntelligence(
        categories=categories,
        includedSkills=skills,
        excludedSkills=[],
        plannerVersion=SKILLS_PLANNER_VERSION,
        skillRegistryVersion=SKILL_REGISTRY_VERSION,
        skillEvidenceIndexVersion=SKILL_EVIDENCE_INDEX_VERSION,
        roleFamily=".NET Application Development",
        targetRole="Senior .NET Developer",
        targetCompany="Example",
        level="Senior",
        validationStatus="valid",
        warnings=[],
    )


def test_render_skills_preserves_planner_tier_category_and_skill_order() -> None:
    data = intelligence(
        [
            planned_skill("C#", order=1),
            planned_skill("ASP.NET Core", category="Frameworks", order=2),
            planned_skill("SQL Server", category="Databases", tier="secondary", order=3),
            planned_skill("Git", category="DevOps & CI/CD", tier="supporting", order=4, requirement_ids=[]),
        ]
    )

    result = render_skills_intelligence(data)

    assert result.validation.validation_status == "valid"
    assert [(group.category, group.items) for group in result.groups] == [
        ("Languages", ["C#"]),
        ("Frameworks", ["ASP.NET Core"]),
        ("Databases", ["SQL Server"]),
        ("DevOps & CI/CD", ["Git"]),
    ]
    assert result.groups[0].rendering_policy_version == SKILLS_RENDERING_POLICY_VERSION


def test_render_skills_applies_total_category_and_per_category_limits() -> None:
    data = intelligence(
        [
            planned_skill("C#", order=1),
            planned_skill("JavaScript", order=2),
            planned_skill("SQL Server", category="Databases", tier="secondary", order=3),
            planned_skill("Git", category="DevOps & CI/CD", tier="supporting", order=4, requirement_ids=[]),
        ]
    )

    result = render_skills_intelligence(
        data,
        SkillsRenderingPolicy(maximumTotalSkills=2, maximumCategories=2, maximumSkillsPerCategory=1),
    )

    assert result.validation.validation_status == "valid_with_warnings"
    assert SKILLS_RENDER_PRIMARY_OMITTED in result.validation.warnings
    assert [(group.category, group.items) for group in result.groups] == [
        ("Languages", ["C#"]),
        ("Databases", ["SQL Server"]),
    ]


def test_render_skills_never_renders_unsafe_or_excluded_skills() -> None:
    data = intelligence(
        [
            planned_skill("C#", order=1),
            planned_skill("Azure", category="Cloud Platforms", tier="secondary", match_type="related", requirement_ids=[], order=2),
            planned_skill("Java", category="Languages", evidence_ids=[], requirement_ids=["req-java"], order=3),
            planned_skill("Spring Boot", category="Frameworks", decision="excluded", order=4),
        ]
    )

    result = render_skills_intelligence(data)

    assert result.validation.validation_status == "invalid"
    assert SKILLS_RENDER_EXCLUDED_SKILL in result.validation.errors
    assert [(group.category, group.items) for group in result.groups] == [("Languages", ["C#"])]


def test_render_skills_reports_valid_with_warnings_when_lower_tier_selected_after_primary_omission() -> None:
    data = intelligence(
        [
            planned_skill("C#", order=1),
            planned_skill("SQL Server", category="Databases", order=2),
            planned_skill("JavaScript", tier="secondary", order=3),
        ]
    )

    result = render_skills_intelligence(
        data,
        SkillsRenderingPolicy(maximumTotalSkills=2, maximumCategories=1, maximumSkillsPerCategory=2),
    )

    assert result.validation.validation_status == "valid_with_warnings"
    assert result.validation.errors == []
    assert SKILLS_RENDER_PRIMARY_OMITTED in result.validation.warnings
    assert [(group.category, group.items) for group in result.groups] == [("Languages", ["C#", "JavaScript"])]


def test_validate_rendered_skill_groups_rejects_unknown_externally_supplied_items() -> None:
    data = intelligence([planned_skill("C#", order=1)])
    result = render_skills_intelligence(data)
    tampered = result.groups[0].model_copy(update={"items": ["C#", "Invented Skill"]})

    validation = validate_rendered_skill_groups(data, [tampered], selected_skills=[data.categories[0].skills[0]])

    assert validation.validation_status == "invalid"
    assert SKILLS_RENDER_EXCLUDED_SKILL not in validation.errors
