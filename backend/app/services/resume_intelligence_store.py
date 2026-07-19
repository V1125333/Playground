from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import (
    ExperienceIntelligencePlan,
    GenerateResumeRequest,
    JobAnalysisResponse,
    ProfileMatchResponse,
    ProfileMatchSummary,
    ResumeIntelligencePackageSchema,
    SummaryIntelligence,
)
from app.core.config import settings
from app.services.experience_planner import EXPERIENCE_PLANNER_VERSION
from app.services.experience_prompt_builder import EXPERIENCE_PROMPT_VERSION
from app.services.experience_generation_service import experience_model_configuration_hash
from app.services.skills_planner import SkillsIntelligence, skills_intelligence_stale_reasons


STALE_PACKAGE_MESSAGE = "Your profile or job description changed after analysis. Run Analyze & Match again."
EXPERIENCE_INTELLIGENCE_STALE_MESSAGE = "Experience intelligence is missing or stale. Run Analyze & Match again."
SKILLS_INTELLIGENCE_STALE_MESSAGE = "Skills intelligence is missing or stale. Run Analyze & Match again."
logger = logging.getLogger(__name__)


class ResumeIntelligencePackageNotFoundError(Exception):
    pass


class ResumeIntelligencePackageOwnershipError(Exception):
    pass


class ResumeIntelligencePackageStaleError(Exception):
    pass


