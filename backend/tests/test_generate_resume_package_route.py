from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.api.routes import resumes as resumes_route
from app.core.config import settings
from app.main import app
from app.schemas.resume import (
    CandidateProfile,
    JobAnalysisResponse,
    JobKeywordAnalysisItem,
    ExperienceRoleIntelligence,
    ResumeContact,
    ResumeExperience,
    SkillCategory,
    StructuredResumeRecord,
    ResumeIntelligencePackageSchema,
)
from app.services.profile_matching import match_job_to_profile as actual_match_job_to_profile
from app.services.profile_service import compute_profile_content_hash, ensure_profile_record_ids
from app.services.resume_intelligence_store import STALE_PACKAGE_MESSAGE, ResumeIntelligencePackageStaleError
from app.services.summary_generation_service import SUMMARY_PROMPT_VERSION
from app.services.summary_intelligence import summary_model_configuration_hash
from app.services.summary_planner import SummaryBuildResult, SummaryGenerationResult, SummaryValidationResult
from app.services.experience_planner import EXPERIENCE_PLANNER_VERSION
from app.services.experience_prompt_builder import EXPERIENCE_PROMPT_VERSION
from app.services.experience_generation_service import experience_model_configuration_hash


USER_ID = UUID("11111111-1111-1111-1111-111111111111")
PROFILE_ID = "22222222-2222-2222-2222-222222222222"
PACKAGE_ID = "33333333-3333-3333-3333-333333333333"
PERSISTED_RESUME_ID = "44444444-4444-4444-4444-444444444444"
JOB_DESCRIPTION = "Need C#, .NET, REST APIs, and SQL Server."
STORED_SUMMARY = "Senior .NET Developer with experience building enterprise applications using C#, .NET, REST APIs, and SQL Server. Focused on maintainable API delivery, database-backed features, and clear technical execution for business stakeholders."


def keyword(value: str) -> JobKeywordAnalysisItem:
    return JobKeywordAnalysisItem(
        id=f"req-{value.casefold().replace(' ', '-').replace('#', 'sharp')}",
        value=value,
        normalizedValue=value,
        category="Technical",
        sourceType="explicit",
        confidence="high",
        priority="high",
        priorityScore=90,
        directFromJD=True,
        evidenceText=f"JD requires {value}",
        sourceSentence=f"JD requires {value}",
        occurrenceCount=1,
    )


def job_analysis() -> JobAnalysisResponse:
    return JobAnalysisResponse(
        roleInformation={"title": "Software Engineer IV", "seniority": "Senior"},
        keywords=[keyword("C#"), keyword(".NET"), keyword("REST API"), keyword("MS SQL Server")],
        analysisHash="package-route-analysis",
    )


def candidate_profile() -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Venu Madhav Pendurthi",
            firstName="Venu",
            lastName="Madhav Pendurthi",
            title="Senior .NET Developer",
            contact=ResumeContact(email="venu@example.com", phone="+12014436937", location="Hartford, CT"),
            skills=[
                SkillCategory(
                    category="Programming Languages",
                    items=["C#"],
                ),
                SkillCategory(
                    category="Backend Development",
                    items=[".NET", "REST API"],
                ),
                SkillCategory(
                    category="Databases",
                    items=["MS SQL Server"],
                ),
            ],
            experience=[
                ResumeExperience(
                    experienceId="exp-current",
                    company="Infosys",
                    role="Senior .NET Developer",
                    location="Hartford, CT",
                    startDate="2025-01",
                    endDate="Present",
                    rawNotes="Built C# and .NET REST API enhancements backed by SQL Server for enterprise delivery.",
                    technologies=["C#", ".NET", "REST API", "MS SQL Server"],
                )
            ],
        )
    )


def profile_record(profile: CandidateProfile):
    return SimpleNamespace(
        profile_id=PROFILE_ID,
        profile_version=7,
        content_hash=compute_profile_content_hash(profile),
        updated_at="2026-07-18T00:00:00+00:00",
        profile_data=profile,
    )


