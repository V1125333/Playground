import pytest

from app.schemas.resume import (
    ExperienceMetric,
    ExperiencePromptEvidence,
    ExperiencePromptMetric,
    ProfileEvidenceType,
    ResumeGenerationSettings,
    ResumeProject,
)
from app.services.experience_planner import build_experience_intelligence
from app.services.experience_prompt_builder import (
    EXPERIENCE_PROMPT_VERSION,
    PROMPT_CONFLICTING_EXCLUSION,
    PROMPT_METADATA_LEAKAGE,
    PROMPT_PROJECT_WRONG_EXPERIENCE,
    PROMPT_UNSUPPORTED_METRIC,
    build_experience_prompts,
    validate_experience_prompt,
)
from app.services.profile_matching import build_profile_evidence_index, match_job_to_profile
from tests.test_experience_planner import PROFILE_ID, analysis, profile, requirement


def prompt_for(candidate, job_description, *requirements):
    job_analysis = analysis(*requirements)
    match = match_job_to_profile(job_analysis, candidate, PROFILE_ID)
    evidence = build_profile_evidence_index(candidate, PROFILE_ID)
    plan = build_experience_intelligence(
        candidate,
        job_description,
        job_analysis.normalized_requirements,
        match.match_summary,
        evidence,
        ResumeGenerationSettings(bulletsPerRecentRole=5, bulletsPerOlderRole=2),
    )
    plan = build_experience_prompts(
        plan,
        candidate,
        evidence,
        job_analysis.normalized_requirements,
        type("Target", (), {"target_role": "Software Engineer", "target_company": "Acme", "level": "Senior"})(),
        ResumeGenerationSettings(bulletsPerRecentRole=5, bulletsPerOlderRole=2),
    )
    return plan, evidence, job_analysis.normalized_requirements


def test_builds_one_prompt_per_role_plan_with_prompt_version() -> None:
    candidate = profile()
    plan, _, _ = prompt_for(candidate, "Need C#, REST API, SQL Server.", requirement("C#"), requirement("REST API Development"), requirement("SQL Server"))

    assert len(plan.experience_prompt_inputs) == len(plan.roles)
    assert all(prompt.prompt_version == EXPERIENCE_PROMPT_VERSION for prompt in plan.experience_prompt_inputs)
    assert plan.experience_prompt_inputs[0].experience_id == "exp-current"


def test_prompt_is_deterministic_and_minimal() -> None:
    candidate = profile()
    first, _, _ = prompt_for(candidate, "Need C# APIs.", requirement("C#"))
    second, _, _ = prompt_for(candidate, "Need C# APIs.", requirement("C#"))
    payload = first.experience_prompt_inputs[0].model_dump(mode="json", by_alias=True)
    payload_text = str(payload)

    assert payload == second.experience_prompt_inputs[0].model_dump(mode="json", by_alias=True)
    assert "venu@example.com" not in payload_text
    assert "+12014436937" not in payload_text
    assert "education" not in payload_text.lower()
    assert "certification" not in payload_text.lower()
    assert "keywords" not in payload


def test_prompt_uses_role_specific_technologies_and_excludes_profile_only_skill() -> None:
    candidate = profile()
    plan, _, _ = prompt_for(candidate, "Need Java Spring Boot API development.", requirement("Java"), requirement("Spring Boot"))
    current = next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-current")

    technologies = [item.name for item in current.approved_technologies]

    assert "Java" not in technologies
    assert "Spring Boot" not in technologies


@pytest.mark.parametrize(
    ("job_description", "requirements", "expected_family"),
    [
        (
            "Need senior .NET developer with C#, ASP.NET Core, REST API, and SQL Server.",
            [requirement("C#"), requirement("ASP.NET Core"), requirement("SQL Server")],
            "Backend .NET Development",
        ),
        (
            "Need production support engineer to troubleshoot defects, maintain systems, and support deployments.",
            [requirement("Troubleshooting", category="Responsibility"), requirement("Production Support", category="Responsibility")],
            "Production Support / Application Maintenance",
        ),
        (
            "Need data engineer with Python, Spark, Databricks, and SQL transformations.",
            [requirement("Python"), requirement("Spark"), requirement("Databricks")],
            "Data Engineering",
        ),
        (
            "Need AI engineer with Python, FastAPI, and RAG workflows.",
            [requirement("Python"), requirement("FastAPI"), requirement("RAG")],
            "AI / Generative AI Engineering",
        ),
    ],
)
def test_prompt_builder_supports_role_family_scenarios(job_description, requirements, expected_family) -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-ai",
            name="AI Assistant",
            bullets=["Built Python FastAPI RAG workflow for document search."],
            technologies=["Python", "FastAPI", "RAG"],
            linkedExperienceIds=["exp-current"],
        )
    )

    plan, _, _ = prompt_for(candidate, job_description, *requirements)

    assert plan.role_family == expected_family
    assert len(plan.experience_prompt_inputs) == len(plan.roles)
    assert all(prompt.prompt_version == EXPERIENCE_PROMPT_VERSION for prompt in plan.experience_prompt_inputs)


