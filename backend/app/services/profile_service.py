from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import CandidateProfile, CandidateProfileRecord

if TYPE_CHECKING:
    from app.models.candidate_profile import CandidateProfileModel


DEFAULT_PROFILE_NAME = "Primary Profile"
PROFILE_SCHEMA_VERSION = 1


class ProfileNotFoundError(Exception):
    pass


class ProfileOwnershipError(Exception):
    pass


class ProfileVersionConflictError(Exception):
    def __init__(self, current_version: int) -> None:
        self.current_version = current_version
        super().__init__("This profile was updated elsewhere. Reload before saving.")


def user_id_from_email(email: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"jobyro:user:{email.lower().strip()}")


def ensure_profile_record_ids(profile: CandidateProfile) -> CandidateProfile:
    data = profile.model_dump(mode="json", by_alias=True)
    for collection_key, id_key, prefix, label_keys in (
        ("experience", "experienceId", "experience", ("company", "role", "startDate")),
        ("projects", "projectId", "project", ("name", "org")),
        ("education", "educationId", "education", ("degree", "institution", "gradYear")),
        ("certifications", "certificationId", "certification", ("name", "issuer", "issuedDate")),
    ):
        for item in data.get(collection_key, []):
            if not item.get(id_key):
                basis = "|".join(str(item.get(key, "")) for key in label_keys).strip("|")
                item[id_key] = stable_id(prefix, basis or json.dumps(item, sort_keys=True))
    return CandidateProfile.model_validate(data)


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def normalized_profile_payload(profile: CandidateProfile) -> dict:
    stable = ensure_profile_record_ids(profile)
    data = stable.model_dump(mode="json", by_alias=True)
    return normalize_json(data)