def generation_payload(*, package_id: str = PACKAGE_ID) -> dict:
    return {
        "profileId": PROFILE_ID,
        "profileVersion": 7,
        "resumeIntelligencePackageId": package_id,
        "candidate": {
            "firstName": "Venu",
            "lastName": "Madhav Pendurthi",
            "currentTitle": "Senior .NET Developer",
            "email": "venu@example.com",
            "phone": "+12014436937",
            "location": {
                "city": "Hartford",
                "state": "CT",
                "country": "United States",
                "displayValue": "Hartford, CT",
            },
        },
        "skills": [
            {"categoryId": "programming-languages", "categoryName": "Programming Languages", "order": 0, "items": ["C#"]},
            {"categoryId": "backend-development", "categoryName": "Backend Development", "order": 1, "items": [".NET", "REST API"]},
            {"categoryId": "databases", "categoryName": "Databases", "order": 2, "items": ["MS SQL Server"]},
        ],
        "workExperience": [
            {
                "experienceId": "exp-current",
                "companyName": "Infosys",
                "clientName": None,
                "roleTitle": "Senior .NET Developer",
                "location": {
                    "city": "Hartford",
                    "state": "CT",
                    "country": "United States",
                    "displayValue": "Hartford, CT",
                },
                "startDate": {"month": 0, "year": 0, "displayValue": "2025-01"},
                "endDate": None,
                "isCurrentRole": True,
            }
        ],
        "job": {
            "description": JOB_DESCRIPTION,
            "targetRole": "Software Engineer IV",
            "targetCompany": "Velera",
            "level": "Senior",
        },
        "resumePreferences": {
            "templateId": "classic-ats",
            "headerVisibility": {
                "fullName": True,
                "currentTitle": True,
                "email": True,
                "phone": True,
                "location": True,
                "linkedinUrl": False,
                "githubUrl": False,
                "portfolioUrl": False,
            },
            "sectionVisibility": {
                "summary": True,
                "skills": True,
                "experience": True,
                "projects": True,
                "education": True,
                "certifications": True,
            },
        },
    }


def match_payload() -> dict:
    return {
        "profileId": PROFILE_ID,
        "jobAnalysis": job_analysis().model_dump(mode="json", by_alias=True),
        "jobDescription": JOB_DESCRIPTION,
        "targetRole": "Software Engineer IV",
        "targetCompany": "Velera",
        "level": "Senior",
    }


def persisted_record(structured, stored_profile_match_json: dict) -> StructuredResumeRecord:
    persisted = structured.model_copy(update={"resume_id": PERSISTED_RESUME_ID, "user_id": str(USER_ID)})
    return StructuredResumeRecord(
        resumeId=PERSISTED_RESUME_ID,
        userId=str(USER_ID),
        profileId=PROFILE_ID,
        profileVersion=persisted.profile_version,
        profileContentHash=persisted.profile_content_hash,
        resumeName=persisted.resume_name,
        targetJobTitle=persisted.target_job_title,
        targetCompany=persisted.target_company,
        jobDescription=persisted.job_description,
        jobAnalysisJson={},
        profileMatchJson=stored_profile_match_json,
        resumeJson=persisted,
        templateId=persisted.template_id,
        matchScore=persisted.match_score,
        generationAlgorithmVersion=persisted.generation_algorithm_version,
        status=persisted.status,
        versionNumber=persisted.version_number,
        parentResumeId="",
        createdAt=persisted.created_at,
        updatedAt=persisted.updated_at,
    )


def summary_intelligence_json(record) -> dict:
    return {
        "summary": STORED_SUMMARY,
        "selectedTechnologies": ["C#", ".NET", "REST APIs", "SQL Server"],
        "selectedCapabilities": ["API delivery", "database-backed features"],
        "usedEvidenceIds": ["skill-csharp"],
        "excludedJdTerms": [],
        "riskFlags": [],
        "validationStatus": "valid",
        "validationWarnings": [],
        "generationMode": "openai",
        "model": "gpt-5.5",
        "profileId": PROFILE_ID,
        "profileVersion": record.profile_version,
        "profileHash": record.content_hash,
        "jobDescriptionHash": "8c11f784004b74c2ff0a410fe17a187e07242ca1e0c035553250461fba832f0b",
        "targetRole": "Software Engineer IV",
        "targetCompany": "Velera",
        "level": "Senior",
        "promptVersion": SUMMARY_PROMPT_VERSION,
        "modelConfigurationHash": summary_model_configuration_hash("gpt-5.5"),
        "createdAt": "2026-07-18T00:00:00+00:00",
    }


