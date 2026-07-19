from types import SimpleNamespace

from app.schemas.resume import GenerateResumeRequest
from app.core.config import settings
from app.services.resume_intelligence_store import (
    STALE_PACKAGE_MESSAGE,
    job_description_hash,
    package_stale_reasons,
)
from app.services.skill_evidence_index import SKILL_EVIDENCE_INDEX_VERSION
from app.services.skill_registry import SKILL_REGISTRY_VERSION
from app.services.skills_planner import SKILLS_PLANNER_VERSION
from app.services.experience_planner import EXPERIENCE_PLANNER_VERSION
from app.services.experience_prompt_builder import EXPERIENCE_PROMPT_VERSION
from app.services.experience_generation_service import experience_model_configuration_hash


def valid_experience_intelligence_json() -> dict:
    return {
        "plannerVersion": EXPERIENCE_PLANNER_VERSION,
        "experiencePromptInputs": [{"experienceId": "exp-current", "promptVersion": EXPERIENCE_PROMPT_VERSION, "validationResult": {"isValid": True}}],
        "roleIntelligence": [
            {
                "experienceId": "exp-current",
                "bullets": [
                    {
                        "bulletId": "bullet-1",
                        "order": 1,
                        "generatedText": "Built C# API delivery with SQL Server.",
                        "currentText": "Built C# API delivery with SQL Server.",
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
    }


def valid_skills_intelligence_json() -> dict:
    return {
        "categories": [
            {
                "category": "Languages",
                "order": 1,
                "skills": [],
            }
        ],
        "includedSkills": [],
        "excludedSkills": [],
        "plannerVersion": SKILLS_PLANNER_VERSION,
        "skillRegistryVersion": SKILL_REGISTRY_VERSION,
        "skillEvidenceIndexVersion": SKILL_EVIDENCE_INDEX_VERSION,
        "roleFamily": ".NET Application Development",
        "targetRole": "Software Engineer",
        "targetCompany": "Acme",
        "level": "Senior",
        "validationStatus": "valid",
        "warnings": [],
        "createdAt": "2026-07-19T00:00:00+00:00",
    }


def profile_record(*, profile_id: str = "11111111-1111-1111-1111-111111111111", version: int = 2, content_hash: str = "profile-hash"):
    return SimpleNamespace(profile_id=profile_id, profile_version=version, content_hash=content_hash)


def package_record(**overrides):
    values = {
        "profile_id": "11111111-1111-1111-1111-111111111111",
        "profile_version": 2,
        "profile_content_hash": "profile-hash",
        "job_description_hash": job_description_hash("Need C#, .NET, and SQL Server."),
        "target_role": "Software Engineer",
        "target_company": "Acme",
        "level": "Senior",
        "experience_intelligence_json": valid_experience_intelligence_json(),
        "skills_intelligence_json": valid_skills_intelligence_json(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def payload(**overrides) -> GenerateResumeRequest:
    data = {
        "job": {
            "description": "Need C#, .NET, and SQL Server.",
            "targetRole": "Software Engineer",
            "targetCompany": "Acme",
            "level": "Senior",
        }
    }
    data.update(overrides)
    return GenerateResumeRequest(**data)


def test_job_description_hash_ignores_whitespace_noise() -> None:
    assert job_description_hash("Need C# and SQL Server.") == job_description_hash("  Need   C# and SQL Server.  ")


def test_valid_package_has_no_stale_reasons() -> None:
    assert package_stale_reasons(package_record(), profile_record(), payload()) == []


def test_stale_jd_is_detected_with_expected_message_constant() -> None:
    reasons = package_stale_reasons(package_record(), profile_record(), payload(job={"description": "Need Java.", "targetRole": "Software Engineer", "targetCompany": "Acme", "level": "Senior"}))

    assert "job description changed" in reasons
    assert STALE_PACKAGE_MESSAGE == "Your profile or job description changed after analysis. Run Analyze & Match again."


def test_stale_profile_version_and_wrong_profile_are_detected() -> None:
    reasons = package_stale_reasons(
        package_record(profile_id="22222222-2222-2222-2222-222222222222", profile_version=1),
        profile_record(),
        payload(),
    )

    assert "profileId changed" in reasons
    assert "profileVersion changed" in reasons


def test_project_mapping_hash_change_makes_package_stale() -> None:
    reasons = package_stale_reasons(
        package_record(),
        profile_record(content_hash="profile-hash-after-project-link-change"),
        payload(),
    )

    assert "profile hash changed" in reasons


def test_stale_experience_planner_version_is_detected() -> None:
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json={"plannerVersion": "old-planner"}),
        profile_record(),
        payload(),
    )

    assert "experience planner version changed" in reasons


def test_stale_experience_prompt_version_is_detected() -> None:
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json={
            "plannerVersion": EXPERIENCE_PLANNER_VERSION,
            "experiencePromptInputs": [{"promptVersion": "old-prompt"}],
        }),
        profile_record(),
        payload(),
    )

    assert "experience prompt version changed" in reasons


def test_stale_experience_writer_prompt_version_is_detected() -> None:
    data = valid_experience_intelligence_json()
    data["writerPromptVersion"] = "old-writer"
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "experience writer prompt version changed" in reasons


def test_stale_experience_model_is_detected() -> None:
    data = valid_experience_intelligence_json()
    data["writerModel"] = "old-model"
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "experience model changed" in reasons


def test_stale_experience_model_configuration_hash_is_detected() -> None:
    data = valid_experience_intelligence_json()
    data["modelConfigurationHash"] = "old-config"
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "experience model configuration changed" in reasons


def test_stale_skills_planner_version_is_detected() -> None:
    data = valid_skills_intelligence_json()
    data["plannerVersion"] = "old-skills-planner"
    reasons = package_stale_reasons(
        package_record(skills_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "skills planner version changed" in reasons


def test_stale_skill_registry_version_is_detected() -> None:
    data = valid_skills_intelligence_json()
    data["skillRegistryVersion"] = "old-registry"
    reasons = package_stale_reasons(
        package_record(skills_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "skill registry version changed" in reasons


def test_stale_skill_evidence_index_version_is_detected() -> None:
    data = valid_skills_intelligence_json()
    data["skillEvidenceIndexVersion"] = "old-evidence-index"
    reasons = package_stale_reasons(
        package_record(skills_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "skill evidence index version changed" in reasons


def test_missing_skills_intelligence_is_stale() -> None:
    reasons = package_stale_reasons(
        package_record(skills_intelligence_json=None),
        profile_record(),
        payload(),
    )

    assert "skills intelligence missing" in reasons


def test_missing_experience_role_intelligence_for_valid_prompt_is_stale() -> None:
    data = valid_experience_intelligence_json()
    data["experiencePromptInputs"].append({"experienceId": "exp-older", "promptVersion": EXPERIENCE_PROMPT_VERSION, "validationResult": {"isValid": True}})
    reasons = package_stale_reasons(
        package_record(experience_intelligence_json=data),
        profile_record(),
        payload(),
    )

    assert "experience generated bullets missing for planned roles" in reasons
