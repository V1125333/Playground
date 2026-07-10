from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2)
    email: EmailStr
    password: str = Field(min_length=8)


class RegisterResponse(BaseModel):
    email: EmailStr
    otp_uri: str
    qr_data_url: str


class ConfirmTotpRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    code: str = Field(min_length=6, max_length=6)


class SetupTotpRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    token: str
    user: dict


class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)


class ResetPasswordRequest(BaseModel):
    email: EmailStr
    temporary_password: str
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8)
