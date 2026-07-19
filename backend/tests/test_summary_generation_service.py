from __future__ import annotations

import json
from dataclasses import dataclass, field

import pytest

from app.core.config import settings
from app.services.ai_usage import AICompletionResult, AIService
from app.services.summary_generation_service import (
    SUMMARY_SYSTEM_PROMPT,
    build_summary_generation_input,
    generate_summary,
)
from app.services.summary_planner import SummaryValidationCode
from app.services.summary_planner import deterministic_summary
from tests.test_summary_planner import analysis, keyword, planner_for


@dataclass
class FakeSummaryService:
    responses: list[str | Exception]
    model: str = "summary-test-model"
    calls: list[dict] = field(default_factory=list)

    def model_for(self, model_key: str) -> str:
        self.calls.append({"method": "model_for", "model_key": model_key})
        return self.model

    async def responses_json(self, **kwargs):
        self.calls.append({"method": "responses_json", **kwargs})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return AICompletionResult(
            content=response,
            model=self.model,
            input_tokens=10,
            output_tokens=10,
            total_tokens=20,
            estimated_cost=0,
            latency_ms=1,
            cache_hit=False,
        )


def model_json(summary: str, evidence_id: str, technologies: list[str], capabilities: list[str]) -> str:
    return json.dumps(
        {
            "summary": summary,
            "usedEvidenceIds": [evidence_id],
            "usedTechnologies": technologies,
            "usedCapabilities": capabilities,
            "excludedJdSignals": [],
            "riskFlags": [],
        }
    )


def valid_dotnet_summary(planner) -> str:
    return deterministic_summary(planner).summary


@pytest.fixture
def enabled_summary_ai(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_summary_generation_enabled", True)
    monkeypatch.setattr(settings, "openai_summary_model", "gpt-5.5")
    monkeypatch.setattr(settings, "openai_summary_max_output_tokens", 500)
    monkeypatch.setattr(settings, "openai_summary_timeout_seconds", 30)


@pytest.mark.asyncio
async def test_dedicated_summary_model_configuration_is_honored(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    evidence_id = next(iter(planner.evidence_ids))
    service = FakeSummaryService([model_json(valid_dotnet_summary(planner), evidence_id, ["C#", "SQL Server"], ["code reviews"])], model="gpt-5.5")

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        job_id="job-1",
    )

    assert result.generation.generation_method == "openai"
    assert any(call.get("model_key") == "summary_generation" for call in service.calls)
    responses_call = next(call for call in service.calls if call["method"] == "responses_json")
    assert responses_call["model_key"] == "summary_generation"
    assert responses_call["max_output_tokens"] == 500
    assert responses_call["timeout_seconds"] == 30
    assert responses_call["system_prompt"] == SUMMARY_SYSTEM_PROMPT


def test_ai_service_uses_summary_model_only_for_summary_key(monkeypatch) -> None:
    monkeypatch.setattr(settings, "openai_summary_model", "summary-only-model")
    monkeypatch.setattr(settings, "ai_model_resume_generation", "resume-generation-model")
    service = AIService()

    assert service.model_for("summary_generation") == "summary-only-model"
    assert service.model_for("resume_generation") == "resume-generation-model"


def test_summary_input_contains_profile_and_jd_but_excludes_email_phone() -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))

    payload = build_summary_generation_input(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        profile_version=3,
    )
    text = json.dumps(payload)

    assert "candidateProfile" in payload
    assert "targetJob" in payload
    assert request.job_description in text
    assert profile.contact.email not in text
    assert profile.contact.phone not in text
    assert payload["candidateProfile"]["workExperience"]
    assert payload["summaryPlanner"]["evidenceIds"]


@pytest.mark.asyncio
async def test_valid_structured_openai_response_is_used(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    evidence_id = next(iter(planner.evidence_ids))
    service = FakeSummaryService([model_json(valid_dotnet_summary(planner), evidence_id, ["C#", "SQL Server"], ["code reviews"])])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
    )

    assert result.validation.is_valid is True
    assert result.generation.summary == valid_dotnet_summary(planner)
    assert result.generation.generation_method == "openai"


@pytest.mark.asyncio
async def test_malformed_response_falls_back_to_deterministic(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    service = FakeSummaryService(["{not-json"])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=0,
    )

    assert result.generation.generation_method == "deterministic_fallback"
    assert result.validation.is_valid is True


@pytest.mark.asyncio
async def test_timeout_falls_back_to_deterministic(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    service = FakeSummaryService([TimeoutError("timeout")])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=0,
    )

    assert result.generation.generation_method == "deterministic_fallback"


@pytest.mark.asyncio
async def test_retry_success_after_invalid_summary(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    evidence_id = next(iter(planner.evidence_ids))
    invalid = model_json(
        "Senior Full Stack .NET Developer with 9.6+ years of experience using Java and Spring Boot.",
        evidence_id,
        ["Java"],
        [],
    )
    valid = model_json(valid_dotnet_summary(planner), evidence_id, ["C#", "SQL Server"], ["code reviews"])
    service = FakeSummaryService([invalid, valid])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=1,
    )

    assert result.generation.generation_method == "retry"
    assert len([call for call in service.calls if call["method"] == "responses_json"]) == 2


@pytest.mark.asyncio
async def test_retry_exhaustion_uses_fallback(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    evidence_id = next(iter(planner.evidence_ids))
    invalid = model_json(
        "Senior Full Stack .NET Developer with 9.6+ years of experience using Java and Spring Boot.",
        evidence_id,
        ["Java"],
        [],
    )
    service = FakeSummaryService([invalid, invalid])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=1,
    )

    assert result.generation.generation_method == "deterministic_fallback"


@pytest.mark.asyncio
async def test_unsupported_java_spring_leakage_is_rejected(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("Java"), keyword("Spring Boot"), keyword("C#")))
    evidence_id = next(iter(planner.evidence_ids))
    invalid = model_json(
        "Senior Full Stack .NET Developer with 9+ years of experience working in Java backend development using Java and Spring Boot.",
        evidence_id,
        ["Java", "Spring Boot"],
        [],
    )
    service = FakeSummaryService([invalid])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=0,
    )

    assert result.generation.generation_method == "deterministic_fallback"
    assert "Java" not in result.generation.summary
    assert "Spring Boot" not in result.generation.summary


@pytest.mark.asyncio
async def test_metadata_and_decimal_year_leakage_fall_back(enabled_summary_ai) -> None:
    profile, request, context, planner = planner_for(analysis(keyword("C#"), keyword("SQL Server")))
    evidence_id = next(iter(planner.evidence_ids))
    invalid = model_json(
        "Senior Full Stack .NET Developer with 9.6+ years of experience at Infosys in Hartford using C#.",
        evidence_id,
        ["C#"],
        [],
    )
    service = FakeSummaryService([invalid])

    result = await generate_summary(
        profile=profile,
        payload=request,
        job_analysis=request.job_analysis,
        profile_match=context.profile_match,
        planner=planner,
        ai_service=service,
        max_retries=0,
    )

    assert result.generation.generation_method == "deterministic_fallback"
    assert SummaryValidationCode.invalid_experience_display not in result.validation.validation_codes
    assert "9.6+" not in result.generation.summary