def experience_intelligence_json() -> dict:
    return {
        "plannerVersion": EXPERIENCE_PLANNER_VERSION,
        "roleFamily": "Backend .NET Development",
        "experiencePromptInputs": [
            {
                "experienceId": "exp-current",
                "roleContext": {
                    "roleTitle": "Senior .NET Developer",
                    "companyName": "Infosys",
                    "clientName": None,
                    "isCurrentRole": True,
                    "roleFamily": "Backend .NET Development",
                },
                "targetContext": {"targetRole": "Software Engineer IV", "targetCompany": "Velera", "level": "Senior", "targetThemes": ["API delivery"]},
                "approvedEvidence": [
                    {
                        "evidenceId": "experience-exp-current-raw-notes",
                        "evidenceType": "responsibility",
                        "text": "Built C# and .NET REST API enhancements backed by SQL Server for enterprise delivery.",
                        "sourceRecordId": "experience-exp-current",
                        "projectId": None,
                    }
                ],
                "approvedTechnologies": [{"name": "C#", "evidenceIds": ["experience-exp-current-raw-notes"]}],
                "approvedCapabilities": [{"name": "API delivery", "evidenceIds": ["experience-exp-current-raw-notes"], "supportedRequirementIds": ["req-csharp"]}],
                "approvedMetrics": [],
                "linkedProjects": [],
                "bulletThemes": ["API delivery"],
                "supportedRequirementIds": ["req-csharp"],
                "excludedTerms": [],
                "writingRules": {
                    "bulletCount": 1,
                    "maximumWordsPerBullet": 30,
                    "useOnlyApprovedEvidence": True,
                    "doNotInventMetrics": True,
                    "doNotInventTechnologies": True,
                    "doNotInventLeadership": True,
                    "doNotInventArchitectureOwnership": True,
                    "doNotUseUnsupportedJdTerms": True,
                    "startWithActionVerb": True,
                    "avoidFirstPerson": True,
                    "avoidDuplicateOpenings": True,
                    "avoidGenericFiller": True,
                },
                "plannerVersion": EXPERIENCE_PLANNER_VERSION,
                "promptVersion": EXPERIENCE_PROMPT_VERSION,
                "validationResult": {"isValid": True, "codes": [], "warnings": []},
            }
        ],
        "roleIntelligence": [
            {
                "experienceId": "exp-current",
                "bullets": [
                    {
                        "bulletId": "bullet-stored-api",
                        "order": 1,
                        "generatedText": "Built C# REST API enhancements with SQL Server for enterprise application delivery.",
                        "currentText": "Built C# REST API enhancements with SQL Server for enterprise application delivery.",
                        "userEdited": False,
                        "supportingEvidenceIds": ["experience-exp-current-raw-notes"],
                        "supportedRequirementIds": ["req-csharp"],
                        "validationStatus": "valid",
                        "warnings": [],
                        "generationMethod": "openai",
                        "model": settings.openai_experience_model,
                        "promptVersion": settings.experience_writer_prompt_version,
                    }
                ],
                "generationMode": "openai",
                "model": settings.openai_experience_model,
                "promptVersion": settings.experience_writer_prompt_version,
                "validationStatus": "valid",
                "warnings": [],
                "modelConfigurationHash": experience_model_configuration_hash(settings.openai_experience_model),
            }
        ],
        "writerPromptVersion": settings.experience_writer_prompt_version,
        "writerModel": settings.openai_experience_model,
        "modelConfigurationHash": experience_model_configuration_hash(settings.openai_experience_model),
        "overallValidationStatus": "valid",
        "validationStatus": "valid",
        "warnings": [],
        "createdAt": "2026-07-18T00:00:00+00:00",
    }


