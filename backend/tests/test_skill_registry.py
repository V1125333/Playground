from __future__ import annotations

from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    KeywordSourceType,
    NormalizedRequirements,
    ResumeGenerationSettings,
    SkillCategory,
)
from app.services.experience_planner import build_experience_intelligence
from app.services.profile_matching import build_profile_evidence_index, match_job_to_profile
from app.services.skill_registry import (
    SKILL_REGISTRY_CATEGORIES,
    get_parent_concepts,
    get_related_concepts,
    get_skill_category,
    get_skill_definition,
    is_supported_directional_match,
    list_registered_skills,
    match_skills,
    normalize_skill_name,
    resolve_skill_alias,
    validate_skill_registry,
)


def test_exact_skill_normalization() -> None:
    assert normalize_skill_name("C#").model_dump(by_alias=True) == {
        "originalValue": "C#",
        "canonicalName": "C#",
        "normalizedValue": "c sharp",
        "matchType": "exact",
        "category": "Languages",
        "warnings": [],
    }
    assert normalize_skill_name("Python").canonical_name == "Python"
    assert normalize_skill_name("Azure Data Factory").canonical_name == "Azure Data Factory"
    assert normalize_skill_name("SQL Server").canonical_name == "SQL Server"


def test_alias_skill_normalization() -> None:
    cases = {
        "c sharp": "C#",
        "dotnet": ".NET",
        "mssql": "SQL Server",
        "postgres": "PostgreSQL",
        "adf": "Azure Data Factory",
        "restful api": "REST APIs",
        "ci cd": "CI/CD",
        "rag": "Retrieval-Augmented Generation",
        "Azure Data Factory (ADF)": "Azure Data Factory",
    }
    for raw, canonical in cases.items():
        result = normalize_skill_name(raw)
        assert result.canonical_name == canonical
        assert result.match_type in {"alias", "normalized"}


def test_unknown_values_are_not_forced_to_nearest_skill() -> None:
    unknown = normalize_skill_name("DefinitelyUnknownTool")
    blank = normalize_skill_name("   ")

    assert unknown.canonical_name is None
    assert unknown.match_type == "unknown"
    assert unknown.warnings == ["unknown_skill"]
    assert blank.canonical_name is None
    assert blank.normalized_value == ""
    assert blank.warnings == ["blank_skill"]
    assert match_skills("Java", "JavaScript").match_type == "no_match"
    assert match_skills("Spring Boot", ".NET").match_type == "no_match"
    assert match_skills("AWS", "Azure").match_type == "no_match"


def test_directional_matches_are_safe_and_explicit() -> None:
    asp_to_dotnet = match_skills("ASP.NET Core", ".NET")
    dotnet_to_asp = match_skills(".NET", "ASP.NET Core")
    adf_to_azure = match_skills("Azure Data Factory", "Azure")
    azure_to_adf = match_skills("Azure", "Azure Data Factory")
    sql_server_to_sql = match_skills("SQL Server", "SQL")
    sql_to_sql_server = match_skills("SQL", "SQL Server")
    ts_to_js = match_skills("TypeScript", "JavaScript")
    js_to_ts = match_skills("JavaScript", "TypeScript")

    assert asp_to_dotnet.match_type == "narrower"
    assert asp_to_dotnet.strength == "strong"
    assert asp_to_dotnet.allowed_for_evidence_support is True
    assert dotnet_to_asp.match_type == "broader"
    assert dotnet_to_asp.allowed_for_evidence_support is False
    assert adf_to_azure.allowed_for_evidence_support is True
    assert azure_to_adf.allowed_for_evidence_support is False
    assert sql_server_to_sql.allowed_for_evidence_support is True
    assert sql_to_sql_server.allowed_for_evidence_support is False
    assert ts_to_js.allowed_for_evidence_support is True
    assert js_to_ts.allowed_for_evidence_support is False
    assert is_supported_directional_match("SQL Server", "SQL") is True
    assert is_supported_directional_match("SQL", "SQL Server") is False