def job_description_hash(job_description: str) -> str:
    normalized = " ".join((job_description or "").strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def create_resume_intelligence_package(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    profile_record,
    payload,
    job_analysis: JobAnalysisResponse,
    profile_match: ProfileMatchResponse,
    summary_intelligence: SummaryIntelligence,
    experience_intelligence: ExperienceIntelligencePlan | None = None,
    skills_intelligence: SkillsIntelligence | None = None,
) -> ResumeIntelligencePackageSchema:
    from app.models.resume_intelligence import ResumeIntelligencePackageModel

    jd_hash = job_description_hash(payload.job_description)
    record = ResumeIntelligencePackageModel(
        user_id=user_id,
        profile_id=uuid.UUID(profile_record.profile_id),
        profile_version=profile_record.profile_version,
        profile_content_hash=profile_record.content_hash,
        job_description_hash=jd_hash,
        target_role=(payload.target_role or job_analysis.role_information.title or "").strip(),
        target_company=(payload.target_company or "").strip() or None,
        level=(payload.level or "Senior").strip() or "Senior",
        job_description=payload.job_description,
        job_intelligence_json=job_analysis.model_dump(mode="json", by_alias=True),
        normalized_requirements_json=job_analysis.normalized_requirements.model_dump(mode="json", by_alias=True),
        profile_match_json=profile_match.match_summary.model_dump(mode="json", by_alias=True),
        summary_intelligence_json=summary_intelligence.model_dump(mode="json", by_alias=True),
        experience_intelligence_json=experience_intelligence.model_dump(mode="json", by_alias=True) if experience_intelligence else None,
        skills_intelligence_json=skills_intelligence.model_dump(mode="json", by_alias=True) if skills_intelligence else None,
        validation_status=package_validation_status(job_analysis.analysis_warnings, experience_intelligence, skills_intelligence),
        validation_warnings=package_validation_warnings(job_analysis.analysis_warnings, experience_intelligence, skills_intelligence),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    logger.info(
        "resume_intelligence_package_created",
        extra={
            "package_id": str(record.id),
            "profile_id": str(record.profile_id),
            "validation_status": record.validation_status,
        },
    )
    return package_record_to_schema(record)


async def get_resume_intelligence_package(session: AsyncSession, user_id: uuid.UUID, package_id: str):
    from app.models.resume_intelligence import ResumeIntelligencePackageModel

    try:
        package_uuid = uuid.UUID(package_id)
    except ValueError as exc:
        raise ResumeIntelligencePackageNotFoundError("Resume intelligence package not found.") from exc
    result = await session.execute(select(ResumeIntelligencePackageModel).where(ResumeIntelligencePackageModel.id == package_uuid))
    record = result.scalar_one_or_none()
    if not record:
        raise ResumeIntelligencePackageNotFoundError("Resume intelligence package not found.")
    if record.user_id != user_id:
        raise ResumeIntelligencePackageOwnershipError("You do not have access to this resume intelligence package.")
    return record


async def validate_resume_intelligence_package(
    session: AsyncSession,
    user_id: uuid.UUID,
    package_id: str,
    profile_record,
    payload: GenerateResumeRequest,
):
    record = await get_resume_intelligence_package(session, user_id, package_id)
    warnings = package_stale_reasons(record, profile_record, payload)
    if warnings:
        record.validation_status = "stale"
        record.validation_warnings = warnings
        record.updated_at = datetime.now(timezone.utc)
        await session.commit()
        logger.info(
            "resume_intelligence_package_stale",
            extra={
                "package_id": str(record.id),
                "profile_id": str(record.profile_id),
                "reasons": warnings,
            },
        )
        if any(_is_skills_stale_reason(reason) for reason in warnings):
            raise ResumeIntelligencePackageStaleError(SKILLS_INTELLIGENCE_STALE_MESSAGE)
        raise ResumeIntelligencePackageStaleError(STALE_PACKAGE_MESSAGE)
    if record.validation_status not in {"valid", "valid_with_warnings"}:
        logger.info(
            "resume_intelligence_package_invalid_status",
            extra={
                "package_id": str(record.id),
                "profile_id": str(record.profile_id),
                "validation_status": record.validation_status,
            },
        )
        raise ResumeIntelligencePackageStaleError(STALE_PACKAGE_MESSAGE)
    logger.info(
        "resume_intelligence_package_reused",
        extra={
            "package_id": str(record.id),
            "profile_id": str(record.profile_id),
            "validation_status": record.validation_status,
        },
    )
    return record


def package_stale_reasons(record, profile_record, payload: GenerateResumeRequest) -> list[str]:
    reasons: list[str] = []
    if str(record.profile_id) != str(profile_record.profile_id):
        reasons.append("profileId changed")
    if record.profile_version != profile_record.profile_version:
        reasons.append("profileVersion changed")
    if record.profile_content_hash != profile_record.content_hash:
        reasons.append("profile hash changed")
    if record.job_description_hash != job_description_hash(payload.job_description):
        reasons.append("job description changed")
    if normalized(record.target_role) != normalized(payload.target_role):
        reasons.append("target role changed")
    if normalized(record.target_company or "") != normalized(payload.target_company):
        reasons.append("target company changed")
    if normalized(record.level) != normalized(payload.level or "Senior"):
        reasons.append("experience level changed")
    experience_intelligence = getattr(record, "experience_intelligence_json", None)
    if not experience_intelligence:
        reasons.append("experience intelligence missing")
    else:
        reasons.extend(experience_intelligence_stale_reasons(experience_intelligence))
    skills_intelligence = getattr(record, "skills_intelligence_json", None)
    reasons.extend(skills_intelligence_stale_reasons(skills_intelligence))
    return reasons


def experience_intelligence_stale_reasons(experience_intelligence: dict) -> list[str]:
    reasons: list[str] = []
    planner_version = experience_intelligence.get("plannerVersion") or experience_intelligence.get("planner_version")
    if planner_version != EXPERIENCE_PLANNER_VERSION:
        reasons.append("experience planner version changed")
    prompt_inputs = experience_intelligence.get("experiencePromptInputs") or experience_intelligence.get("experience_prompt_inputs") or []
    for prompt in prompt_inputs:
        prompt_version = prompt.get("promptVersion") or prompt.get("prompt_version")
        if prompt_version != EXPERIENCE_PROMPT_VERSION:
            reasons.append("experience prompt version changed")
            break
    writer_prompt_version = experience_intelligence.get("writerPromptVersion") or experience_intelligence.get("writer_prompt_version")
    if writer_prompt_version != settings.experience_writer_prompt_version:
        reasons.append("experience writer prompt version changed")
    writer_model = experience_intelligence.get("writerModel") or experience_intelligence.get("writer_model")
    if writer_model != settings.openai_experience_model:
        reasons.append("experience model changed")
    config_hash = experience_intelligence.get("modelConfigurationHash") or experience_intelligence.get("model_configuration_hash")
    if config_hash != experience_model_configuration_hash(writer_model):
        reasons.append("experience model configuration changed")
    prompt_inputs = experience_intelligence.get("experiencePromptInputs") or experience_intelligence.get("experience_prompt_inputs") or []
    valid_prompt_ids = {
        prompt.get("experienceId") or prompt.get("experience_id")
        for prompt in prompt_inputs
        if (prompt.get("validationResult") or prompt.get("validation_result") or {}).get("isValid")
    }
    role_intelligence = experience_intelligence.get("roleIntelligence") or experience_intelligence.get("role_intelligence") or []
    if not role_intelligence:
        reasons.append("experience generated bullets missing")
    generated_role_ids = {
        item.get("experienceId") or item.get("experience_id")
        for item in role_intelligence
    }
    if valid_prompt_ids and valid_prompt_ids - generated_role_ids:
        reasons.append("experience generated bullets missing for planned roles")
    invalid_roles = [
        item
        for item in role_intelligence
        if (item.get("validationStatus") or item.get("validation_status") or "") not in {"valid", "fallback", "warning"}
    ]
    if invalid_roles:
        reasons.append("experience generated bullets invalid")
    return reasons


def package_validation_status(
    analysis_warnings: list[str],
    experience_intelligence: ExperienceIntelligencePlan | None,
    skills_intelligence: SkillsIntelligence | None = None,
) -> str:
    if experience_intelligence is None:
        return "invalid"
    if experience_intelligence.validation_status == "invalid" or experience_intelligence.overall_validation_status == "invalid":
        return "invalid"
    if skills_intelligence is None:
        return "invalid"
    if skills_intelligence.validation_status == "invalid":
        return "invalid"
    if analysis_warnings or experience_intelligence.warnings or experience_intelligence.validation_status in {"warning", "valid_with_warnings"}:
        return "valid_with_warnings"
    if skills_intelligence.warnings or skills_intelligence.validation_status == "valid_with_warnings":
        return "valid_with_warnings"
    return "valid"


def package_validation_warnings(
    analysis_warnings: list[str],
    experience_intelligence: ExperienceIntelligencePlan | None,
    skills_intelligence: SkillsIntelligence | None = None,
) -> list[str]:
    warnings = list(analysis_warnings)
    if experience_intelligence is None:
        warnings.append("experience intelligence missing")
    else:
        warnings.extend(experience_intelligence.warnings)
    if skills_intelligence is None:
        warnings.append("skills intelligence missing")
    else:
        warnings.extend(skills_intelligence.warnings)
    return dedupe(warnings)


def normalized(value: str | None) -> str:
    return " ".join((value or "").strip().split()).casefold()


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = normalized(value)
        if key and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def package_record_to_job_analysis(record) -> JobAnalysisResponse:
    return JobAnalysisResponse.model_validate(record.job_intelligence_json)


def package_record_to_profile_match(record) -> ProfileMatchSummary:
    return ProfileMatchSummary.model_validate(record.profile_match_json)


def package_record_to_experience_intelligence(record) -> ExperienceIntelligencePlan:
    data = getattr(record, "experience_intelligence_json", None)
    if not data:
        raise ResumeIntelligencePackageStaleError(EXPERIENCE_INTELLIGENCE_STALE_MESSAGE)
    reasons = experience_intelligence_stale_reasons(data)
    if reasons:
        raise ResumeIntelligencePackageStaleError(EXPERIENCE_INTELLIGENCE_STALE_MESSAGE)
    return ExperienceIntelligencePlan.model_validate(data)


def package_record_to_skills_intelligence(record) -> SkillsIntelligence:
    data = getattr(record, "skills_intelligence_json", None)
    if not data:
        raise ResumeIntelligencePackageStaleError(SKILLS_INTELLIGENCE_STALE_MESSAGE)
    reasons = skills_intelligence_stale_reasons(data)
    if reasons:
        raise ResumeIntelligencePackageStaleError(SKILLS_INTELLIGENCE_STALE_MESSAGE)
    return SkillsIntelligence.model_validate(data)


def package_record_to_schema(record) -> ResumeIntelligencePackageSchema:
    return ResumeIntelligencePackageSchema(
        packageId=str(record.id),
        profileId=str(record.profile_id),
        profileVersion=record.profile_version,
        jobDescriptionHash=record.job_description_hash,
        targetRole=record.target_role,
        targetCompany=record.target_company or "",
        level=record.level,
        jobIntelligence=record.job_intelligence_json,
        normalizedRequirements=record.normalized_requirements_json,
        profileMatch=record.profile_match_json,
        summaryIntelligence=record.summary_intelligence_json,
        experienceIntelligence=getattr(record, "experience_intelligence_json", None),
        skillsIntelligence=getattr(record, "skills_intelligence_json", None),
        validationStatus=record.validation_status,
        validationWarnings=record.validation_warnings or [],
        createdAt=to_iso(record.created_at),
        updatedAt=to_iso(record.updated_at),
    )


def to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _is_skills_stale_reason(reason: str) -> bool:
    return "skill" in reason.casefold()
