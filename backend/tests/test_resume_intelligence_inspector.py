from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

from fastapi.testclient import TestClient

from app.api.routes import resume_intelligence as inspector_route
from app.services import llm as llm_service
from app.services import profile_matching as profile_matching_service
from app.services import resume_intelligence_store
from app.services import resume_store
from app.services import resume_generation_pipeline
from app.services import summary_intelligence as summary_intelligence_service
from app.services import experience_planner as experience_planner_service
from app.services import experience_prompt_builder as experience_prompt_builder_service
from app.services import experience_generation_service
from app.services import skill_evidence_index as skill_evidence_index_service
from app.services import skills_planner as skills_planner_service
from app.services import skills_rendering as skills_rendering_service
from app.main import app
from app.services.profile_matching import match_job_to_profile as actual_match_job_to_profile
from app.services.profile_service import compute_profile_content_hash
from app.services.resume_intelligence_inspector import inspect_resume_intelligence_package
from app.services.resume_intelligence_store import ResumeIntelligencePackageNotFoundError, ResumeIntelligencePackageOwnershipError, job_description_hash
from tests.test_generate_resume_package_route import (
    JOB_DESCRIPTION,
    PACKAGE_ID,
    PROFILE_ID,
    USER_ID,
    candidate_profile,
    experience_intelligence_json,
    job_analysis,
    profile_record,
    skills_intelligence_json,
    summary_intelligence_json,
)


def package_record(*, validation_status: str = "valid", legacy: bool = False):
    profile = candidate_profile()
    record = profile_record(profile)
    analysis = job_analysis()
    match = actual_match_job_to_profile(
        analysis,
        profile,
        PROFILE_ID,
        record.updated_at,
        record.profile_version,
        record.content_hash,
    ).match_summary
    summary = summary_intelligence_json(record)
    summary["usedEvidenceIds"] = ["experience-exp-current-raw-notes"]
    summary["supportedRequirementIds"] = ["req-csharp"]
    experience = experience_intelligence_json()
    skills = skills_intelligence_json()
    skills["categories"][0]["skills"][0]["supportingEvidenceIds"] = ["experience-exp-current-raw-notes"]
    skills["excludedSkills"] = [
        {
            "canonicalName": "Java",
            "originalRequirementValue": "Java",
            "requirementIds": ["req-java"],
            "exclusionCode": "NO_CANDIDATE_EVIDENCE",
            "reason": "Java is present in the job requirements, but no safe candidate skill evidence supports it.",
        }
    ]
    normalized = analysis.normalized_requirements.model_dump(mode="json", by_alias=True)
    normalized["technicalRequirements"].append(
        {
            "requirementId": "req-java",
            "canonicalTerm": "Java",
            "originalTerms": ["Java"],
            "category": "Technical",
            "requirementLevel": "required",
            "priority": "high",
            "explicit": True,
            "confidence": 0.9,
            "evidenceText": "JD requires Java",
            "sourceSentence": "JD requires Java",
            "reason": "",
        }
    )
    return SimpleNamespace(
        id=UUID(PACKAGE_ID),
        user_id=USER_ID,
        profile_id=UUID(PROFILE_ID),
        profile_version=record.profile_version,
        profile_content_hash=record.content_hash,
        job_description_hash=job_description_hash(JOB_DESCRIPTION),
        target_role="Software Engineer IV",
        target_company="Velera",
        level="Senior",
        job_description=JOB_DESCRIPTION,
        job_intelligence_json=analysis.model_dump(mode="json", by_alias=True),
        normalized_requirements_json=normalized,
        profile_match_json=match.model_dump(mode="json", by_alias=True),
        summary_intelligence_json=None if legacy else summary,
        experience_intelligence_json=None if legacy else experience,
        skills_intelligence_json=None if legacy else skills,
        validation_status=validation_status,
        validation_warnings=["profile hash changed"] if validation_status == "stale" else [],
        created_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
        updated_at=datetime(2026, 7, 18, tzinfo=timezone.utc),
    )


async def fake_session():
    yield object()


def auth_override():
    return USER_ID


def profile_record_for_package(package):
    profile = candidate_profile()
    return SimpleNamespace(
        profile_id=str(package.profile_id),
        profile_version=package.profile_version,
        content_hash=compute_profile_content_hash(profile),
        updated_at="2026-07-18T00:00:00+00:00",
        profile_data=profile,
    )


