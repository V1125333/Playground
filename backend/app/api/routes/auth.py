from fastapi import APIRouter, Header, HTTPException

from app.schemas.auth import (
    ConfirmTotpRequest,
    ForgotPasswordRequest,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    RegisterResponse,
    ResetPasswordRequest,
    SetupTotpRequest,
)
from app.services import auth_store

router = APIRouter()


@router.post("/register", response_model=RegisterResponse)
async def register(payload: RegisterRequest) -> RegisterResponse:
    try:
        return RegisterResponse(**auth_store.register_user(payload.name, payload.email, payload.password))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/setup-totp", response_model=RegisterResponse)
async def setup_totp(payload: SetupTotpRequest) -> RegisterResponse:
    try:
        return RegisterResponse(**auth_store.setup_totp(payload.email, payload.password))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/confirm-totp")
async def confirm_totp(payload: ConfirmTotpRequest) -> dict[str, str]:
    try:
        auth_store.confirm_totp(payload.email, payload.code)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/login", response_model=LoginResponse)
async def login(payload: LoginRequest) -> LoginResponse:
    try:
        return LoginResponse(**auth_store.login_user(payload.email, payload.password, payload.code))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Account not found.") from exc
    except PermissionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, str]:
    try:
        auth_store.forgot_password(payload.email, payload.code)
        return {"status": "temporary_password_sent_to_super_admin"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict[str, str]:
    try:
        auth_store.reset_password(payload.email, payload.temporary_password, payload.code, payload.new_password)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/me")
async def me(authorization: str = Header(default="")) -> dict:
    token = bearer_token(authorization)
    try:
        return auth_store.user_from_token(token)
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid session.") from exc


@router.get("/admin/temp-passwords")
async def temp_passwords(authorization: str = Header(default="")) -> list[dict]:
    token = bearer_token(authorization)
    try:
        return auth_store.get_temp_passwords(token)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post("/logout")
async def logout() -> dict[str, str]:
    return {"status": "ok"}


def bearer_token(header: str) -> str:
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    return header.removeprefix("Bearer ").strip()
