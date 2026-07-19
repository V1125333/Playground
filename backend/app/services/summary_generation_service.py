from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from app.core.config import settings
from app.schemas.resume import CandidateProfile, GenerateResumeRequest, JobAnalysisResponse, ProfileMatchSummary
from app.services.ai_usage import AICompletionResult, get_ai_service
from app.services.summary_planner import (
    SUMMARY_MAX_WORDS,
    SUMMARY_MIN_SENTENCES,
    SummaryBuildResult,
    SummaryGenerationResult,
    SummaryPlanner,
    clean_text,
    deterministic_summary,
    repair_summary_result,
    validate_summary_result,
)


SUMMARY_SYSTEM_PROMPT = (
    "You are an expert technical resume writer.\n\n"
    "Write a concise, professional resume summary tailored to the supplied target job.\n\n"
    "The candidate profile is the source of truth.\n\n"
    "The job description may change emphasis, terminology, capability selection, and technology "
    "prioritization, but it may not introduce unsupported technologies, responsibilities, metrics, "
    "domains, leadership claims, architecture claims, or years of specialized experience.\n\n"
    "Preserve the candidate's primary professional identity unless the profile explicitly supports a "
    "different identity.\n\n"
    "Use only facts supported by the candidate profile and approved Summary Planner signals.\n\n"
    "Do not treat company names, client names, locations, dates, education records, or contact "
    "information as professional capabilities.\n\n"
    "Do not use internal phrases such as: ATS, matched keyword, evidence-backed, grounded in, semantic "
    "match, candidate profile, job description.\n\n"
    "Do not write a keyword list.\n\n"
    "Do not use generic filler such as: results-driven professional, proven track record, known for excellence.\n\n"
    "Prefer concrete technical capabilities, relevant technologies, delivery themes, and business value.\n\n"
    "Return JSON only."
)
SUMMARY_PROMPT_VERSION = "summary-generation-v2-intelligence"


class SummaryModelResponse(BaseModel):
    summary: str
    used_evidence_ids: list[str] = Field(default_factory=list, alias="usedEvidenceIds")
    used_technologies: list[str] = Field(default_factory=list, alias="usedTechnologies")
    used_capabilities: list[str] = Field(default_factory=list, alias="usedCapabilities")
    excluded_jd_signals: list[str] = Field(default_factory=list, alias="excludedJdSignals")
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")

    model_config = {"populate_by_name": True}


class SummaryGenerationDiagnostics(BaseModel):
    enabled: bool
    model: str
    mode: str
    retry_count: int = Field(default=0, alias="retryCount")
    input_profile_version: int = Field(default=0, alias="inputProfileVersion")
    analysis_hash: str = Field(default="", alias="analysisHash")
    used_evidence_ids: list[str] = Field(default_factory=list, alias="usedEvidenceIds")
    used_technologies: list[str] = Field(default_factory=list, alias="usedTechnologies")
    used_capabilities: list[str] = Field(default_factory=list, alias="usedCapabilities")
    excluded_jd_signals: list[str] = Field(default_factory=list, alias="excludedJdSignals")
    risk_flags: list[str] = Field(default_factory=list, alias="riskFlags")

    model_config = {"populate_by_name": True}


class SummaryAIService(Protocol):
    def model_for(self, model_key: str) -> str:
        ...

    async def responses_json(self, **kwargs) -> AICompletionResult:
        ...


async def generate_summary(
    *,
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    job_analysis: JobAnalysisResponse | None,
    profile_match: ProfileMatchSummary | None,
    planner: SummaryPlanner,
    ai_service: SummaryAIService | None = None,
    job_id: str = "",
    profile_version: int = 0,
    max_retries: int = 1,
) -> SummaryBuildResult:
    service = ai_service or get_ai_service()
    should_use_openai = bool(settings.openai_api_key and settings.ai_summary_generation_enabled)
    if should_use_openai:
        validation_errors: list[str] = []
        for attempt in range(max_retries + 1):
            try:
                model_response = await call_summary_model(
                    service=service,
                    profile=profile,
                    payload=payload,
                    job_analysis=job_analysis,
                    profile_match=profile_match,
                    planner=planner,
                    job_id=job_id,
                    profile_version=profile_version,
                    previous_errors=validation_errors,
                )
                generation = model_response_to_generation(model_response, mode="openai" if attempt == 0 else "retry")
                validation = validate_summary_result(generation, planner)
                if validation.is_valid:
                    return SummaryBuildResult(planner=planner, generation=generation, validation=validation)
                validation_errors = validation.errors
            except Exception as exc:
                validation_errors = [f"Summary OpenAI generation failed: {exc}"]
                if attempt >= max_retries:
                    break

    fallback = deterministic_summary(planner).model_copy(update={"generation_method": "deterministic_fallback"})
    validation = validate_summary_result(fallback, planner)
    if not validation.is_valid:
        repaired = repair_summary_result(fallback, planner, validation).model_copy(update={"generation_method": "deterministic_fallback"})
        repaired_validation = validate_summary_result(repaired, planner)
        return SummaryBuildResult(planner=planner, generation=repaired, validation=repaired_validation)
    return SummaryBuildResult(planner=planner, generation=fallback, validation=validation)


