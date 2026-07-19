from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    NormalizedRequirements,
    ResumeContact,
    ResumeExperience,
    ResumeGenerationSettings,
    ResumeProject,
    SkillCategory,
    TypedJobRequirement,
)
from app.services.experience_planner import build_experience_intelligence
from app.services.profile_matching import build_profile_evidence_index, match_job_to_profile


PROFILE_ID = "22222222-2222-2222-2222-222222222222"


def requirement(term: str, *, category: str = "Technical", priority: str = "critical") -> TypedJobRequirement:
    slug = term.lower().replace(" ", "-").replace("#", "sharp").replace("/", "-")
    return TypedJobRequirement(
        requirementId=f"req-{slug}",
        canonicalTerm=term,
        originalTerms=[term],
        category=category,
        requirementLevel="responsibility" if category == "Responsibility" else "required",
        priority=priority,
        explicit=True,
        confidence=0.95,
        evidenceText=f"Need {term}.",
        sourceSentence=f"Need {term}.",
    )


def analysis(*requirements: TypedJobRequirement) -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer", "seniority": "Senior"},
        normalizedRequirements=NormalizedRequirements(
            technicalRequirements=[item for item in requirements if item.category == "Technical"],
            responsibilityRequirements=[item for item in requirements if item.category == "Responsibility"],
            leadershipRequirements=[item for item in requirements if item.category == "Leadership"],
        ),
    )


def profile() -> CandidateProfile:
    return CandidateProfile(
        name="Venu Madhav Pendurthi",
        firstName="Venu",
        lastName="Madhav Pendurthi",
        title="Senior .NET Developer",
        contact=ResumeContact(email="venu@example.com", phone="+12014436937", location="Hartford, CT"),
        skills=[
            SkillCategory(category="Programming Languages", items=["C#", "Java"]),
            SkillCategory(category="Data", items=["Python", "Spark", "Databricks"]),
        ],
        experience=[
            ResumeExperience(
                experienceId="exp-current",
                company="Infosys",
                clientName="Molina Healthcare",
                role="Senior .NET Developer",
                location="Hartford, CT",
                startDate="2025-01",
                endDate="Present",
                isCurrentRole=True,
                responsibilities=[
                    "Built C# REST API enhancements with ASP.NET Core and SQL Server for enterprise workflows.",
                    "Reviewed code, release notes, and implementation details with QA and business stakeholders.",
                    "Resolved production defects by tracing application logs, SQL behavior, and service-layer code paths.",
                ],
                achievements=[
                    "Reduced recurring defects by improving validation coverage before release.",
                ],
                technologies=["C#", "ASP.NET Core", "REST API", "SQL Server"],
            ),
            ResumeExperience(
                experienceId="exp-data",
                company="Tata Consultancy Services",
                role=".NET Developer",
                location="Hyderabad",
                startDate="2016-12",
                endDate="2021-10",
                responsibilities=[
                    "Built Python ETL pipelines with Spark and Databricks for data processing workflows.",
                    "Optimized SQL transformations and batch validation checks for reporting accuracy.",
                ],
                technologies=["Python", "Spark", "Databricks", "SQL"],
            ),
        ],
    )


def build_plan(job_description: str, *requirements: TypedJobRequirement, candidate: CandidateProfile | None = None):
    candidate = candidate or profile()
    job_analysis = analysis(*requirements)
    match = match_job_to_profile(job_analysis, candidate, PROFILE_ID)
    evidence = build_profile_evidence_index(candidate, PROFILE_ID)
    return build_experience_intelligence(
        candidate,
        job_description,
        job_analysis.normalized_requirements,
        match.match_summary,
        evidence,
        ResumeGenerationSettings(bulletsPerRecentRole=5, bulletsPerOlderRole=2),
    )


def test_experience_plan_uses_role_specific_evidence_not_profile_level_skills() -> None:
    plan = build_plan(
        "Need Java and Spring Boot API development.",
        requirement("Java"),
        requirement("Spring Boot"),
        requirement("API Development", category="Responsibility", priority="high"),
    )

    selected_technologies = [technology.name for role in plan.roles for technology in role.selected_technologies]
    selected_evidence_ids = [evidence.evidence_id for role in plan.roles for evidence in role.selected_evidence]

    assert "Java" not in selected_technologies
    assert all("-skill-java" not in evidence_id for evidence_id in selected_evidence_ids)


def test_experience_plan_keeps_technologies_attached_to_their_real_role() -> None:
    plan = build_plan(
        "Need C#, REST APIs, SQL Server, Python, Spark, and Databricks.",
        requirement("C#"),
        requirement("REST API Development"),
        requirement("SQL Server"),
        requirement("Python"),
        requirement("Spark"),
        requirement("Databricks"),
    )

    by_role = {role.experience_id: [technology.name for technology in role.selected_technologies] for role in plan.roles}

    assert "C#" in by_role["exp-current"]
    assert "SQL Server" in by_role["exp-current"]
    assert "Python" not in by_role["exp-current"]
    assert "Python" in by_role["exp-data"]
    assert "Databricks" in by_role["exp-data"]
    assert "C#" not in by_role["exp-data"]


