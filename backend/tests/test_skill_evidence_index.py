from __future__ import annotations

from datetime import date

import pytest

from app.schemas.resume import (
    CandidateProfile,
    ExperienceMetric,
    ResumeCertification,
    ResumeExperience,
    ResumeProject,
    SkillCategory,
)
from app.services.profile_service import compute_profile_content_hash
from app.services.skill_evidence_index import (
    SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN,
    SKILL_EVIDENCE_INDEX_VERSION,
    SKILL_EVIDENCE_INVALID_PROJECT_LINK,
    SKILL_EVIDENCE_METADATA_LEAKAGE,
    SKILL_EVIDENCE_PROFILE_ONLY,
    SKILL_EVIDENCE_UNKNOWN_SKILL,
    SKILL_NOT_REGISTERED,
    UNMAPPED_PROJECT_EXCLUDED,
    build_skill_evidence_index,
)


REFERENCE_DATE = date(2026, 7, 19)


def base_profile(**updates) -> CandidateProfile:
    payload = {
        "name": "Venu Madhav Pendurthi",
        "title": "Senior Full Stack .NET Developer",
        "skills": [
            SkillCategory(category="Programming Languages", items=["C#", "Python"]),
            SkillCategory(category="Cloud", items=["Azure Data Factory", "Splunk"]),
        ],
        "experience": [
            ResumeExperience(
                experienceId="exp-infosys",
                company="Infosys",
                clientName="Molina Healthcare",
                role="Senior .NET Developer",
                startDate="2025-01",
                endDate="Present",
                isCurrentRole=True,
                technologies=["C#", "ASP.NET Core", "SQL Server"],
                responsibilities=[
                    "Built REST APIs with ASP.NET Core for provider portal workflows.",
                    "Reviewed SQL Server changes and code reviews before release.",
                ],
                achievements=["Improved API reliability across SQL Server workflows."],
                metrics=[ExperienceMetric(metricId="metric-1", label="SQL Server query reduction", value="30%")],
            ),
            ResumeExperience(
                experienceId="exp-tcs",
                company="Tata Consultancy Services",
                role=".NET Developer",
                startDate="2016-12",
                endDate="2021-10",
                technologies=["ASP.NET MVC"],
                bullets=["Maintained ASP.NET MVC applications and SQL Server stored procedures."],
            ),
        ],
        "projects": [],
        "certifications": [],
    }
    payload.update(updates)
    return CandidateProfile(**payload)


def summary(index, canonical_name: str):
    return next(item for item in index.summaries if item.canonical_name == canonical_name)


def records(index, canonical_name: str):
    return [item for item in index.records if item.canonical_name == canonical_name]


def test_builds_deterministic_skill_evidence_records_from_profile_sources():
    index = build_skill_evidence_index(base_profile(), reference_date=REFERENCE_DATE)

    assert index.index_version == SKILL_EVIDENCE_INDEX_VERSION
    assert index.validation_status == "valid_with_warnings"
    assert [item.skill_evidence_id for item in index.records] == sorted(item.skill_evidence_id for item in index.records)

    csharp = summary(index, "C#")
    assert csharp.allowed_for_skill_selection is True
    assert csharp.strongest_evidence == "strong"
    assert csharp.most_recent_evidence == "current"
    assert "exp-infosys" in csharp.experience_ids
    assert csharp.profile_only is False

    mvc = summary(index, "ASP.NET MVC")
    assert mvc.strongest_evidence == "medium"
    assert mvc.most_recent_evidence == "older"
    assert "exp-tcs" in mvc.experience_ids


def test_profile_only_skill_is_weak_and_warned_until_supported_elsewhere():
    index = build_skill_evidence_index(
        base_profile(skills=[SkillCategory(category="AI", items=["LangChain"])]),
        reference_date=REFERENCE_DATE,
    )

    langchain = summary(index, "LangChain")
    assert langchain.profile_only is True
    assert langchain.strongest_evidence == "weak"
    assert langchain.allowed_for_skill_selection is True
    assert SKILL_EVIDENCE_PROFILE_ONLY in langchain.warnings


def test_unknown_skill_is_preserved_but_not_allowed_for_selection():
    index = build_skill_evidence_index(base_profile(), reference_date=REFERENCE_DATE)

    unknown = next(item for item in index.unknown_skills if item.normalized_value == "splunk")
    assert unknown.canonical_name is None
    assert unknown.allowed_for_skill_selection is False
    assert SKILL_NOT_REGISTERED in unknown.warnings
    assert SKILL_EVIDENCE_UNKNOWN_SKILL in unknown.warnings


def test_specific_cloud_data_service_does_not_create_parent_azure_record():
    profile = base_profile(
        skills=[SkillCategory(category="Data", items=["Azure Data Factory"])],
        experience=[],
        certifications=[],
    )
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    assert summary(index, "Azure Data Factory").canonical_name == "Azure Data Factory"
    assert "Azure" not in {item.canonical_name for item in index.summaries}