async def call_summary_model(
    *,
    service: SummaryAIService,
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    job_analysis: JobAnalysisResponse | None,
    profile_match: ProfileMatchSummary | None,
    planner: SummaryPlanner,
    job_id: str,
    profile_version: int,
    previous_errors: list[str],
) -> SummaryModelResponse:
    request_payload = build_summary_generation_input(
        profile=profile,
        payload=payload,
        job_analysis=job_analysis,
        profile_match=profile_match,
        planner=planner,
        profile_version=profile_version,
        previous_errors=previous_errors,
    )
    result = await service.responses_json(
        feature="summary_generation",
        purpose="Resume Summary Generation",
        model_key="summary_generation",
        system_prompt=SUMMARY_SYSTEM_PROMPT,
        user_payload=request_payload,
        json_schema=SummaryModelResponse.model_json_schema(by_alias=True),
        max_output_tokens=settings.openai_summary_max_output_tokens,
        timeout_seconds=settings.openai_summary_timeout_seconds,
        cache_parts={
            "profileVersion": profile_version,
            "profileName": profile.name,
            "jobDescription": payload.job_description,
            "targetRole": payload.target_role,
            "targetCompany": payload.target_company,
            "planner": planner.model_dump(mode="json", by_alias=True),
        },
        job_id=job_id,
    )
    return SummaryModelResponse.model_validate_json(result.content)


def build_summary_generation_input(
    *,
    profile: CandidateProfile,
    payload: GenerateResumeRequest,
    job_analysis: JobAnalysisResponse | None,
    profile_match: ProfileMatchSummary | None,
    planner: SummaryPlanner,
    profile_version: int,
    previous_errors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "candidateProfile": sanitized_candidate_profile(profile, planner),
        "targetJob": {
            "targetRole": payload.target_role,
            "targetCompany": payload.target_company,
            "seniority": payload.level,
            "jobDescription": payload.job_description,
            "typedTechnicalRequirements": typed_requirements(job_analysis, "technical")[:30],
            "typedResponsibilityRequirements": typed_requirements(job_analysis, "responsibility")[:30],
            "supportedRequirements": supported_requirements(profile_match)[:30],
            "partiallySupportedRequirements": partially_supported_requirements(profile_match)[:20],
            "unsupportedRequirements": unsupported_requirements(profile_match)[:20],
        },
        "summaryPlanner": {
            "stableIdentity": {
                "title": planner.candidate_identity.current_title,
                "experienceDisplay": planner.candidate_identity.years_of_experience_display,
            },
            "approvedTechnologies": planner.target_emphasis.top_supported_technologies,
            "approvedCapabilities": planner.target_emphasis.top_supported_capabilities,
            "supportedJdPriorities": [item.model_dump(mode="json", by_alias=True) for item in planner.supported_jd_priorities],
            "unsupportedJdPriorities": planner.unsupported_jd_only_technologies,
            "verifiedDomains": [item.value for item in planner.verified_domains],
            "evidenceIds": sorted(planner.evidence_ids),
            "targetEmphasis": planner.target_emphasis.model_dump(mode="json", by_alias=True),
        },
        "generationRules": {
            "minimumSentences": SUMMARY_MIN_SENTENCES,
            "preferredSentences": 3,
            "maximumSentences": 4,
            "maximumWords": SUMMARY_MAX_WORDS,
            "preserveCandidateIdentity": True,
            "tailorToJobDescription": True,
            "doNotInventExperience": True,
            "doNotInventMetrics": True,
            "doNotMentionUnsupportedTechnologies": True,
            "doNotCopyJobDescription": True,
            "doNotUseFirstPerson": True,
        },
        "previousValidationErrors": previous_errors or [],
        "diagnostics": {
            "profileVersion": profile_version,
            "analysisHash": getattr(job_analysis, "analysis_hash", "") if job_analysis else "",
        },
    }