def setup_route(monkeypatch, package):
    async def fake_get_package(_session, user_id, package_id):
        assert user_id == USER_ID
        assert package_id == PACKAGE_ID
        return package

    async def fake_get_profile(_session, user_id, profile_id):
        assert user_id == USER_ID
        assert profile_id == PROFILE_ID
        return profile_record_for_package(package)

    monkeypatch.setattr(inspector_route, "get_resume_intelligence_package", fake_get_package)
    monkeypatch.setattr(inspector_route.profile_service, "get_profile", fake_get_profile)
    app.dependency_overrides[inspector_route.db_session] = fake_session
    app.dependency_overrides[inspector_route.current_user_id] = auth_override


def teardown_route():
    app.dependency_overrides.clear()


def test_complete_package_inspection_resolves_summary_bullets_skills_and_coverage():
    package = package_record()

    inspection = inspect_resume_intelligence_package(package, profile_record_for_package(package))

    assert inspection.package_id == PACKAGE_ID
    assert inspection.status == "valid"
    assert inspection.summary.generated_text
    assert inspection.summary.supporting_evidence_ids == ["experience-exp-current-raw-notes"]
    assert inspection.summary.evidence_details[0].evidence_text.startswith("Built C#")
    assert inspection.experience_overview.role_count == 1
    assert inspection.experience_overview.bullet_count == 1
    bullet = inspection.experience_overview.roles[0].bullets[0]
    assert bullet.bullet_id == "bullet-stored-api"
    assert bullet.generation_method == "openai"
    assert bullet.evidence_details[0].evidence_id == "experience-exp-current-raw-notes"
    assert inspection.skills_overview.primary_skill_count == 1
    assert inspection.skills_overview.skills[0].score_breakdown["finalScore"] == 100
    assert inspection.skills_overview.excluded_skills[0].canonical_name == "Java"
    java_coverage = [item for item in inspection.requirement_coverage if item.requirement_id == "req-java"][0]
    assert not java_coverage.covered
    assert java_coverage.exclusion_reason.startswith("Java is present")
    assert inspection.metrics.covered_requirement_count >= 1


def test_stale_package_inspection_is_allowed_without_mutation():
    package = package_record(validation_status="stale")
    before = deepcopy(package.__dict__)

    inspection = inspect_resume_intelligence_package(package, profile_record_for_package(package))

    assert inspection.stale is True
    assert "profile hash changed" in inspection.stale_reasons
    assert package.__dict__ == before


def test_current_profile_mismatch_and_summary_version_mismatch_are_stale():
    package = package_record()
    package.summary_intelligence_json["promptVersion"] = "old-summary-prompt"
    current_profile = profile_record_for_package(package)
    current_profile.profile_version = package.profile_version + 1
    current_profile.content_hash = "different-profile-hash"

    inspection = inspect_resume_intelligence_package(package, current_profile)

    assert inspection.stale is True
    assert "profileVersion changed: stored=7 current=8" in inspection.stale_reasons
    assert "profile hash changed" in inspection.stale_reasons
    assert "summary prompt version changed" in inspection.stale_reasons
    assert "INSPECTOR_VERSION_METADATA_MISSING" in {warning.code for warning in inspection.warnings}


def test_legacy_package_degrades_with_missing_section_warnings():
    package = package_record(legacy=True)

    inspection = inspect_resume_intelligence_package(package, profile_record_for_package(package))

    warning_codes = {warning.code for warning in inspection.warnings}
    assert "experience intelligence missing" in inspection.stale_reasons
    assert "skills intelligence missing" in inspection.stale_reasons
    assert inspection.summary.generated_text == ""
    assert inspection.experience_overview.role_count == 0
    assert inspection.skills_overview.skill_count == 0
    assert "INSPECTOR_SUMMARY_INTELLIGENCE_MISSING" in warning_codes
    assert "INSPECTOR_EXPERIENCE_INTELLIGENCE_MISSING" in warning_codes
    assert "INSPECTOR_SKILLS_INTELLIGENCE_MISSING" in warning_codes


