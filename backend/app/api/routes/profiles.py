from fastapi import APIRouter, Depends, Header, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.resume import (
    CandidateProfileRecord,
    CreateCandidateProfileRequest,
    UpdateCandidateProfileRequest,
)
from app.services import auth_store, profile_service
from app.services.profile_service import (
    ProfileNotFoundError,
    ProfileOwnershipError,
    ProfileVersionConflictError,
    user_id_from_email,
)

router = APIRouter()


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


@router.post("", response_model=CandidateProfileRecord)
async def create_candidate_profile(
    payload: CreateCandidateProfileRequest,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> CandidateProfileRecord:
    try:
        return await profile_service.create_profile(
            session,
            user_id,
            payload.profile_data,
            payload.profile_name,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not create profile: {exc}") from exc


@router.get("", response_model=list[CandidateProfileRecord])
async def list_candidate_profiles(
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> list[CandidateProfileRecord]:
    return await profile_service.list_profiles_for_user(session, user_id)


@router.get("/primary", response_model=CandidateProfileRecord | None)
async def get_primary_candidate_profile(
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> CandidateProfileRecord | None:
    return await profile_service.get_primary_profile_for_user(session, user_id)


@router.get("/{profile_id}", response_model=CandidateProfileRecord)
async def get_candidate_profile(
    profile_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> CandidateProfileRecord:
    try:
        return await profile_service.get_profile(session, user_id, profile_id)
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{profile_id}", response_model=CandidateProfileRecord)
async def update_candidate_profile(
    profile_id: str,
    payload: UpdateCandidateProfileRequest,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> CandidateProfileRecord:
    try:
        return await profile_service.update_profile(
            session,
            user_id,
            profile_id,
            payload.profile_data,
            payload.profile_name,
            payload.expected_profile_version,
        )
    except ProfileVersionConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": str(exc),
                "currentProfileVersion": exc.current_version,
            },
        ) from exc
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{profile_id}", status_code=204)
async def delete_candidate_profile(
    profile_id: str,
    session: AsyncSession = Depends(db_session),
    user_id=Depends(current_user_id),
) -> Response:
    try:
        await profile_service.delete_profile(session, user_id, profile_id)
    except ProfileOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=204)
