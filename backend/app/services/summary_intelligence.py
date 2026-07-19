from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.core.config import settings
from app.schemas.resume import GenerateResumeRequest, SummaryIntelligence
from app.services.resume_intelligence_store import job_description_hash, normalized
from app.services.summary_generation_service import SUMMARY_PROMPT_VERSION
from app.services.summary_planner import SummaryBuildResult, SummaryGenerationResult


SUMMARY_INTELLIGENCE_STALE_MESSAGE = "Summary intelligence is missing or stale. Run Analyze & Match again."


def summary_model_configuration_hash(model: str | None = None) -> str:
    payload = "|".join(
        [
            model or settings.openai_summary_model,
            str(settings.openai_summary_max_output_tokens),
            str(settings.openai_summary_timeout_seconds),
            SUMMARY_PROMPT_VERSION,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_summary_intelligence(
    *,
    summary_build: SummaryBuildResult,
    model: str,
    profile_record,
    payload,
) -> SummaryIntelligence:
    status = "fallback" if summary_build.generation.generation_method == "deterministic_fallback" else "valid"
    if not summary_build.validation.is_valid:
        status = "invalid"
    return SummaryIntelligence(
        summary=summary_build.generation.summary,
        selectedTechnologies=summary_build.planner.target_emphasis.top_supported_technologies,
        selectedCapabilities=summary_build.planner.target_emphasis.top_supported_capabilities,
        usedEvidenceIds=summary_build.generation.used_evidence_ids,
        excludedJdTerms=[
            *summary_build.generation.excluded_signals,
            *summary_build.planner.target_emphasis.excluded_unsupported_signals,
        ],
        riskFlags=summary_build.generation.risk_flags,
        validationStatus=status,
        validationWarnings=[*summary_build.validation.errors, *summary_build.validation.warnings],
        generationMode=summary_build.generation.generation_method,
        model=model,
        profileId=profile_record.profile_id,
        profileVersion=profile_record.profile_version,
        profileHash=profile_record.content_hash,
        jobDescriptionHash=job_description_hash(payload.job_description),
        targetRole=(payload.target_role or "").strip(),
        targetCompany=(payload.target_company or "").strip(),
        level=(payload.level or "Senior").strip() or "Senior",
        promptVersion=SUMMARY_PROMPT_VERSION,
        modelConfigurationHash=summary_model_configuration_hash(model),
        createdAt=datetime.now(timezone.utc),
    )


def summary_generation_from_intelligence(summary: SummaryIntelligence) -> SummaryGenerationResult:
    return SummaryGenerationResult(
        summary=summary.summary,
        usedEvidenceIds=summary.used_evidence_ids,
        usedSignals=[*summary.selected_technologies, *summary.selected_capabilities],
        excludedSignals=summary.excluded_jd_terms,
        riskFlags=summary.risk_flags,
        generationMethod=summary.generation_mode,
    )


def validate_summary_intelligence_for_package(record, profile_record, payload: GenerateResumeRequest) -> SummaryIntelligence:
    if not record.summary_intelligence_json:
        raise ValueError("summary intelligence is missing")
    summary = SummaryIntelligence.model_validate(record.summary_intelligence_json)
    stale_reasons = summary_intelligence_stale_reasons(summary, profile_record, payload)
    if stale_reasons:
        raise ValueError("; ".join(stale_reasons))
    if summary.validation_status not in {"valid", "fallback"}:
        raise ValueError("summary intelligence is invalid")
    return summary


def summary_intelligence_stale_reasons(
    summary: SummaryIntelligence,
    profile_record,
    payload: GenerateResumeRequest,
) -> list[str]:
    reasons: list[str] = []
    if summary.profile_id != str(profile_record.profile_id):
        reasons.append("summary profileId changed")
    if summary.profile_version != profile_record.profile_version:
        reasons.append("summary profileVersion changed")
    if summary.profile_hash != profile_record.content_hash:
        reasons.append("summary profile hash changed")
    if summary.job_description_hash != job_description_hash(payload.job_description):
        reasons.append("summary job description changed")
    if normalized(summary.target_role) != normalized(payload.target_role):
        reasons.append("summary target role changed")
    if normalized(summary.target_company) != normalized(payload.target_company):
        reasons.append("summary target company changed")
    if normalized(summary.level) != normalized(payload.level or "Senior"):
        reasons.append("summary experience level changed")
    if summary.prompt_version != SUMMARY_PROMPT_VERSION:
        reasons.append("summary prompt version changed")
    if summary.model_configuration_hash != summary_model_configuration_hash():
        reasons.append("summary model configuration changed")
    return reasons