def test_missing_evidence_and_requirement_references_are_reported():
    package = package_record()
    package.experience_intelligence_json["roleIntelligence"][0]["bullets"][0]["supportingEvidenceIds"] = ["missing-evidence"]
    package.experience_intelligence_json["roleIntelligence"][0]["bullets"][0]["supportedRequirementIds"] = ["missing-requirement"]

    inspection = inspect_resume_intelligence_package(package, profile_record_for_package(package))

    bullet = inspection.experience_overview.roles[0].bullets[0]
    codes = {warning.code for warning in bullet.warnings}
    assert "INSPECTOR_INVALID_EVIDENCE_REFERENCE" in codes
    assert "INSPECTOR_INVALID_REQUIREMENT_REFERENCE" in codes
    assert bullet.evidence_details[0].warnings[0].code == "INSPECTOR_EVIDENCE_NOT_FOUND"


def test_inspection_has_no_contact_raw_jd_or_prompt_leakage():
    package = package_record()

    body = inspect_resume_intelligence_package(package, profile_record_for_package(package)).model_dump_json(by_alias=True)

    assert "venu@example.com" not in body
    assert "+12014436937" not in body
    assert JOB_DESCRIPTION not in body
    assert "system prompt" not in body.casefold()
    assert "user prompt" not in body.casefold()


def test_metadata_and_secret_like_evidence_are_redacted():
    package = package_record()
    sensitive_evidence = {
        "evidenceId": "experience-exp-current-location-sensitive",
        "evidenceType": "work_experience",
        "sourceRecordId": "experience-exp-current",
        "sourceLabel": "Location marker",
        "originalText": "123 Main Street Hartford CT sk-testsecret123456789",
        "strengthScore": 80,
    }
    package.profile_match_json["matchedRequirements"][0]["evidence"].append(sensitive_evidence)
    package.experience_intelligence_json["roleIntelligence"][0]["bullets"][0]["supportingEvidenceIds"] = [sensitive_evidence["evidenceId"]]

    body = inspect_resume_intelligence_package(package, profile_record_for_package(package)).model_dump_json(by_alias=True)

    assert "123 Main Street" not in body
    assert "sk-testsecret123456789" not in body
    assert "[metadata-redacted]" in body
    assert "INSPECTOR_METADATA_LEAKAGE" in body


def test_inspection_endpoint_owner_can_inspect_and_does_not_call_generation(monkeypatch):
    package = package_record()
    setup_route(monkeypatch, package)
    monkeypatch.setattr(inspector_route, "inspect_resume_intelligence_package", Mock(wraps=inspect_resume_intelligence_package))

    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    teardown_route()
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["packageId"] == PACKAGE_ID
    assert body["skillsOverview"]["skills"][0]["skillId"] == "skill-csharp"
    inspector_route.inspect_resume_intelligence_package.assert_called_once()


def test_inspection_endpoint_does_not_call_ai_planners_writers_or_generation(monkeypatch):
    package = package_record()
    setup_route(monkeypatch, package)
    forbidden = Mock(side_effect=AssertionError("Inspector must not call generation or intelligence builders."))
    monkeypatch.setattr(llm_service, "analyze_job_for_resume", forbidden)
    monkeypatch.setattr(summary_intelligence_service, "build_summary_intelligence", forbidden)
    monkeypatch.setattr(experience_planner_service, "build_experience_intelligence", forbidden)
    monkeypatch.setattr(experience_prompt_builder_service, "build_experience_prompts", forbidden)
    monkeypatch.setattr(experience_generation_service, "generate_experience_intelligence", forbidden)
    monkeypatch.setattr(skill_evidence_index_service, "build_skill_evidence_index", forbidden)
    monkeypatch.setattr(skills_planner_service, "build_skills_intelligence", forbidden)
    monkeypatch.setattr(skills_rendering_service, "render_skills_intelligence", forbidden)
    monkeypatch.setattr(resume_generation_pipeline, "assemble_structured_resume", forbidden)
    monkeypatch.setattr(profile_matching_service, "match_job_to_profile", forbidden)
    monkeypatch.setattr(resume_intelligence_store, "create_resume_intelligence_package", forbidden)
    monkeypatch.setattr(resume_intelligence_store, "validate_resume_intelligence_package", forbidden)
    monkeypatch.setattr(resume_store, "create_generated_resume", forbidden)
    monkeypatch.setattr(resume_store, "update_resume", forbidden)
    monkeypatch.setattr(resume_store, "delete_resume", forbidden)

    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    teardown_route()
    assert response.status_code == 200, response.text
    forbidden.assert_not_called()


def test_inspection_endpoint_does_not_mutate_package_row(monkeypatch):
    package = package_record(validation_status="stale")
    before = deepcopy(package.__dict__)
    setup_route(monkeypatch, package)

    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    teardown_route()
    assert response.status_code == 200, response.text
    assert package.__dict__ == before