def test_certification_scope_supports_only_recognized_broad_skill():
    profile = base_profile(
        skills=[],
        experience=[],
        certifications=[
            ResumeCertification(certificationId="cert-azure", name="Microsoft Azure Fundamentals AZ-900", issuer="Microsoft"),
            ResumeCertification(certificationId="cert-random", name="Internal Excellence Badge", issuer="Employer"),
        ],
    )
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    azure = summary(index, "Azure")
    assert azure.allowed_for_skill_selection is True
    assert azure.strongest_evidence == "medium"
    assert "certification" in azure.source_types
    assert "Azure Data Factory" not in {item.canonical_name for item in index.summaries}
    assert SKILL_EVIDENCE_CERTIFICATION_SCOPE_UNKNOWN in index.warnings


def test_project_linked_to_experience_preserves_linked_ids_for_later_planners():
    profile = base_profile(
        projects=[
            ResumeProject(
                projectId="project-provider",
                name="Provider Portal",
                bullets=["Built React pages backed by REST APIs."],
                technologies=["React", "REST APIs"],
                linkedExperienceIds=["exp-infosys"],
            )
        ]
    )
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    react_records = records(index, "React")
    assert react_records
    assert all(item.project_id == "project-provider" for item in react_records)
    assert all(item.linked_experience_ids == ["exp-infosys"] for item in react_records)
    assert "project-provider" in summary(index, "React").project_ids


def test_project_linked_to_one_experience_does_not_claim_another_experience():
    profile = base_profile(
        projects=[
            ResumeProject(
                projectId="project-provider",
                name="Provider Portal",
                bullets=["Built React pages backed by REST APIs."],
                technologies=["React"],
                linkedExperienceIds=["exp-infosys"],
            )
        ]
    )
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    assert "exp-tcs" not in {linked_id for item in records(index, "React") for linked_id in item.linked_experience_ids}


def test_unmapped_project_remains_project_evidence_and_warns_it_is_excluded_from_employment():
    profile = base_profile(
        projects=[
            ResumeProject(
                projectId="project-ai",
                name="AI Assistant",
                bullets=["Built a LangChain RAG workflow with Python."],
                technologies=["LangChain", "Python"],
                linkedExperienceIds=[],
            )
        ]
    )
    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    langchain = summary(index, "LangChain")
    assert langchain.allowed_for_skill_selection is True
    assert langchain.project_ids == ["project-ai"]
    assert not langchain.experience_ids
    assert UNMAPPED_PROJECT_EXCLUDED in index.warnings


def test_invalid_project_link_is_reported_for_backward_compatible_raw_payloads():
    profile = CandidateProfile.model_construct(
        name="Venu",
        first_name="Venu",
        last_name="",
        title="Developer",
        contact=base_profile().contact,
        summary="",
        skills=[],
        experience=[ResumeExperience(experienceId="exp-1", company="Infosys", role="Developer")],
        projects=[
            ResumeProject.model_construct(
                project_id="project-1",
                name="Old Project",
                org="",
                link="",
                bullets=[],
                technologies=["React"],
                linked_experience_ids=["missing-exp"],
            )
        ],
        education=[],
        certifications=[],
    )

    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    assert SKILL_EVIDENCE_INVALID_PROJECT_LINK in index.warnings
    assert index.validation_status == "invalid"


def test_metadata_leakage_is_warned_and_not_allowed_for_selection():
    index = build_skill_evidence_index(
        base_profile(skills=[SkillCategory(category="Companies", items=["Infosys"])]),
        reference_date=REFERENCE_DATE,
    )

    leaked = next(item for item in index.records if item.original_value == "Infosys")
    assert SKILL_EVIDENCE_METADATA_LEAKAGE in leaked.warnings
    assert leaked.allowed_for_skill_selection is False
    assert index.validation_status == "invalid"


def test_linked_experience_ids_change_profile_hash_and_invalidate_packages():
    unmapped = base_profile(
        projects=[ResumeProject(projectId="project-1", name="Portal", technologies=["React"], linkedExperienceIds=[])]
    )
    linked = base_profile(
        projects=[ResumeProject(projectId="project-1", name="Portal", technologies=["React"], linkedExperienceIds=["exp-infosys"])]
    )

    assert compute_profile_content_hash(unmapped) != compute_profile_content_hash(linked)


def test_existing_project_json_without_links_defaults_to_empty_list():
    project = ResumeProject.model_validate({"projectId": "project-1", "name": "Legacy", "technologies": ["React"]})
    profile = base_profile(projects=[project])

    index = build_skill_evidence_index(profile, reference_date=REFERENCE_DATE)

    assert project.linked_experience_ids == []
    assert records(index, "React")[0].linked_experience_ids == []


def test_blank_project_links_are_rejected_by_profile_schema():
    with pytest.raises(ValueError, match="blank IDs"):
        CandidateProfile(
            name="Venu",
            experience=[ResumeExperience(experienceId="exp-1", company="Infosys", role="Developer")],
            projects=[ResumeProject(projectId="project-1", name="Portfolio", linkedExperienceIds=[""])],
        )


def test_duplicate_project_links_are_rejected_by_profile_schema():
    with pytest.raises(ValueError, match="duplicate IDs"):
        CandidateProfile(
            name="Venu",
            experience=[ResumeExperience(experienceId="exp-1", company="Infosys", role="Developer")],
            projects=[ResumeProject(projectId="project-1", name="Portfolio", linkedExperienceIds=["exp-1", "exp-1"])],
        )
