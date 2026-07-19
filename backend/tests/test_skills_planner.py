from __future__ import annotations

from datetime import date

from app.schemas.resume import CandidateProfile, JobAnalysisResponse, NormalizedRequirements, ResumeExperience, ResumeProject, SkillCategory, TypedJobRequirement
from app.services.skill_evidence_index import build_skill_evidence_index
from app.services.skills_planner import (
    build_skills_intelligence,
    classify_skill_role_family,
    skills_intelligence_stale_reasons,
)


REFERENCE_DATE = date(2026, 7, 19)


def req(term: str, *, priority: str = "critical", category: str = "Technical", requirement_id: str | None = None) -> TypedJobRequirement:
    return TypedJobRequirement(
        requirementId=requirement_id or f"req-{term.casefold().replace(' ', '-').replace('#', 'sharp')}",
        canonicalTerm=term,
        originalTerms=[term],
        category=category,
        requirementLevel="required",
        priority=priority,
        explicit=True,
        evidenceText=f"Requires {term}",
        sourceSentence=f"Requires {term}",
    )


def requirements(*items: TypedJobRequirement) -> NormalizedRequirements:
    return NormalizedRequirements(technicalRequirements=list(items))


def profile_for_planning() -> CandidateProfile:
    return CandidateProfile(
        name="Venu Madhav Pendurthi",
        title="Senior Full Stack .NET Developer",
        skills=[
            SkillCategory(category="Languages", items=["C#", "Python", "JavaScript", "TypeScript", "SQL"]),
            SkillCategory(category="Profile Only", items=["LangChain"]),
        ],
        experience=[
            ResumeExperience(
                experienceId="exp-dotnet",
                company="Infosys",
                role="Senior .NET Developer",
                startDate="2025-01",
                endDate="Present",
                isCurrentRole=True,
                technologies=["C#", ".NET", "ASP.NET Core", "REST APIs", "SQL Server", "Azure", "Azure DevOps", "Docker", "JavaScript", "TypeScript", "React"],
                responsibilities=["Built ASP.NET Core REST APIs and reviewed SQL Server changes."],
            ),
            ResumeExperience(
                experienceId="exp-data",
                company="E-Universe",
                role="Data Engineer",
                startDate="2023-01",
                endDate="2024-12",
                technologies=["Python", "SQL", "Azure Data Factory", "Azure Databricks", "Apache Spark", "ETL", "Data Pipelines"],
                responsibilities=["Built Azure Data Factory and Databricks ETL pipelines with Spark."],
            ),
        ],
        projects=[
            ResumeProject(
                projectId="project-ai",
                name="AI Assistant",
                technologies=["Python", "FastAPI", "Retrieval-Augmented Generation", "Large Language Models", "AI Agents"],
                bullets=["Built a FastAPI RAG workflow with LLM orchestration."],
                linkedExperienceIds=[],
            )
        ],
    )


def plan_for(profile: CandidateProfile, reqs: NormalizedRequirements, *, target_role: str):
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)
    return build_skills_intelligence(
        skill_evidence_index=index,
        typed_requirements=reqs,
        job_analysis=JobAnalysisResponse(roleInformation={"title": target_role}),
        target_context={"targetRole": target_role, "targetCompany": "Acme", "level": "Senior"},
    )


def by_name(plan):
    return {skill.canonical_name: skill for skill in plan.included_skills}


def excluded_names(plan):
    return {item.canonical_name for item in plan.excluded_skills}


def test_dotnet_full_stack_prioritizes_supported_core_stack():
    plan = plan_for(
        profile_for_planning(),
        requirements(req("C#"), req(".NET"), req("ASP.NET Core"), req("REST APIs"), req("SQL Server"), req("Java"), req("Spring Boot")),
        target_role="Senior Full Stack .NET Developer",
    )

    skills = by_name(plan)
    assert plan.role_family == "Full Stack Development"
    for name in ("C#", ".NET", "ASP.NET Core", "REST APIs", "SQL Server"):
        assert skills[name].tier == "primary"
        assert skills[name].supported_requirement_ids
    assert skills["React"].tier in {"secondary", "supporting"}
    assert excluded_names(plan) >= {"Java", "Spring Boot"}