def test_linked_project_is_included_only_for_correct_role() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-ai",
            name="AI Assistant",
            bullets=["Built Python FastAPI RAG workflow for document search."],
            technologies=["Python", "FastAPI"],
            linkedExperienceIds=["exp-current"],
        )
    )

    plan, _, _ = prompt_for(candidate, "Need Python FastAPI RAG.", requirement("Python"), requirement("FastAPI"), requirement("RAG"))
    current = next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-current")
    older = next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-data")

    assert [project.project_id for project in current.linked_projects] == ["project-ai"]
    assert older.linked_projects == []
    assert all(evidence.project_id != "project-ai" for evidence in older.approved_evidence)


def test_unmapped_project_is_excluded_from_prompt() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-ai",
            name="AI Assistant",
            bullets=["Built Python FastAPI RAG workflow for document search."],
            technologies=["FastAPI"],
        )
    )

    plan, _, _ = prompt_for(candidate, "Need FastAPI RAG.", requirement("FastAPI"), requirement("RAG"))

    assert all(not prompt.linked_projects for prompt in plan.experience_prompt_inputs)
    assert all(evidence.project_id != "project-ai" for prompt in plan.experience_prompt_inputs for evidence in prompt.approved_evidence)


def test_explicit_metric_is_included_and_inferred_metric_is_not_created() -> None:
    candidate = profile()
    candidate.experience[0].metrics = [ExperienceMetric(metricId="metric-defects", label="Defect reduction", value="20%")]

    plan, _, _ = prompt_for(candidate, "Need quality improvements and defect reduction.", requirement("Quality Improvements", category="Responsibility"))
    current = next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-current")

    assert any(metric.value == "Defect reduction 20%" for metric in current.approved_metrics)
    assert all(metric.evidence_ids for metric in current.approved_metrics)


def test_validation_rejects_unsupported_metric_and_exclusion_conflict() -> None:
    candidate = profile()
    plan, evidence, requirements = prompt_for(candidate, "Need C# APIs.", requirement("C#"))
    prompt = plan.experience_prompt_inputs[0].model_copy(
        update={
            "approved_metrics": [ExperiencePromptMetric(value="30%", context="invented", evidenceIds=["missing-evidence"])],
            "excluded_terms": [plan.experience_prompt_inputs[0].approved_technologies[0].name if plan.experience_prompt_inputs[0].approved_technologies else "C#"],
        }
    )
    validation = validate_experience_prompt(prompt, plan.roles[0], candidate, evidence, requirements)

    assert PROMPT_UNSUPPORTED_METRIC in validation.codes
    assert PROMPT_CONFLICTING_EXCLUSION in validation.codes


def test_validation_detects_wrong_role_project_and_metadata_leakage() -> None:
    candidate = profile()
    candidate.projects.append(
        ResumeProject(
            projectId="project-current",
            name="Current Project",
            bullets=["Built FastAPI workflow."],
            linkedExperienceIds=["exp-current"],
        )
    )
    plan, evidence, requirements = prompt_for(candidate, "Need FastAPI.", requirement("FastAPI"))
    older_plan = next(role for role in plan.roles if role.experience_id == "exp-data")
    older_prompt = next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-data")
    project_evidence = next(item for item in evidence if item.evidence_type == ProfileEvidenceType.project and item.project_id == "project-current")
    leaked = older_prompt.model_copy(
        update={
            "approved_evidence": [
                ExperiencePromptEvidence(
                    evidenceId=project_evidence.evidence_id,
                    evidenceType="project",
                    text=candidate.experience[1].company,
                    sourceRecordId=project_evidence.source_record_id,
                    projectId=project_evidence.project_id,
                )
            ]
        }
    )
    validation = validate_experience_prompt(leaked, older_plan, candidate, evidence, requirements)

    assert PROMPT_PROJECT_WRONG_EXPERIENCE in validation.codes
    assert PROMPT_METADATA_LEAKAGE in validation.codes