async def fake_session():
    yield object()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def test_generate_route_reuses_valid_resume_intelligence_package(monkeypatch) -> None:
    profile = candidate_profile()
    record = profile_record(profile)
    stored_analysis = job_analysis()
    stored_match = actual_match_job_to_profile(
        stored_analysis,
        profile,
        PROFILE_ID,
        record.updated_at,
        record.profile_version,
        record.content_hash,
    ).match_summary
    stored_analysis_json = stored_analysis.model_dump(mode="json", by_alias=True)
    stored_match_json = stored_match.model_dump(mode="json", by_alias=True)
    captured: dict[str, object] = {}

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return record

    async def fake_validate_package(_session, user_id, package_id, profile_record_arg, payload):
        assert user_id == USER_ID
        assert package_id == PACKAGE_ID
        assert profile_record_arg is record
        assert payload.job_description == JOB_DESCRIPTION
        assert payload.target_role == "Software Engineer IV"
        assert payload.target_company == "Velera"
        assert payload.level == "Senior"
        return SimpleNamespace(
            id=UUID(PACKAGE_ID),
            profile_id=UUID(PROFILE_ID),
            profile_version=record.profile_version,
            profile_content_hash=record.content_hash,
            job_intelligence_json=stored_analysis_json,
            profile_match_json=stored_match_json,
            summary_intelligence_json=summary_intelligence_json(record),
            experience_intelligence_json=experience_intelligence_json(),
        )

    async def fake_create_generated_resume(_session, user_id, structured, job_analysis_json, profile_match_json):
        assert user_id == USER_ID
        captured["structured"] = structured
        captured["job_analysis_json"] = job_analysis_json
        captured["profile_match_json"] = profile_match_json
        return persisted_record(structured, stored_match_json)

    # Replace the imported route symbol with a callable that fails loudly if package reuse regresses.
    match_spy = Mock(side_effect=AssertionError("match_job_to_profile must not be called for a valid package generation path."))

    monkeypatch.setattr(resumes_route, "match_job_to_profile", match_spy)
    monkeypatch.setattr(resumes_route, "build_summary_planner", Mock(side_effect=AssertionError("Summary Planner must not be rebuilt for a valid package generation path.")))
    monkeypatch.setattr(resumes_route, "generate_summary", Mock(side_effect=AssertionError("Summary model must not be called during valid package generation.")))
    monkeypatch.setattr(resumes_route, "generate_experience_intelligence", Mock(side_effect=AssertionError("Experience model must not be called during valid package generation.")))
    monkeypatch.setattr(resumes_route, "build_experience_intelligence", Mock(side_effect=AssertionError("Experience Planner must not be rebuilt during valid package generation.")))
    monkeypatch.setattr(resumes_route, "build_experience_prompts", Mock(side_effect=AssertionError("Experience Prompt Builder must not run during valid package generation.")))
    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "validate_resume_intelligence_package", fake_validate_package)
    monkeypatch.setattr(resumes_route, "create_generated_resume", fake_create_generated_resume)
    app.dependency_overrides[resumes_route.db_session] = fake_session
    app.dependency_overrides[resumes_route.optional_current_user_id] = lambda: USER_ID

    response = TestClient(app).post("/api/resumes/generate", json=generation_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resumeId"] == PERSISTED_RESUME_ID
    assert body["persistedResumeId"] == PERSISTED_RESUME_ID
    assert captured["job_analysis_json"] == stored_analysis_json
    assert captured["profile_match_json"] == stored_match_json
    assert captured["structured"].match_score == stored_match.overall_match_score
    assert [section for section in captured["structured"].sections if section.type == "summary"][0].content == STORED_SUMMARY
    experience_section = [section for section in captured["structured"].sections if section.type == "experience"][0]
    assert experience_section.content[0]["bullets"][0]["currentText"] == "Built C# REST API enhancements with SQL Server for enterprise application delivery."
    assert experience_section.content[0]["bullets"][0]["generationMethod"] == "openai"
    match_spy.assert_not_called()


def test_match_profile_route_creates_package_with_summary_intelligence(monkeypatch) -> None:
    profile = candidate_profile()
    record = profile_record(profile)
    captured: dict[str, object] = {}

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return record

    async def fake_generate_summary(**kwargs):
        planner = kwargs["planner"]
        captured["summary_planner"] = planner
        return SummaryBuildResult(
            planner=planner,
            generation=SummaryGenerationResult(
                summary=STORED_SUMMARY,
                usedEvidenceIds=["skill-csharp"],
                usedSignals=["C#", ".NET"],
                excludedSignals=[],
                riskFlags=[],
                generationMethod="openai",
            ),
            validation=SummaryValidationResult(isValid=True),
        )

    async def fake_generate_experience_intelligence(experience_intelligence):
        return experience_intelligence.model_copy(
            update={
                "role_intelligence": [
                    ExperienceRoleIntelligence.model_validate(experience_intelligence_json()["roleIntelligence"][0])
                ],
                "writer_prompt_version": settings.experience_writer_prompt_version,
                "writer_model": settings.openai_experience_model,
                "overall_validation_status": "valid",
                "validation_status": "valid",
            }
        )

    async def fake_create_package(_session, user_id, *, profile_record, payload, job_analysis, profile_match, summary_intelligence, experience_intelligence=None):
        assert user_id == USER_ID
        assert profile_record is record
        assert payload.job_description == JOB_DESCRIPTION
        assert summary_intelligence.summary == STORED_SUMMARY
        assert summary_intelligence.validation_status == "valid"
        assert summary_intelligence.generation_mode == "openai"
        assert experience_intelligence is not None
        assert experience_intelligence.roles
        assert experience_intelligence.roles[0].experience_id == "exp-current"
        assert experience_intelligence.experience_prompt_inputs
        assert experience_intelligence.experience_prompt_inputs[0].experience_id == "exp-current"
        assert experience_intelligence.experience_prompt_inputs[0].prompt_version == "experience-prompt-v1"
        assert experience_intelligence.role_intelligence
        assert experience_intelligence.role_intelligence[0].bullets
        captured["summary_intelligence"] = summary_intelligence
        captured["experience_intelligence"] = experience_intelligence
        return ResumeIntelligencePackageSchema(
            packageId=PACKAGE_ID,
            profileId=PROFILE_ID,
            profileVersion=record.profile_version,
            jobDescriptionHash=summary_intelligence.job_description_hash,
            targetRole="Software Engineer IV",
            targetCompany="Velera",
            level="Senior",
            jobIntelligence=job_analysis.model_dump(mode="json", by_alias=True),
            normalizedRequirements=job_analysis.normalized_requirements.model_dump(mode="json", by_alias=True),
            profileMatch=profile_match.match_summary.model_dump(mode="json", by_alias=True),
            summaryIntelligence=summary_intelligence,
            experienceIntelligence=experience_intelligence,
            validationStatus="valid",
            validationWarnings=[],
            createdAt="2026-07-18T00:00:00+00:00",
            updatedAt="2026-07-18T00:00:00+00:00",
        )

    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "generate_summary", fake_generate_summary)
    monkeypatch.setattr(resumes_route, "generate_experience_intelligence", fake_generate_experience_intelligence)
    monkeypatch.setattr(resumes_route, "create_resume_intelligence_package", fake_create_package)
    app.dependency_overrides[resumes_route.db_session] = fake_session
    app.dependency_overrides[resumes_route.optional_current_user_id] = lambda: USER_ID

    response = TestClient(app).post("/api/resumes/match-profile", json=match_payload())

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["packageId"] == PACKAGE_ID
    assert body["summaryIntelligence"]["summary"] == STORED_SUMMARY
    assert body["summaryIntelligence"]["generationMode"] == "openai"
    assert body["experienceIntelligence"]["plannerVersion"] == captured["experience_intelligence"].planner_version
    assert body["experienceIntelligence"]["roles"][0]["experienceId"] == "exp-current"
    assert body["experienceIntelligence"]["experiencePromptInputs"][0]["promptVersion"] == "experience-prompt-v1"
    assert captured["summary_intelligence"].model == "gpt-5.5"
    assert captured["summary_planner"].target_emphasis.top_supported_technologies


