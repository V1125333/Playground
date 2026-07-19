from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import (
    ExperienceBulletInspection,
    ExperienceOverview,
    ExperienceRoleInspection,
    ExcludedSkillInspection,
    RequirementCoverageInspection,
    ResumeIntelligenceInspection,
    SkillsOverview,
    SkillInspection,
    SummaryInspection,
)
from app.services import auth_store, profile_service
from app.services.profile_service import ProfileNotFoundError, ProfileOwnershipError, user_id_from_email
from app.services.resume_intelligence_inspector import (
    inspect_excluded_skill,
    inspect_experience_bullet,
    inspect_experience_role,
    inspect_requirement_coverage,
    inspect_resume_intelligence_package,
    inspect_skill,
    inspect_summary,
)
from app.services.resume_intelligence_store import (
    ResumeIntelligencePackageNotFoundError,
    ResumeIntelligencePackageOwnershipError,
    get_resume_intelligence_package,
)


router = APIRouter()
logger = logging.getLogger(__name__)


async def db_session():
    from app.core.database import get_session

    async for session in get_session():
        yield session


def current_user_id(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        user = auth_store.user_from_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session.") from exc
    return user_id_from_email(user["email"])


async def _load_package_and_profile(session: AsyncSession, user_id, package_id: str):
    try:
        package = await get_resume_intelligence_package(session, user_id, package_id)
    except ResumeIntelligencePackageOwnershipError as exc:
        raise HTTPException(status_code=404, detail="Resume intelligence package not found.") from exc
    except ResumeIntelligencePackageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    profile_record = None
    try:
        profile_record = await profile_service.get_profile(session, user_id, str(package.profile_id))
    except (ProfileNotFoundError, ProfileOwnershipError):
        profile_record = None
    return package, profile_record


@router.get("/{package_id}/inspect", response_model=ResumeIntelligenceInspection)
async def inspect_package(
    package_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> ResumeIntelligenceInspection:
    started = time.perf_counter()
    package, profile_record = await _load_package_and_profile(session, user_id, package_id)
    inspection = inspect_resume_intelligence_package(package, profile_record)
    logger.info(
        "resume_intelligence_inspected",
        extra={
            "package_id": package_id,
            "user_id": str(user_id),
            "section": "inspect",
            "stale": inspection.stale,
            "warning_count": inspection.metrics.warning_count,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        },
    )
    return inspection


@router.get("/{package_id}/summary", response_model=SummaryInspection)
async def inspect_package_summary(
    package_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> SummaryInspection:
    package, _profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_summary(package)


@router.get("/{package_id}/experiences", response_model=ExperienceOverview)
async def inspect_package_experiences(
    package_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> ExperienceOverview:
    package, profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_resume_intelligence_package(package, profile_record).experience_overview


@router.get("/{package_id}/experiences/{experience_id}", response_model=ExperienceRoleInspection)
async def inspect_package_experience(
    package_id: str,
    experience_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> ExperienceRoleInspection:
    package, _profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_experience_role(package, experience_id)


@router.get("/{package_id}/experiences/{experience_id}/bullets/{bullet_id}", response_model=ExperienceBulletInspection)
async def inspect_package_experience_bullet(
    package_id: str,
    experience_id: str,
    bullet_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> ExperienceBulletInspection:
    package, _profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_experience_bullet(package, experience_id, bullet_id)


@router.get("/{package_id}/skills", response_model=SkillsOverview)
async def inspect_package_skills(
    package_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> SkillsOverview:
    package, profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_resume_intelligence_package(package, profile_record).skills_overview


@router.get("/{package_id}/skills/{skill_id}", response_model=SkillInspection | ExcludedSkillInspection)
async def inspect_package_skill(
    package_id: str,
    skill_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
):
    package, _profile_record = await _load_package_and_profile(session, user_id, package_id)
    if skill_id.startswith("requirement-"):
        return inspect_excluded_skill(package, skill_id.removeprefix("requirement-"))
    return inspect_skill(package, skill_id)


@router.get("/{package_id}/requirements", response_model=list[RequirementCoverageInspection])
async def inspect_package_requirements(
    package_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> list[RequirementCoverageInspection]:
    package, profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_resume_intelligence_package(package, profile_record).requirement_coverage


@router.get("/{package_id}/requirements/{requirement_id}", response_model=RequirementCoverageInspection)
async def inspect_package_requirement(
    package_id: str,
    requirement_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> RequirementCoverageInspection:
    package, _profile_record = await _load_package_and_profile(session, user_id, package_id)
    return inspect_requirement_coverage(package, requirement_id)