def test_production_support_role_ranks_supported_operational_tools_without_promoting_ai_labels():
    plan = plan_for(
        profile_for_planning(),
        requirements(req("SQL Server"), req("REST APIs"), req("Azure DevOps"), req("LangChain", priority="medium")),
        target_role="Production Support .NET Engineer",
    )

    skills = by_name(plan)
    assert plan.role_family == "Production Support / Application Maintenance"
    assert skills["SQL Server"].tier == "primary"
    assert skills["REST APIs"].tier == "primary"
    assert skills["Azure DevOps"].tier == "primary"
    assert skills["LangChain"].tier != "primary"
    assert skills["LangChain"].profile_only is True


def test_data_engineer_role_prioritizes_supported_data_stack():
    plan = plan_for(
        profile_for_planning(),
        requirements(req("Python"), req("SQL"), req("Azure Data Factory"), req("Azure Databricks"), req("Apache Spark"), req("ETL")),
        target_role="Senior Data Engineer",
    )

    skills = by_name(plan)
    assert plan.role_family == "Data Engineering"
    for name in ("Python", "SQL", "Azure Data Factory", "Azure Databricks", "Apache Spark", "ETL"):
        assert skills[name].tier == "primary"
    assert plan.categories[0].category == "Languages"
    assert "Data Engineering" in [category.category for category in plan.categories]


def test_ai_engineer_role_uses_supported_ai_project_evidence_not_profile_only_inference():
    plan = plan_for(
        profile_for_planning(),
        requirements(req("Python"), req("FastAPI"), req("Retrieval-Augmented Generation"), req("Large Language Models"), req("AI Agents")),
        target_role="AI Engineer",
    )

    skills = by_name(plan)
    assert plan.role_family == "AI / Generative AI Engineering"
    for name in ("Python", "FastAPI", "Retrieval-Augmented Generation", "Large Language Models", "AI Agents"):
        assert skills[name].tier in {"primary", "secondary"}
        assert skills[name].supporting_evidence_ids
    assert "LangChain" not in skills


def test_java_jd_excludes_unsupported_java_and_spring_without_matching_javascript():
    plan = plan_for(
        profile_for_planning(),
        requirements(req("Java"), req("Spring Boot"), req("REST APIs"), req("Docker")),
        target_role="Java Backend Developer",
    )

    assert excluded_names(plan) >= {"Java", "Spring Boot"}
    skills = by_name(plan)
    assert "JavaScript" in skills
    assert "req-java" not in skills["JavaScript"].supported_requirement_ids
    assert skills["REST APIs"].tier in {"primary", "secondary"}
    assert skills["Docker"].tier in {"secondary", "supporting", "primary"}


def test_aws_jd_excludes_aws_when_candidate_only_has_azure():
    plan = plan_for(profile_for_planning(), requirements(req("AWS")), target_role="Cloud Engineer AWS")

    assert "AWS" in excluded_names(plan)
    assert "Azure" in by_name(plan)
    assert by_name(plan)["Azure"].supported_requirement_ids == []


def test_directional_matching_rules_are_respected():
    profile = CandidateProfile(
        name="Directional Tester",
        experience=[
            ResumeExperience(experienceId="exp-adf", company="A", role="Data", isCurrentRole=True, technologies=["Azure Data Factory"]),
            ResumeExperience(experienceId="exp-dotnet", company="B", role="Developer", isCurrentRole=True, technologies=["ASP.NET Core"]),
            ResumeExperience(experienceId="exp-sql", company="C", role="Developer", isCurrentRole=True, technologies=["SQL Server"]),
            ResumeExperience(experienceId="exp-ts", company="D", role="Developer", isCurrentRole=True, technologies=["TypeScript"]),
        ],
    )
    broad = plan_for(profile, requirements(req("Azure"), req(".NET"), req("SQL"), req("JavaScript")), target_role="Full Stack .NET Developer")
    skills = by_name(broad)
    assert skills["Azure Data Factory"].match_type == "narrower"
    assert skills["ASP.NET Core"].match_type == "narrower"
    assert skills["SQL Server"].match_type == "narrower"
    assert skills["TypeScript"].match_type == "narrower"

    narrow = plan_for(
        CandidateProfile(
            name="Broad Tester",
            experience=[ResumeExperience(experienceId="exp-broad", company="A", role="Developer", isCurrentRole=True, technologies=["Azure", ".NET", "SQL", "JavaScript"])],
        ),
        requirements(req("Azure Data Factory"), req("ASP.NET Core"), req("SQL Server"), req("TypeScript")),
        target_role="Full Stack .NET Developer",
    )
    assert excluded_names(narrow) >= {"Azure Data Factory", "ASP.NET Core", "SQL Server", "TypeScript"}
    narrow_skills = by_name(narrow)
    for broader_skill in ("Azure", ".NET", "SQL", "JavaScript"):
        assert narrow_skills[broader_skill].match_type == "broader"
        assert narrow_skills[broader_skill].supported_requirement_ids == []
        assert narrow_skills[broader_skill].score_breakdown.jd_priority == 0
        assert narrow_skills[broader_skill].tier != "primary"