def test_experience_plan_excludes_company_client_location_metadata() -> None:
    plan = build_plan(
        "Need healthcare stakeholder collaboration in Hartford for Molina Healthcare.",
        requirement("Stakeholder Collaboration", category="Responsibility", priority="high"),
        requirement("Healthcare", category="Responsibility", priority="medium"),
    )

    selected_text = " ".join(evidence.text for role in plan.roles for evidence in role.selected_evidence)

    assert "Molina Healthcare" not in selected_text
    assert "Hartford" not in selected_text
    assert all("metadata leakage" not in warning for warning in plan.warnings)


def test_experience_plan_tunes_themes_for_support_focused_jd() -> None:
    plan = build_plan(
        "Troubleshoot production applications, resolve defects, support deployments, and maintain reliable systems.",
        requirement("Production Support", category="Responsibility", priority="high"),
        requirement("Troubleshooting", category="Responsibility", priority="high"),
        requirement("Release Management", category="Responsibility", priority="medium"),
    )

    current = next(role for role in plan.roles if role.experience_id == "exp-current")

    assert plan.role_family == "Production Support / Application Maintenance"
    assert "production reliability" in current.bullet_themes
    assert "release and deployment" in current.bullet_themes


def test_experience_plan_respects_recent_and_older_role_bullet_settings() -> None:
    plan = build_plan(
        "Need C#, SQL Server, Python, Spark, API development, and data engineering.",
        requirement("C#"),
        requirement("SQL Server"),
        requirement("Python"),
        requirement("Spark"),
        requirement("API Development", category="Responsibility", priority="high"),
    )

    current = next(role for role in plan.roles if role.experience_id == "exp-current")
    older = next(role for role in plan.roles if role.experience_id == "exp-data")

    assert current.bullet_count <= 5
    assert older.bullet_count <= 2


def test_full_stack_dotnet_jd_is_not_misclassified_as_database_only() -> None:
    plan = build_plan(
        "Need senior full stack C# .NET ASP.NET Core REST API SQL Server frontend and backend delivery.",
        requirement("C#"),
        requirement("ASP.NET Core"),
        requirement("REST API Development"),
        requirement("SQL Server"),
    )

    assert plan.role_family == "Full Stack .NET Development"


def test_low_relevance_role_evidence_is_not_selected_as_placeholder_planning() -> None:
    plan = build_plan(
        "Need COBOL mainframe payroll batch processing and JCL scheduling.",
        requirement("COBOL"),
        requirement("JCL"),
        requirement("Mainframe Batch Processing", category="Responsibility", priority="high"),
    )

    assert all(role.bullet_count == 0 for role in plan.roles)
    assert all(not role.selected_evidence for role in plan.roles)
    assert plan.validation_status == "warning"
    assert any("insufficient role evidence" in warning for warning in plan.warnings)


def test_selected_technology_requires_jd_or_role_title_support() -> None:
    plan = build_plan(
        "Need data engineer with Python, Spark, Databricks, ETL pipelines, and SQL transformations.",
        requirement("Python"),
        requirement("Spark"),
        requirement("Databricks"),
        requirement("ETL Pipeline Development", category="Responsibility", priority="high"),
    )

    by_role = {role.experience_id: [technology.name for technology in role.selected_technologies] for role in plan.roles}

    assert "C#" not in by_role["exp-current"]
    assert "ASP.NET Core" not in by_role["exp-current"]
    assert "Python" in by_role["exp-data"]
    assert "Spark" in by_role["exp-data"]


def test_project_linked_to_infosys_may_support_infosys_role_plan() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-ai",
            name="AI Search Assistant",
            bullets=["Built Python FastAPI RAG workflow for document search."],
            technologies=["Python", "FastAPI", "RAG"],
            linkedExperienceIds=["exp-current"],
        )
    )

    plan = build_plan(
        "Need Python FastAPI RAG document search experience.",
        requirement("Python"),
        requirement("FastAPI"),
        requirement("RAG"),
        candidate=candidate,
    )

    current = next(role for role in plan.roles if role.experience_id == "exp-current")
    older = next(role for role in plan.roles if role.experience_id == "exp-data")

    assert any(evidence.project_id == "project-ai" for evidence in current.selected_evidence)
    assert any("project-project-ai" == evidence.source_record_id for evidence in current.selected_evidence)
    assert all(evidence.project_id != "project-ai" for evidence in older.selected_evidence)


def test_unmapped_project_is_excluded_from_every_employment_plan() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-ai",
            name="AI Search Assistant",
            bullets=["Built Python FastAPI RAG workflow for document search."],
            technologies=["FastAPI", "RAG"],
        )
    )

    plan = build_plan(
        "Need FastAPI and RAG experience.",
        requirement("FastAPI"),
        requirement("RAG"),
        candidate=candidate,
    )

    assert all(evidence.project_id != "project-ai" for role in plan.roles for evidence in role.selected_evidence)
    assert any("UNMAPPED_PROJECT_EXCLUDED" in warning for warning in plan.warnings)


def test_project_linked_to_infosys_cannot_support_tcs_role_plan() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-current-only",
            name="Current Role API Project",
            bullets=["Built Python API automation for current-role delivery."],
            technologies=["Python"],
            linkedExperienceIds=["exp-current"],
        )
    )

    plan = build_plan(
        "Need Python API automation.",
        requirement("Python"),
        requirement("API Development", category="Responsibility", priority="high"),
        candidate=candidate,
    )

    older = next(role for role in plan.roles if role.experience_id == "exp-data")

    assert all(evidence.project_id != "project-current-only" for evidence in older.selected_evidence)