def test_generate_route_rejects_stale_package_without_rematching(monkeypatch) -> None:
    profile = candidate_profile()
    record = profile_record(profile)

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return record

    async def fake_validate_package(*_args, **_kwargs):
        raise ResumeIntelligencePackageStaleError(STALE_PACKAGE_MESSAGE)

    match_spy = Mock(side_effect=AssertionError("match_job_to_profile must not be called for a stale package."))

    async def fail_persistence(*_args, **_kwargs):
        raise AssertionError("stale package generation must not persist a resume.")

    monkeypatch.setattr(resumes_route, "match_job_to_profile", match_spy)
    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "validate_resume_intelligence_package", fake_validate_package)
    monkeypatch.setattr(resumes_route, "create_generated_resume", fail_persistence)
    app.dependency_overrides[resumes_route.db_session] = fake_session
    app.dependency_overrides[resumes_route.optional_current_user_id] = lambda: USER_ID

    response = TestClient(app).post("/api/resumes/generate", json=generation_payload(package_id=PACKAGE_ID))

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == STALE_PACKAGE_MESSAGE
    match_spy.assert_not_called()


def test_generate_route_rejects_package_missing_summary_without_regeneration(monkeypatch) -> None:
    profile = candidate_profile()
    record = profile_record(profile)
    stored_analysis = job_analysis()
    stored_match = actual_match_job_to_profile(
        stored_analysis,
        profile,
        PROFILE_ID,
        record.updated_at,
        record.profile_version,
        record.content_hash,
    ).match_summary

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return record

    async def fake_validate_package(_session, user_id, package_id, profile_record_arg, payload):
        assert user_id == USER_ID
        assert package_id == PACKAGE_ID
        assert profile_record_arg is record
        return SimpleNamespace(
            id=UUID(PACKAGE_ID),
            profile_id=UUID(PROFILE_ID),
            profile_version=record.profile_version,
            profile_content_hash=record.content_hash,
            job_intelligence_json=stored_analysis.model_dump(mode="json", by_alias=True),
            profile_match_json=stored_match.model_dump(mode="json", by_alias=True),
            summary_intelligence_json=None,
        )

    async def fail_persistence(*_args, **_kwargs):
        raise AssertionError("missing summary intelligence must not persist a resume.")

    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "validate_resume_intelligence_package", fake_validate_package)
    monkeypatch.setattr(resumes_route, "generate_summary", Mock(side_effect=AssertionError("Generate must not regenerate a missing package summary.")))
    monkeypatch.setattr(resumes_route, "build_summary_planner", Mock(side_effect=AssertionError("Generate must not rebuild a planner for missing package summary.")))
    monkeypatch.setattr(resumes_route, "create_generated_resume", fail_persistence)
    app.dependency_overrides[resumes_route.db_session] = fake_session
    app.dependency_overrides[resumes_route.optional_current_user_id] = lambda: USER_ID

    response = TestClient(app).post("/api/resumes/generate", json=generation_payload())

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Summary intelligence is missing or stale. Run Analyze & Match again."