def typed_requirements(job_analysis: JobAnalysisResponse | None, requirement_group: str) -> list[dict[str, Any]]:
    if not job_analysis:
        return []
    requirements = (
        job_analysis.normalized_requirements.technical_requirements
        if requirement_group == "technical"
        else job_analysis.normalized_requirements.responsibility_requirements
    )
    return [
        {
            "requirementId": item.requirement_id,
            "canonicalTerm": item.canonical_term,
            "category": item.category,
            "priority": str(item.priority.value if hasattr(item.priority, "value") else item.priority),
            "evidenceText": item.evidence_text,
            "sourceSentence": item.source_sentence,
        }
        for item in requirements
    ]


def supported_requirements(profile_match: ProfileMatchSummary | None) -> list[dict[str, Any]]:
    if not profile_match:
        return []
    return [
        {
            "requirementId": item.requirement_id,
            "requirement": item.requirement_value,
            "category": item.requirement_category,
            "priority": item.requirement_priority,
            "evidenceIds": [evidence.evidence_id for evidence in item.evidence if evidence.evidence_id],
        }
        for item in profile_match.matched_requirements
        if item.is_safe_to_use
    ]


def partially_supported_requirements(profile_match: ProfileMatchSummary | None) -> list[dict[str, Any]]:
    if not profile_match:
        return []
    return [
        {
            "requirementId": item.requirement_id,
            "requirement": item.requirement_value,
            "category": item.requirement_category,
            "priority": item.requirement_priority,
            "evidenceIds": [evidence.evidence_id for evidence in item.evidence if evidence.evidence_id],
            "requiresUserConfirmation": item.requires_user_confirmation,
            "safeToUse": item.is_safe_to_use,
        }
        for item in profile_match.partially_matched_requirements
        if item.evidence and item.is_safe_to_use
    ]


def unsupported_requirements(profile_match: ProfileMatchSummary | None) -> list[dict[str, str]]:
    if not profile_match:
        return []
    return [
        {
            "requirementId": item.requirement_id,
            "requirement": item.requirement_value,
            "category": item.requirement_category,
            "priority": item.requirement_priority,
        }
        for item in [*profile_match.unmatched_requirements, *profile_match.partially_matched_requirements]
        if not item.is_safe_to_use
    ]


def sanitized_candidate_profile(profile: CandidateProfile, planner: SummaryPlanner) -> dict[str, Any]:
    return {
        "identity": {
            "currentTitle": profile.title,
            "yearsOfExperience": planner.candidate_identity.years_of_experience,
            "experienceDisplay": planner.candidate_identity.years_of_experience_display,
            "primarySpecialization": planner.candidate_identity.primary_positioning,
        },
        "skills": [
            {"category": group.category_name or group.category, "items": group.items}
            for group in profile.skills
            if group.items
        ],
        "workExperience": [
            {
                "experienceId": role.experience_id,
                "companyName": role.company,
                "clientName": role.client_name,
                "roleTitle": role.role,
                "startDate": role.start_date,
                "endDate": None if role.end_date.casefold() == "present" else role.end_date,
                "isCurrentRole": role.is_current_role or role.end_date.casefold() == "present",
                "responsibilities": evidence_text_items(role.responsibilities, planner),
                "achievements": evidence_text_items(role.achievements, planner),
                "technologies": role.technologies,
                "domains": [item.value for item in planner.verified_domains if item.source == f"{role.role} at {role.company}"],
            }
            for role in profile.experience
        ],
        "projects": [
            {"projectId": project.project_id, "name": project.name, "bullets": project.bullets, "technologies": project.technologies}
            for project in profile.projects
        ],
        "certifications": [
            {"certificationId": cert.certification_id, "name": cert.name, "issuer": cert.issuer}
            for cert in profile.certifications
        ],
        "education": [
            {"educationId": edu.education_id, "degree": edu.degree, "institution": edu.institution}
            for edu in profile.education
        ],
    }


def evidence_text_items(values: list[str], planner: SummaryPlanner) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for value in values:
        evidence_id = evidence_id_for_text(value, planner)
        output.append({"text": clean_text(value), "evidenceId": evidence_id})
    return output


def evidence_id_for_text(value: str, planner: SummaryPlanner) -> str:
    normalized = clean_text(value).casefold()
    for collection in (planner.verified_capabilities, planner.allowed_metrics):
        for signal in collection:
            if signal.value.casefold() == normalized or normalized in signal.value.casefold():
                return signal.evidence_ids[0]
    return ""


def model_response_to_generation(response: SummaryModelResponse, *, mode: str) -> SummaryGenerationResult:
    return SummaryGenerationResult(
        summary=response.summary,
        usedEvidenceIds=response.used_evidence_ids,
        usedSignals=[*response.used_technologies, *response.used_capabilities],
        excludedSignals=response.excluded_jd_signals,
        riskFlags=response.risk_flags,
        generationMethod=mode,
    )
