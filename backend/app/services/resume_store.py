from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import CandidateProfile, ProfileMatchSummary, StructuredGeneratedResume, StructuredResumeRecord
from app.services.profile_matching import build_profile_evidence_index
from app.services.resume_validator import validate_structured_resume
from app.services.structured_bullets import normalize_structured_resume_bullets


class ResumeNotFoundError(Exception):
    pass


class ResumeOwnershipError(Exception):
    pass


async def create_generated_resume(
    session: AsyncSession,
    user_id: uuid.UUID,
    resume: StructuredGeneratedResume,
    job_analysis_json: dict,
    profile_match_json: dict,
    parent_resume_id: str = "",
) -> StructuredResumeRecord:
    from app.models.generated_resume import GeneratedResumeModel

    resume = normalize_structured_resume_bullets(resume)
    record = GeneratedResumeModel(
        user_id=user_id,
        profile_id=uuid.UUID(resume.profile_id),
        profile_version=resume.profile_version,
        profile_content_hash=resume.profile_content_hash,
        resume_name=resume.resume_name,
        target_job_title=resume.target_job_title,
        target_company=resume.target_company or None,
        job_description=resume.job_description,
        job_analysis_json=job_analysis_json,
        profile_match_json=profile_match_json,
        resume_json=resume.model_dump(mode="json", by_alias=True),
        template_id=resume.template_id,
        match_score=resume.match_score,
        generation_algorithm_version=resume.generation_algorithm_version,
        status=resume.status,
        version_number=resume.version_number,
        parent_resume_id=uuid.UUID(parent_resume_id) if parent_resume_id else None,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    updated_resume = resume.model_copy(
        update={
            "resume_id": str(record.id),
            "user_id": str(record.user_id),
            "created_at": record.created_at.isoformat(),
            "updated_at": record.updated_at.isoformat(),
        }
    )
    record.resume_json = updated_resume.model_dump(mode="json", by_alias=True)
    await session.commit()
    await session.refresh(record)
    return record_to_schema(record)


async def list_resumes(session: AsyncSession, user_id: uuid.UUID) -> list[StructuredResumeRecord]:
    from app.models.generated_resume import GeneratedResumeModel

    result = await session.execute(
        select(GeneratedResumeModel)
        .where(GeneratedResumeModel.user_id == user_id)
        .order_by(GeneratedResumeModel.updated_at.desc())
    )
    return [record_to_schema(record) for record in result.scalars().all()]


async def get_resume(session: AsyncSession, user_id: uuid.UUID, resume_id: str) -> StructuredResumeRecord:
    record = await get_resume_model(session, user_id, resume_id)
    return record_to_schema(record)


async def update_resume(
    session: AsyncSession,
    user_id: uuid.UUID,
    resume_id: str,
    resume: StructuredGeneratedResume,
    status: str = "draft",
) -> StructuredResumeRecord:
    record = await get_resume_model(session, user_id, resume_id)
    resume = normalize_structured_resume_bullets(resume)
    resume = await validate_resume_for_update(session, user_id, record.profile_id, resume, record.profile_match_json)
    record.resume_json = resume.model_dump(mode="json", by_alias=True)
    record.status = resume.status or status
    await session.commit()
    await session.refresh(record)
    return record_to_schema(record)


async def validate_resume_for_update(
    session: AsyncSession,
    user_id: uuid.UUID,
    profile_id: uuid.UUID,
    resume: StructuredGeneratedResume,
    profile_match_json: dict,
) -> StructuredGeneratedResume:
    from app.models.candidate_profile import CandidateProfileModel

    result = await session.execute(
        select(CandidateProfileModel).where(
            CandidateProfileModel.id == profile_id,
            CandidateProfileModel.user_id == user_id,
        )
    )
    profile_record = result.scalar_one_or_none()
    if not profile_record:
        return resume

    profile = CandidateProfile.model_validate(profile_record.profile_data)
    profile_match = ProfileMatchSummary.model_validate(profile_match_json)
    validation = validate_structured_resume(
        resume,
        build_profile_evidence_index(profile, str(profile_id)),
        profile_match,
    )
    warnings = [issue.message for issue in [*validation.warnings, *validation.errors]]
    return resume.model_copy(
        update={
            "warnings": sorted(set([*resume.warnings, *warnings]))[:20],
            "status": "draft" if validation.is_valid else "needs_review",
        }
    )


async def save_resume_version(session: AsyncSession, user_id: uuid.UUID, resume_id: str) -> StructuredResumeRecord:
    source = await get_resume_model(session, user_id, resume_id)
    from app.models.generated_resume import GeneratedResumeModel

    next_version = await next_version_number(session, user_id, source.id)
    resume = normalize_structured_resume_bullets(StructuredGeneratedResume.model_validate(source.resume_json)).model_copy(
        update={"version_number": next_version, "status": "draft"}
    )
    record = GeneratedResumeModel(
        user_id=source.user_id,
        profile_id=source.profile_id,
        profile_version=source.profile_version,
        profile_content_hash=source.profile_content_hash,
        resume_name=source.resume_name,
        target_job_title=source.target_job_title,
        target_company=source.target_company,
        job_description=source.job_description,
        job_analysis_json=source.job_analysis_json,
        profile_match_json=source.profile_match_json,
        resume_json=resume.model_dump(mode="json", by_alias=True),
        template_id=source.template_id,
        match_score=source.match_score,
        generation_algorithm_version=source.generation_algorithm_version,
        status="draft",
        version_number=next_version,
        parent_resume_id=source.id,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record_to_schema(record)


async def list_resume_versions(session: AsyncSession, user_id: uuid.UUID, resume_id: str) -> list[StructuredResumeRecord]:
    source = await get_resume_model(session, user_id, resume_id)
    from app.models.generated_resume import GeneratedResumeModel

    result = await session.execute(
        select(GeneratedResumeModel)
        .where((GeneratedResumeModel.id == source.id) | (GeneratedResumeModel.parent_resume_id == source.id))
        .where(GeneratedResumeModel.user_id == user_id)
        .order_by(GeneratedResumeModel.version_number.asc())
    )
    return [record_to_schema(record) for record in result.scalars().all()]


async def delete_resume(session: AsyncSession, user_id: uuid.UUID, resume_id: str) -> None:
    record = await get_resume_model(session, user_id, resume_id)
    await session.delete(record)
    await session.commit()


async def next_version_number(session: AsyncSession, user_id: uuid.UUID, parent_id: uuid.UUID) -> int:
    from app.models.generated_resume import GeneratedResumeModel

    result = await session.execute(
        select(GeneratedResumeModel)
        .where((GeneratedResumeModel.id == parent_id) | (GeneratedResumeModel.parent_resume_id == parent_id))
        .where(GeneratedResumeModel.user_id == user_id)
    )
    versions = [record.version_number for record in result.scalars().all()]
    return max(versions or [0]) + 1


async def get_resume_model(session: AsyncSession, user_id: uuid.UUID, resume_id: str):
    from app.models.generated_resume import GeneratedResumeModel

    try:
        resume_uuid = uuid.UUID(resume_id)
    except ValueError as exc:
        raise ResumeNotFoundError("Resume not found.") from exc
    result = await session.execute(select(GeneratedResumeModel).where(GeneratedResumeModel.id == resume_uuid))
    record = result.scalar_one_or_none()
    if not record:
        raise ResumeNotFoundError("Resume not found.")
    if record.user_id != user_id:
        raise ResumeOwnershipError("You do not have access to this resume.")
    return record


def record_to_schema(record) -> StructuredResumeRecord:
    resume_json = normalize_structured_resume_bullets(StructuredGeneratedResume.model_validate(record.resume_json))
    return StructuredResumeRecord(
        resumeId=str(record.id),
        userId=str(record.user_id),
        profileId=str(record.profile_id),
        profileVersion=record.profile_version,
        profileContentHash=record.profile_content_hash,
        resumeName=record.resume_name,
        targetJobTitle=record.target_job_title,
        targetCompany=record.target_company or "",
        jobDescription=record.job_description,
        jobAnalysisJson=record.job_analysis_json,
        profileMatchJson=record.profile_match_json,
        resumeJson=resume_json,
        templateId=record.template_id,
        matchScore=record.match_score,
        generationAlgorithmVersion=record.generation_algorithm_version,
        status=record.status,
        versionNumber=record.version_number,
        parentResumeId=str(record.parent_resume_id) if record.parent_resume_id else "",
        createdAt=record.created_at.isoformat(),
        updatedAt=record.updated_at.isoformat(),
    )
