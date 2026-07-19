import pytest

from app.core.config import settings
from app.schemas.resume import ExperienceBulletModelResponse, ExperiencePromptValidationResult
from app.services.ai_usage import AICompletionResult
from app.services.experience_generation_service import (
    EXPERIENCE_BULLET_COUNT_MISMATCH,
    EXPERIENCE_DUPLICATE_BULLET,
    EXPERIENCE_INVALID_EVIDENCE_ID,
    EXPERIENCE_INVALID_REQUIREMENT_ID,
    EXPERIENCE_METADATA_LEAKAGE,
    EXPERIENCE_REPEATED_OPENING,
    EXPERIENCE_TOO_LONG,
    EXPERIENCE_UNSUPPORTED_ARCHITECTURE,
    EXPERIENCE_UNSUPPORTED_LEADERSHIP,
    EXPERIENCE_UNSUPPORTED_METRIC,
    EXPERIENCE_UNSUPPORTED_TECHNOLOGY,
    experience_model_configuration_hash,
    generate_experience_intelligence,
    generate_experience_bullets,
    validate_experience_bullets,
)
from tests.test_experience_prompt_builder import prompt_for
from tests.test_experience_planner import profile, requirement


class FakeExperienceService:
    def __init__(self, *contents: str):
        self.contents = list(contents)
        self.calls = 0

    def model_for(self, model_key: str) -> str:
        assert model_key == "experience_generation"
        return "test-experience-model"

    async def responses_json(self, **kwargs) -> AICompletionResult:
        self.calls += 1
        content = self.contents.pop(0)
        assert kwargs["feature"] == "experience_generation"
        assert "experiencePromptInput" in kwargs["user_payload"]
        assert "email" not in str(kwargs["user_payload"]).lower()
        return AICompletionResult(
            content=content,
            model="test-experience-model",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            estimated_cost=0.0,
            latency_ms=1,
            cache_hit=False,
        )


class DynamicExperienceService:
    def __init__(self):
        self.calls: list[dict] = []

    def model_for(self, model_key: str) -> str:
        assert model_key == "experience_generation"
        return "test-experience-model"

    async def responses_json(self, **kwargs) -> AICompletionResult:
        self.calls.append(kwargs)
        prompt = kwargs["user_payload"]["experiencePromptInput"]
        evidence = prompt["approvedEvidence"]
        requirement_ids = prompt["supportedRequirementIds"]
        bullets = []
        verbs = ["Built", "Implemented", "Improved", "Reviewed", "Documented"]
        for index in range(prompt["writingRules"]["bulletCount"]):
            evidence_id = evidence[index % len(evidence)]["evidenceId"]
            bullets.append(
                {
                    "generatedText": f"{verbs[index % len(verbs)]} C# API delivery using SQL Server for enterprise application work.",
                    "supportingEvidenceIds": [evidence_id],
                    "supportedRequirementIds": requirement_ids[:1],
                }
            )
        content = ExperienceBulletModelResponse.model_validate(
            {"experienceId": prompt["experienceId"], "bullets": bullets}
        ).model_dump_json(by_alias=True)
        return AICompletionResult(
            content=content,
            model="test-experience-model",
            input_tokens=1,
            output_tokens=1,
            total_tokens=2,
            estimated_cost=0.0,
            latency_ms=1,
            cache_hit=False,
        )


def current_prompt(*requirements):
    candidate = profile()
    plan, _, _ = prompt_for(candidate, "Need C#, .NET, REST API, SQL Server.", *requirements)
    return next(prompt for prompt in plan.experience_prompt_inputs if prompt.experience_id == "exp-current")


def valid_model_response(prompt):
    evidence_ids = [item.evidence_id for item in prompt.approved_evidence]
    requirement_ids = prompt.supported_requirement_ids
    bullets = []
    verbs = ["Built", "Implemented", "Improved", "Reviewed", "Documented"]
    primary_evidence_id = next(
        item.evidence_id for item in prompt.approved_evidence if "C#" in item.text and "SQL Server" in item.text
    )
    for index in range(prompt.writing_rules.bullet_count):
        evidence_id = primary_evidence_id if index < 2 else evidence_ids[index % len(evidence_ids)]
        text = f"{verbs[index % len(verbs)]} C# API delivery using SQL Server for enterprise application work."
        bullets.append(
            {
                "generatedText": text,
                "supportingEvidenceIds": [evidence_id],
                "supportedRequirementIds": requirement_ids[:1],
            }
        )
    return ExperienceBulletModelResponse.model_validate({"experienceId": prompt.experience_id, "bullets": bullets})


def codes(validation):
    return {issue.code for issue in validation.issues}


def test_valid_structured_response_passes_validation() -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    validation = validate_experience_bullets(prompt, valid_model_response(prompt))

    assert validation.is_valid


@pytest.mark.asyncio
async def test_malformed_json_retries_and_succeeds(monkeypatch) -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_experience_generation_enabled", True)
    service = FakeExperienceService("not-json", valid_model_response(prompt).model_dump_json(by_alias=True))

    result = await generate_experience_bullets(prompt, service=service, max_retries=1)

    assert service.calls == 2
    assert result.validation_result.is_valid
    assert result.generation_method == "retry"