def normalize_json(value):
    if isinstance(value, dict):
        return {key: normalize_json(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [normalize_json(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value.strip())
    return value


def compute_profile_content_hash(profile: CandidateProfile) -> str:
    raw = json.dumps(normalized_profile_payload(profile), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def calculate_profile_completeness(profile: CandidateProfile) -> int:
    score = 0
    contact = profile.contact
    identity_fields = [profile.name, contact.email, contact.phone, contact.location]
    if any(field.strip() for field in identity_fields):
        score += round(15 * filled_ratio(identity_fields))

    if profile.title.strip():
        score += 5
    if profile.summary.strip():
        score += 5

    skills = [skill for group in profile.skills for skill in group.items if skill.strip()]
    if skills:
        score += 15

    experiences = [item for item in profile.experience if item.company.strip() or item.role.strip()]
    if experiences:
        score += 25

    has_work_detail = any(item.raw_notes.strip() or item.bullets or item.metric_flags for item in profile.experience)
    if has_work_detail:
        score += 10

    if any(item.degree.strip() or item.institution.strip() for item in profile.education):
        score += 10

    if any(item.name.strip() for item in profile.projects):
        score += 5

    if any(item.name.strip() for item in profile.certifications):
        score += 5

    if any(value.strip() for value in (contact.linkedin, contact.github, contact.portfolio)):
        score += 5

    return max(0, min(100, score))


def filled_ratio(values: list[str]) -> float:
    if not values:
        return 0
    return sum(1 for value in values if value.strip()) / len(values)


async def create_profile(
    session: AsyncSession,
    user_id: uuid.UUID,
    profile: CandidateProfile,
    profile_name: str = DEFAULT_PROFILE_NAME,
) -> CandidateProfileRecord:
    from app.models.candidate_profile import CandidateProfileModel

    stable_profile = ensure_profile_record_ids(profile)
    content_hash = compute_profile_content_hash(stable_profile)
    record = CandidateProfileModel(
        user_id=user_id,
        profile_name=profile_name or DEFAULT_PROFILE_NAME,
        profile_data=stable_profile.model_dump(mode="json", by_alias=True),
        schema_version=PROFILE_SCHEMA_VERSION,
        profile_version=1,
        completeness_score=calculate_profile_completeness(stable_profile),
        content_hash=content_hash,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return profile_record_to_schema(record)


async def list_profiles_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[CandidateProfileRecord]:
    from app.models.candidate_profile import CandidateProfileModel

    result = await session.execute(
        select(CandidateProfileModel)
        .where(CandidateProfileModel.user_id == user_id)
        .order_by(CandidateProfileModel.updated_at.desc())
    )
    return [profile_record_to_schema(record) for record in result.scalars().all()]


async def get_primary_profile_for_user(session: AsyncSession, user_id: uuid.UUID) -> CandidateProfileRecord | None:
    from app.models.candidate_profile import CandidateProfileModel

    result = await session.execute(
        select(CandidateProfileModel)
        .where(CandidateProfileModel.user_id == user_id)
        .order_by(CandidateProfileModel.updated_at.desc())
        .limit(1)
    )
    record = result.scalar_one_or_none()
    return profile_record_to_schema(record) if record else None


async def get_profile(session: AsyncSession, user_id: uuid.UUID, profile_id: str) -> CandidateProfileRecord:
    record = await get_profile_model(session, user_id, profile_id)
    return profile_record_to_schema(record)


async def update_profile(
    session: AsyncSession,
    user_id: uuid.UUID,
    profile_id: str,
    profile: CandidateProfile,
    profile_name: str | None = None,
    expected_profile_version: int | None = None,
) -> CandidateProfileRecord:
    record = await get_profile_model(session, user_id, profile_id)
    if expected_profile_version is not None and record.profile_version != expected_profile_version:
        raise ProfileVersionConflictError(record.profile_version)

    stable_profile = ensure_profile_record_ids(profile)
    next_hash = compute_profile_content_hash(stable_profile)
    if next_hash != record.content_hash:
        record.profile_version += 1
        record.profile_data = stable_profile.model_dump(mode="json", by_alias=True)
        record.content_hash = next_hash
        record.completeness_score = calculate_profile_completeness(stable_profile)
        record.updated_at = datetime.now(timezone.utc)
    if profile_name is not None and profile_name.strip() and profile_name != record.profile_name:
        record.profile_name = profile_name.strip()
        record.updated_at = datetime.now(timezone.utc)

    await session.commit()
    await session.refresh(record)
    return profile_record_to_schema(record)


async def delete_profile(session: AsyncSession, user_id: uuid.UUID, profile_id: str) -> None:
    record = await get_profile_model(session, user_id, profile_id)
    # Future referential checks for saved resumes/applications should happen here before deletion.
    await session.delete(record)
    await session.commit()


async def get_profile_model(session: AsyncSession, user_id: uuid.UUID, profile_id: str) -> CandidateProfileModel:
    from app.models.candidate_profile import CandidateProfileModel

    try:
        profile_uuid = uuid.UUID(profile_id)
    except ValueError as exc:
        raise ProfileNotFoundError("Profile not found.") from exc
    result = await session.execute(select(CandidateProfileModel).where(CandidateProfileModel.id == profile_uuid))
    record = result.scalar_one_or_none()
    if not record:
        raise ProfileNotFoundError("Profile not found.")
    if record.user_id != user_id:
        raise ProfileOwnershipError("You do not have access to this profile.")
    return record


def profile_record_to_schema(record) -> CandidateProfileRecord:
    profile = CandidateProfile.model_validate(record.profile_data)
    return CandidateProfileRecord(
        profileId=str(record.id),
        userId=str(record.user_id),
        profileName=record.profile_name,
        profileData=profile,
        schemaVersion=record.schema_version,
        profileVersion=record.profile_version,
        completenessScore=record.completeness_score,
        contentHash=record.content_hash,
        createdAt=to_iso(record.created_at),
        updatedAt=to_iso(record.updated_at),
    )


def to_iso(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
