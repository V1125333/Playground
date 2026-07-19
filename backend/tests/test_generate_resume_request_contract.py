from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.routes.resumes import validate_profile_snapshot
from app.schemas.resume import CandidateProfile, GenerateResumeRequest, ProfileLocation, ProfileExperienceDate, ResumeContact, ResumeExperience, SkillCategory
from app.services.profile_service import ensure_profile_record_ids


def persisted_profile() -> CandidateProfile:
    return ensure_profile_record_ids(
        CandidateProfile(
            name="Venu Madhav Pendurthi",
            title="Senior .NET Developer",
            contact=ResumeContact(
                email="venu@example.com",
                phone="+12014436937",
                location="Hartford, CT",
                locationData=ProfileLocation(city="Hartford", state="CT", country="United States"),
            ),
            skills=[
                SkillCategory(category="Programming Languages", categoryId="programming-languages", categoryName="Programming Languages", order=0, items=["C#", "SQL"]),
                SkillCategory(category="Backend Development", categoryId="backend-development", categoryName="Backend Development", order=1, items=[".NET", "REST APIs"]),
            ],
            experience=[
                ResumeExperience(
                    experienceId="exp-current",
                    company="Infosys",
                    clientName="Molina Healthcare",
                    role="Senior .NET Developer",
                    location="Hartford, CT",
                    locationData=ProfileLocation(city="Hartford", state="CT", country="United States"),
                    startDate="2025-01",
                    startDateData=ProfileExperienceDate(month=1, year=2025),
                    endDate="Present",
                    endDateData=None,
                    isCurrentRole=True,
                    rawNotes="Stored evidence stays on the backend profile.",
                    bullets=["Generated bullets are not accepted from generate requests."],
                ),
                ResumeExperience(
                    experienceId="exp-past",
                    company="E-Universe Technologies LLC",
                    role="Sr. Full Stack .NET Developer",
                    location="Chicago, IL",
                    locationData=ProfileLocation(city="Chicago", state="IL", country="United States"),
                    startDate="2023-07",
                    startDateData=ProfileExperienceDate(month=7, year=2023),
                    endDate="2025-01",
                    endDateData=ProfileExperienceDate(month=1, year=2025),
                ),
            ],
        )
    )


def profile_record(profile: CandidateProfile | None = None, *, version: int = 3):
    return SimpleNamespace(
        profile_id="profile-123",
        profile_version=version,
        profile_data=profile or persisted_profile(),
        content_hash="hash",
        updated_at="2026-07-01T00:00:00+00:00",
    )