def test_score_components_sum_and_profile_only_penalty_applies():
    plan = plan_for(profile_for_planning(), requirements(req("LangChain")), target_role="AI Engineer")
    skill = by_name(plan)["LangChain"]
    breakdown = skill.score_breakdown

    assert breakdown.profile_only_penalty < 0
    expected = max(
        0,
        min(
            100,
            breakdown.jd_priority
            + breakdown.evidence_strength
            + breakdown.recency
            + breakdown.frequency
            + breakdown.role_relevance
            + breakdown.exact_match_bonus
            + breakdown.profile_only_penalty
            + breakdown.generic_skill_penalty
            + breakdown.partial_match_penalty,
        ),
    )
    assert skill.score == expected
    assert skill.tier != "primary"


def test_related_and_broader_matches_do_not_claim_requirement_support():
    plan = plan_for(
        CandidateProfile(
            name="Unsafe Match Tester",
            experience=[
                ResumeExperience(
                    experienceId="exp-related",
                    company="A",
                    role="Developer",
                    isCurrentRole=True,
                    technologies=["Swagger", ".NET"],
                )
            ],
        ),
        requirements(req("REST APIs"), req("ASP.NET Core")),
        target_role="Senior .NET Developer",
    )

    skills = by_name(plan)
    assert skills["Swagger"].match_type == "related"
    assert skills["Swagger"].supported_requirement_ids == []
    assert skills["Swagger"].score_breakdown.jd_priority == 0
    assert skills[".NET"].match_type == "broader"
    assert skills[".NET"].supported_requirement_ids == []
    assert skills[".NET"].score_breakdown.jd_priority == 0
    assert excluded_names(plan) >= {"REST APIs", "ASP.NET Core"}
    assert plan.validation_status == "valid"


def test_safe_narrower_matches_cover_requirements_without_false_exclusions():
    plan = plan_for(
        CandidateProfile(
            name="Narrower Match Tester",
            experience=[
                ResumeExperience(
                    experienceId="exp-narrow",
                    company="A",
                    role="Developer",
                    isCurrentRole=True,
                    technologies=["ASP.NET Core", "Azure DevOps"],
                )
            ],
        ),
        requirements(req(".NET"), req("CI/CD")),
        target_role="Senior .NET Developer",
    )

    skills = by_name(plan)
    assert skills["ASP.NET Core"].match_type == "narrower"
    assert skills["ASP.NET Core"].supported_requirement_ids == ["req-.net"]
    assert skills["Azure DevOps"].match_type == "narrower"
    assert skills["Azure DevOps"].supported_requirement_ids == ["req-ci/cd"]
    assert ".NET" not in excluded_names(plan)
    assert "CI/CD" not in excluded_names(plan)
    assert plan.validation_status == "valid"


def test_grouping_has_no_empty_categories_and_is_deterministic():
    plan = plan_for(profile_for_planning(), requirements(req("C#"), req("SQL Server"), req("REST APIs")), target_role="Senior Full Stack .NET Developer")

    assert all(category.skills for category in plan.categories)
    assert [skill.order for skill in plan.included_skills] == sorted(skill.order for skill in plan.included_skills)
    assert plan.categories[0].category == "Languages"


def test_skills_intelligence_stale_reasons_cover_versions():
    plan = plan_for(profile_for_planning(), requirements(req("C#")), target_role="Senior .NET Developer")
    data = plan.model_dump(mode="json", by_alias=True)

    assert skills_intelligence_stale_reasons(data) == []
    data["plannerVersion"] = "old"
    assert "skills planner version changed" in skills_intelligence_stale_reasons(data)


def test_role_family_classifier_is_jd_adaptive():
    assert classify_skill_role_family("Senior Data Engineer", requirements(req("Azure Data Factory"))) == "Data Engineering"
    assert classify_skill_role_family("AI Engineer", requirements(req("Large Language Models"))) == "AI / Generative AI Engineering"
