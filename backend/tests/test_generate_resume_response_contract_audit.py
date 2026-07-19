from __future__ import annotations

from app.schemas.resume import GenerateResumeResponse
from app.services.resume_generation_pipeline import evidence_aware_keyword_score, structured_to_resume_content
from test_resume_output_contract_audit import record_for, run_pipeline


EXPECTED_TOP_LEVEL_FIELDS = {
    "resumeId",
    "atsAnalysis",
    "generationMetadata",
    "resume",
    "atsScore",
    "breakdown",
    "suggestions",
    "aiMetrics",
    "structuredResume",
    "validationResult",
    "persistedResumeId",
}


def test_generate_resume_response_contract_shape_is_stable() -> None:
    result = run_pipeline()
    response = result.response.model_copy(update={"resume_id": "generated-id", "persisted_resume_id": "generated-id"})
    payload = response.model_dump(mode="json", by_alias=True)

    assert set(payload) == EXPECTED_TOP_LEVEL_FIELDS
    assert payload["resumeId"] == "generated-id"
    assert payload["persistedResumeId"] == "generated-id"
    assert payload["structuredResume"]
    assert payload["validationResult"]
    assert payload["atsAnalysis"]
    assert payload["generationMetadata"]
    assert "coverage" in payload["breakdown"]
    assert payload["atsAnalysis"]["score"] == payload["atsScore"]
    assert payload["atsAnalysis"]["coverage"] == payload["breakdown"]["coverage"]
    assert payload["atsAnalysis"]["suggestions"] == payload["suggestions"]
    assert set(payload["breakdown"]["coverage"]) == {
        "supportedAndCovered",
        "supportedButNotRepresented",
        "adjacentUnsupported",
        "unmatched",
        "suggestedExcluded",
    }
    assert "semanticPlan" not in payload
    assert "layoutContract" not in payload
    GenerateResumeResponse.model_validate(payload)


def test_flattened_resume_is_derived_from_structured_resume_for_compatibility() -> None:
    result = run_pipeline()
    expected = structured_to_resume_content(result.candidate, result.structured)
    experience_section = next(section for section in result.structured.sections if section.type == "experience")

    assert result.response.resume.model_dump(mode="json", by_alias=True) == expected.model_dump(mode="json", by_alias=True)
    assert result.response.resume.experience[0].bullets[0] == experience_section.content[0]["bullets"][0]["currentText"]


def test_ats_score_and_breakdown_use_same_evidence_aware_result() -> None:
    result = run_pipeline()

    assert result.response.ats_score >= 0
    assert result.response.ats_analysis.score == result.response.ats_score
    assert result.response.breakdown.keyword_match >= 0
    assert result.response.breakdown.coverage["supportedAndCovered"]
    assert result.response.breakdown.keyword_match == evidence_aware_keyword_score(result.response.breakdown.coverage)
    assert result.response.ats_analysis.breakdown.keyword_match == result.response.breakdown.keyword_match
    assert result.response.ats_analysis.coverage == result.response.breakdown.coverage


def test_generation_metadata_is_public_and_ai_metrics_is_legacy_alias() -> None:
    result = run_pipeline()
    payload = result.response.model_dump(mode="json", by_alias=True)

    assert payload["generationMetadata"]["model"] is None
    assert payload["generationMetadata"]["pipelineVersion"] == result.structured.generation_algorithm_version
    assert payload["aiMetrics"]["generationTimeMs"] == payload["generationMetadata"]["durationMs"]
    assert payload["aiMetrics"]["atsScore"] == payload["atsAnalysis"]["score"]


def test_no_prompt_secret_or_raw_debug_payload_is_returned() -> None:
    result = run_pipeline()
    payload_text = result.response.model_dump_json(by_alias=True).lower()

    assert "semanticplan" not in payload_text
    assert "layoutcontract" not in payload_text
    forbidden = [
        "api_key",
        "apikey",
        "authorization",
        "bearer ",
        "openai_api_key",
        "system prompt",
        "chain of thought",
        "raw request",
        "raw response",
    ]
    assert all(term not in payload_text for term in forbidden)


def test_diagnostic_response_objects_are_not_persisted_as_resume_content() -> None:
    result = run_pipeline()
    record = record_for(result.structured, result.context)
    persisted_payload = record.model_dump(mode="json", by_alias=True)
    resume_json_text = record.resume_json.model_dump_json(by_alias=True)

    assert "semanticPlan" not in resume_json_text
    assert "aiMetrics" not in resume_json_text
    assert "layoutContract" not in resume_json_text
    assert "validationResult" not in resume_json_text
    assert "suggestions" not in resume_json_text
    assert "resumeJson" in persisted_payload
    assert "jobAnalysisJson" in persisted_payload
    assert "profileMatchJson" in persisted_payload


def test_legacy_consumers_can_parse_flattened_resume_and_top_level_score() -> None:
    result = run_pipeline()
    payload = result.response.model_dump(mode="json", by_alias=True)

    assert isinstance(payload["resume"]["experience"][0]["bullets"][0], str)
    assert isinstance(payload["atsScore"], int)
    assert isinstance(payload["breakdown"]["matchedKeywords"], list)
    assert isinstance(payload["suggestions"], list)


def test_canonical_fields_are_authoritative_when_legacy_aliases_conflict() -> None:
    result = run_pipeline()
    payload = result.response.model_dump(mode="json", by_alias=True)
    payload["atsScore"] = 1
    payload["breakdown"]["keywordMatch"] = 1
    payload["suggestions"] = [{"text": "stale", "points": 1}]
    payload["persistedResumeId"] = "legacy-id"

    parsed = GenerateResumeResponse.model_validate(payload)

    assert parsed.ats_score == parsed.ats_analysis.score
    assert parsed.breakdown.keyword_match == parsed.ats_analysis.breakdown.keyword_match
    assert parsed.suggestions == parsed.ats_analysis.suggestions
    assert parsed.persisted_resume_id == parsed.resume_id