def test_generate_route_rejects_changed_summary_model_config_without_regeneration(monkeypatch) -> None:
    profile = candidate_profile()
    record = profile_record(profile)
    stored_analysis = job_analysis()
    stored_match = actual_match_job_to_profile(
        stored_analysis,
        profile,
        PROFILE_ID,
        record.updated_at,
        record.profile_version,
        record.content_hash,
    ).match_summary
    stale_summary = summary_intelligence_json(record)
    stale_summary["model"] = "old-summary-model"
    stale_summary["modelConfigurationHash"] = summary_model_configuration_hash("old-summary-model")

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return record

    async def fake_validate_package(_session, user_id, package_id, profile_record_arg, payload):
        assert user_id == USER_ID
        assert package_id == PACKAGE_ID
        assert profile_record_arg is record
        return SimpleNamespace(
            id=UUID(PACKAGE_ID),
            profile_id=UUID(PROFILE_ID),
            profile_version=record.profile_version,
            profile_content_hash=record.content_hash,
            job_intelligence_json=stored_analysis.model_dump(mode="json", by_alias=True),
            profile_match_json=stored_match.model_dump(mode="json", by_alias=True),
            summary_intelligence_json=stale_summary,
        )

    async def fail_persistence(*_args, **_kwargs):
        raise AssertionError("stale summary model configuration must not persist a resume.")

    monkeypatch.setattr(settings, "openai_summary_model", "new-summary-model")
    monkeypatch.setattr(resumes_route.profile_service, "get_profile", fake_get_profile)
    monkeypatch.setattr(resumes_route, "validate_resume_intelligence_package", fake_validate_package)
    monkeypatch.setattr(resumes_route, "generate_summary", Mock(side_effect=AssertionError("Generate must not regenerate stale summary intelligence.")))
    monkeypatch.setattr(resumes_route, "build_summary_planner", Mock(side_effect=AssertionError("Generate must not rebuild a planner for stale summary intelligence.")))
    monkeypatch.setattr(resumes_route, "create_generated_resume", fail_persistence)
    app.dependency_overrides[resumes_route.db_session] = fake_session
    app.dependency_overrides[resumes_route.optional_current_user_id] = lambda: USER_ID

    response = TestClient(app).post("/api/resumes/generate", json=generation_payload())

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == "Summary intelligence is missing or stale. Run Analyze & Match again."