def canonical_payload(**overrides):
    payload = {
        "profileId": "profile-123",
        "profileVersion": 3,
        "candidate": {
            "firstName": "Venu",
            "lastName": "Madhav Pendurthi",
            "currentTitle": "Senior .NET Developer",
            "email": "venu@example.com",
            "phone": "+12014436937",
            "location": {"city": "Hartford", "state": "CT", "country": "United States", "displayValue": "Hartford, CT"},
        },
        "skills": [
            {"categoryId": "programming-languages", "categoryName": "Programming Languages", "order": 0, "items": ["C#", "SQL"]},
            {"categoryId": "backend-development", "categoryName": "Backend Development", "order": 1, "items": [".NET", "REST APIs"]},
        ],
        "workExperience": [
            {
                "experienceId": "exp-current",
                "companyName": "Infosys",
                "clientName": "Molina Healthcare",
                "roleTitle": "Senior .NET Developer",
                "location": {"city": "Hartford", "state": "CT", "country": "United States", "displayValue": "Hartford, CT"},
                "startDate": {"month": 1, "year": 2025, "displayValue": "Jan 2025"},
                "endDate": None,
                "isCurrentRole": True,
            },
            {
                "experienceId": "exp-past",
                "companyName": "E-Universe Technologies LLC",
                "clientName": None,
                "roleTitle": "Sr. Full Stack .NET Developer",
                "location": {"city": "Chicago", "state": "IL", "country": "United States", "displayValue": "Chicago, IL"},
                "startDate": {"month": 7, "year": 2023, "displayValue": "Jul 2023"},
                "endDate": {"month": 1, "year": 2025, "displayValue": "Jan 2025"},
                "isCurrentRole": False,
            },
        ],
        "job": {
            "description": "Need C#, .NET, REST APIs, SQL, and Agile delivery.",
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
        "generationSettings": {
            "maximumPages": 2,
            "bulletsPerRecentRole": 5,
            "bulletsPerOlderRole": 4,
            "includeProjects": True,
            "includeCertifications": True,
            "includeUnmatchedKeywords": False,
            "writingStyle": "balanced",
        },
    }
    payload.update(overrides)
    return payload


def test_complete_canonical_request_normalizes_job_and_preserves_structured_skills():
    request = GenerateResumeRequest.model_validate(canonical_payload())

    assert request.profile_id == "profile-123"
    assert request.profile_version == 3
    assert request.job_description == "Need C#, .NET, REST APIs, SQL, and Agile delivery."
    assert request.target_role == "Software Engineer IV"
    assert request.target_company == "Velera"
    assert request.skills[0].items == ["C#", "SQL"]
    assert request.work_experience[0].end_date is None
    assert request.resume_preferences.header_visibility.github_url is False


def test_work_experience_rejects_generated_bullet_fields():
    payload = canonical_payload()
    payload["workExperience"][0]["bullets"] = ["Generated bullet"]

    with pytest.raises(ValidationError, match="Generated resume bullet fields are not accepted"):
        GenerateResumeRequest.model_validate(payload)


def test_past_role_requires_end_date_and_end_date_cannot_precede_start_date():
    missing_end = canonical_payload()
    missing_end["workExperience"][1]["endDate"] = None
    with pytest.raises(ValidationError, match="endDate is required"):
        GenerateResumeRequest.model_validate(missing_end)

    reversed_dates = canonical_payload()
    reversed_dates["workExperience"][1]["endDate"] = {"month": 1, "year": 2020, "displayValue": "2020-01"}
    with pytest.raises(ValidationError, match="must not be before"):
        GenerateResumeRequest.model_validate(reversed_dates)


def test_invalid_candidate_and_duplicate_category_ids_fail():
    invalid_email = canonical_payload()
    invalid_email["candidate"]["email"] = "not-an-email"
    with pytest.raises(ValidationError, match="valid candidate email"):
        GenerateResumeRequest.model_validate(invalid_email)

    duplicate_ids = canonical_payload()
    duplicate_ids["skills"][1]["categoryId"] = "programming-languages"
    duplicate_ids["skills"][1]["categoryName"] = "Programming Languages"
    with pytest.raises(ValidationError, match="Duplicate skill category IDs"):
        GenerateResumeRequest.model_validate(duplicate_ids)


def test_location_country_cannot_be_state_city_or_indian_state():
    state_country = canonical_payload()
    state_country["candidate"]["location"]["country"] = "CT"
    with pytest.raises(ValidationError, match="US state abbreviation"):
        GenerateResumeRequest.model_validate(state_country)

    city_country = canonical_payload()
    city_country["workExperience"][0]["location"]["country"] = "Hartford"
    with pytest.raises(ValidationError, match="cannot equal city"):
        GenerateResumeRequest.model_validate(city_country)

    indian_state_country = canonical_payload()
    indian_state_country["workExperience"][0]["location"] = {
        "city": "Visakhapatnam",
        "state": None,
        "country": "Andhra Pradesh",
        "displayValue": "Visakhapatnam, Andhra Pradesh",
    }
    with pytest.raises(ValidationError, match="Indian state name"):
        GenerateResumeRequest.model_validate(indian_state_country)


def test_link_visibility_flags_can_be_true_or_false():
    payload = canonical_payload()
    payload["resumePreferences"]["headerVisibility"]["githubUrl"] = True

    request = GenerateResumeRequest.model_validate(payload)

    assert request.resume_preferences.header_visibility.github_url is True


def test_legacy_request_still_parses_temporarily_and_canonical_job_wins():
    request = GenerateResumeRequest.model_validate(
        {
            "profileId": "profile-123",
            "job_description": "Legacy JD",
            "target_role": "Legacy Role",
            "job": {"description": "Canonical JD", "targetRole": "Canonical Role", "targetCompany": "", "level": "Senior"},
        }
    )

    assert request.job_description == "Canonical JD"
    assert request.target_role == "Canonical Role"
    assert request.target_company == ""


def test_profile_snapshot_validates_against_persisted_profile():
    request = GenerateResumeRequest.model_validate(canonical_payload())

    validate_profile_snapshot(request, profile_record())


def test_stale_profile_version_returns_conflict():
    request = GenerateResumeRequest.model_validate(canonical_payload(profileVersion=2))

    with pytest.raises(HTTPException) as exc_info:
        validate_profile_snapshot(request, profile_record(version=3))

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["currentProfileVersion"] == 3


def test_snapshot_cannot_override_persisted_profile_data():
    payload = canonical_payload()
    payload["candidate"]["firstName"] = "Different"
    request = GenerateResumeRequest.model_validate(payload)

    with pytest.raises(HTTPException) as exc_info:
        validate_profile_snapshot(request, profile_record())

    assert exc_info.value.status_code == 400
    assert "candidate name" in exc_info.value.detail