@pytest.mark.asyncio
async def test_retry_exhaustion_uses_deterministic_fallback(monkeypatch) -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_experience_generation_enabled", True)
    service = FakeExperienceService("not-json", "still-not-json")

    result = await generate_experience_bullets(prompt, service=service, max_retries=1)

    assert service.calls == 2
    assert result.generation_method == "deterministic_fallback"
    assert result.bullets


def test_validation_rejects_wrong_experience_and_bad_ids() -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    response = valid_model_response(prompt).model_copy(
        update={
            "experience_id": "other-role",
            "bullets": [
                valid_model_response(prompt).bullets[0].model_copy(
                    update={"supporting_evidence_ids": ["bad-evidence"], "supported_requirement_ids": ["bad-req"]}
                )
            ],
        }
    )

    validation = validate_experience_bullets(prompt, response)

    assert EXPERIENCE_INVALID_EVIDENCE_ID in codes(validation)
    assert EXPERIENCE_INVALID_REQUIREMENT_ID in codes(validation)


def test_validation_rejects_unsupported_java_aws_metric_leadership_architecture() -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    evidence_id = prompt.approved_evidence[0].evidence_id
    response = ExperienceBulletModelResponse.model_validate(
        {
            "experienceId": prompt.experience_id,
            "bullets": [
                {
                    "generatedText": "Led Java Spring Boot architecture on AWS by improving performance by 30%.",
                    "supportingEvidenceIds": [evidence_id],
                    "supportedRequirementIds": prompt.supported_requirement_ids[:1],
                }
            ],
        }
    )

    validation = validate_experience_bullets(prompt, response)

    assert EXPERIENCE_UNSUPPORTED_TECHNOLOGY in codes(validation)
    assert EXPERIENCE_UNSUPPORTED_METRIC in codes(validation)
    assert EXPERIENCE_UNSUPPORTED_LEADERSHIP in codes(validation)
    assert EXPERIENCE_UNSUPPORTED_ARCHITECTURE in codes(validation)


def test_validation_rejects_metadata_leakage_long_duplicate_and_repeated_openings() -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    evidence_id = prompt.approved_evidence[0].evidence_id
    text = "Built " + " ".join(["application"] * 40) + " for Infosys"
    response = ExperienceBulletModelResponse.model_validate(
        {
            "experienceId": prompt.experience_id,
            "bullets": [
                {"generatedText": text, "supportingEvidenceIds": [evidence_id], "supportedRequirementIds": prompt.supported_requirement_ids[:1]},
                {"generatedText": text, "supportingEvidenceIds": [evidence_id], "supportedRequirementIds": prompt.supported_requirement_ids[:1]},
            ],
        }
    )

    validation = validate_experience_bullets(prompt, response)

    assert EXPERIENCE_METADATA_LEAKAGE in codes(validation)
    assert EXPERIENCE_TOO_LONG in codes(validation)
    assert EXPERIENCE_DUPLICATE_BULLET in codes(validation)
    assert EXPERIENCE_REPEATED_OPENING in codes(validation)
    assert EXPERIENCE_BULLET_COUNT_MISMATCH in codes(validation)


@pytest.mark.asyncio
async def test_no_api_key_uses_fallback_without_calling_model(monkeypatch) -> None:
    prompt = current_prompt(requirement("C#"), requirement("SQL Server"))
    monkeypatch.setattr(settings, "openai_api_key", "")
    service = FakeExperienceService(valid_model_response(prompt).model_dump_json(by_alias=True))

    result = await generate_experience_bullets(prompt, service=service)

    assert service.calls == 0
    assert result.generation_method == "deterministic_fallback"


@pytest.mark.asyncio
async def test_generate_experience_intelligence_calls_model_once_per_valid_prompt_and_skips_invalid(monkeypatch) -> None:
    candidate = profile()
    plan, _, _ = prompt_for(candidate, "Need C#, REST API, SQL Server.", requirement("C#"), requirement("REST API"), requirement("SQL Server"))
    invalid_prompt = plan.experience_prompt_inputs[-1].model_copy(
        update={"validation_result": ExperiencePromptValidationResult(isValid=False, codes=["PROMPT_INSUFFICIENT_EVIDENCE"], warnings=[])}
    )
    plan = plan.model_copy(update={"experience_prompt_inputs": [*plan.experience_prompt_inputs[:-1], invalid_prompt]})
    valid_prompt_count = sum(1 for prompt in plan.experience_prompt_inputs if prompt.validation_result.is_valid)
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_experience_generation_enabled", True)
    service = DynamicExperienceService()

    result = await generate_experience_intelligence(plan, ai_service=service)

    assert len(service.calls) == valid_prompt_count
    assert len(result.role_intelligence) == valid_prompt_count
    assert result.validation_status == "invalid"
    assert result.model_configuration_hash == experience_model_configuration_hash("test-experience-model")
    assert all(role.model_configuration_hash == result.model_configuration_hash for role in result.role_intelligence)
    assert all(call["model_key"] == "experience_generation" for call in service.calls)
    assert all(call["max_output_tokens"] == settings.openai_experience_max_output_tokens for call in service.calls)
    assert all(call["timeout_seconds"] == settings.openai_experience_timeout_seconds for call in service.calls)