def test_category_assignment_and_definition_helpers() -> None:
    expected = {
        "C#": "Languages",
        "ASP.NET Core": "Frameworks",
        "Azure": "Cloud Platforms",
        "Azure Data Factory": "Data Engineering",
        "SQL Server": "Databases",
        "REST APIs": "APIs & Integration",
        "Docker": "DevOps & CI/CD",
        "Retrieval-Augmented Generation": "AI & Machine Learning",
    }
    for skill, category in expected.items():
        assert get_skill_category(skill) == category

    assert get_skill_definition("mssql").canonical_name == "SQL Server"
    assert resolve_skill_alias("dot net") == ".NET"
    assert get_parent_concepts("Azure Data Factory") == ["Azure", "ETL", "Data Pipelines"]
    assert "REST APIs" in get_related_concepts("ASP.NET Core")


def test_registry_integrity() -> None:
    assert validate_skill_registry() == []
    definitions = list_registered_skills()
    canonical_names = [definition.canonical_name for definition in definitions]
    normalized_values = [definition.normalized_value for definition in definitions]
    display_orders = [definition.display_order for definition in definitions]

    assert len(canonical_names) == len(set(canonical_names))
    assert len(normalized_values) == len(set(normalized_values))
    assert display_orders == sorted(display_orders)
    assert all(definition.category in SKILL_REGISTRY_CATEGORIES for definition in definitions)


def test_registry_is_additive_and_does_not_change_existing_profile_matching_flow() -> None:
    profile = CandidateProfile(
        name="Venu Pendurthi",
        title="Senior .NET Developer",
        skills=[SkillCategory(category="Backend Development", items=["ASP.NET Core"])],
        experience=[],
    )
    analysis = JobAnalysisResponse(
        title="Software Engineer",
        company="Example",
        level="Senior",
        summary="Need .NET development.",
        detectedRole={"title": "Software Engineer", "seniority": "Senior", "experience": "", "domain": ""},
        keywords=[
            JobKeywordAnalysisItem(
                id="kw-dotnet",
                term=".NET",
                value=".NET",
                normalizedValue=".NET",
                category="Frameworks",
                priority="high",
                priorityScore=90,
                sourceType=KeywordSourceType.explicit,
                sourceText=".NET development",
                confidence="high",
                reason="Explicit requirement.",
            )
        ],
        explicitKeywords=[],
        inferredKeywords=[],
        suggestedKeywords=[],
        excludedKeywords=[],
        analysisHash="analysis-hash",
    )

    result = match_job_to_profile(analysis, profile)

    assert len(result.match_summary.matched_requirements) == 1
    assert result.match_summary.matched_requirements[0].requirement_value == ".NET"


def test_registry_is_additive_and_does_not_change_experience_planner_flow() -> None:
    profile = CandidateProfile(
        name="Venu Pendurthi",
        title="Senior .NET Developer",
        skills=[SkillCategory(category="Backend Development", items=["ASP.NET Core"])],
        experience=[],
    )
    analysis = JobAnalysisResponse(
        title="Software Engineer",
        company="Example",
        level="Senior",
        summary="Need C# delivery.",
        detectedRole={"title": "Software Engineer", "seniority": "Senior", "experience": "", "domain": ""},
        keywords=[],
        explicitKeywords=[],
        inferredKeywords=[],
        suggestedKeywords=[],
        excludedKeywords=[],
        analysisHash="analysis-hash",
    )
    match = match_job_to_profile(analysis, profile)

    plan = build_experience_intelligence(
        profile,
        "Need C# delivery.",
        analysis.normalized_requirements or NormalizedRequirements(),
        match.match_summary,
        build_profile_evidence_index(profile, "profile-compat"),
        ResumeGenerationSettings(),
    )

    assert plan.planner_version
    assert plan.validation_status in {"valid", "valid_with_warnings"}