def test_inspection_endpoint_rejects_other_user(monkeypatch):
    async def fake_get_package(_session, _user_id, _package_id):
        raise ResumeIntelligencePackageOwnershipError("You do not have access to this resume intelligence package.")

    monkeypatch.setattr(inspector_route, "get_resume_intelligence_package", fake_get_package)
    app.dependency_overrides[inspector_route.db_session] = fake_session
    app.dependency_overrides[inspector_route.current_user_id] = auth_override

    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    teardown_route()
    assert response.status_code == 404


def test_inspection_endpoint_requires_authentication():
    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    assert response.status_code == 401


def test_inspection_endpoint_missing_package_returns_404(monkeypatch):
    async def fake_get_package(_session, _user_id, _package_id):
        raise ResumeIntelligencePackageNotFoundError("Resume intelligence package not found.")

    monkeypatch.setattr(inspector_route, "get_resume_intelligence_package", fake_get_package)
    app.dependency_overrides[inspector_route.db_session] = fake_session
    app.dependency_overrides[inspector_route.current_user_id] = auth_override

    response = TestClient(app).get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect")

    teardown_route()
    assert response.status_code == 404


def test_invalid_package_id_format_is_safe_not_found(monkeypatch):
    async def fake_get_package(_session, _user_id, _package_id):
        raise ResumeIntelligencePackageNotFoundError("Resume intelligence package not found.")

    monkeypatch.setattr(inspector_route, "get_resume_intelligence_package", fake_get_package)
    app.dependency_overrides[inspector_route.db_session] = fake_session
    app.dependency_overrides[inspector_route.current_user_id] = auth_override

    response = TestClient(app).get("/api/resume-intelligence/not-a-uuid/inspect")

    teardown_route()
    assert response.status_code == 404


def test_subroutes_return_summary_experience_skill_and_requirement(monkeypatch):
    package = package_record()
    setup_route(monkeypatch, package)
    client = TestClient(app)

    summary = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/summary")
    role = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/experiences/exp-current")
    bullet = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/experiences/exp-current/bullets/bullet-stored-api")
    skills = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/skills")
    skill = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/skills/skill-csharp")
    requirements = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/requirements")
    requirement = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/requirements/req-csharp")

    teardown_route()
    assert summary.status_code == 200
    assert role.status_code == 200
    assert bullet.status_code == 200
    assert skills.status_code == 200
    assert skill.status_code == 200
    assert requirements.status_code == 200
    assert requirement.status_code == 200
    assert bullet.json()["bulletId"] == "bullet-stored-api"
    assert skill.json()["canonicalName"] == "C#"
    assert requirement.json()["covered"] is True


def test_filtered_endpoints_match_comprehensive_inspection(monkeypatch):
    package = package_record()
    setup_route(monkeypatch, package)
    client = TestClient(app)

    inspect_body = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect").json()
    summary = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/summary").json()
    experiences = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/experiences").json()
    skill = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/skills/skill-csharp").json()
    requirement = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/requirements/req-csharp").json()

    teardown_route()
    assert summary == inspect_body["summary"]
    assert experiences == inspect_body["experienceOverview"]
    assert skill == inspect_body["skillsOverview"]["skills"][0]
    assert requirement == [item for item in inspect_body["requirementCoverage"] if item["requirementId"] == "req-csharp"][0]


def test_inspection_responses_are_deterministic(monkeypatch):
    package = package_record()
    setup_route(monkeypatch, package)
    client = TestClient(app)

    first = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect").json()
    second = client.get(f"/api/resume-intelligence/{PACKAGE_ID}/inspect").json()

    teardown_route()
    assert first == second


def test_bullet_id_from_another_role_is_not_returned_for_requested_role():
    package = package_record()
    other_role = deepcopy(package.experience_intelligence_json["roleIntelligence"][0])
    other_role["experienceId"] = "exp-other"
    other_role["bullets"][0]["bulletId"] = "bullet-other"
    package.experience_intelligence_json["roleIntelligence"].append(other_role)

    wrong_role_lookup = inspect_resume_intelligence_package(package).experience_overview.roles[1]
    missing = inspector_route.inspect_experience_bullet(package, wrong_role_lookup.experience_id, "bullet-stored-api")

    assert missing.validation_status == "missing"
    assert missing.bullet_id == "bullet-stored-api"
