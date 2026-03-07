from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.password_policy import validate_password_input


class RegisterRequest(BaseModel):
    id: str = Field(min_length=3, max_length=64)
    tenant_id: str = Field(min_length=3, max_length=64)
    email: EmailStr
    # bcrypt hard limit = 72 bytes
    password: str = Field(min_length=8, max_length=72)
    role: str = Field(
        default="admin",
        description="owner | admin | editor | viewer"
    )

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password_input(value)


class LoginRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3, max_length=64)
    email: EmailStr
    # prevent bcrypt crash on long input
    password: str = Field(min_length=1, max_length=72)

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        return validate_password_input(value)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str = "bearer"


class MeResponse(BaseModel):
    id: str
    tenant_id: str
    email: EmailStr
    role: str


class UserPreferenceResponse(BaseModel):
    user_id: str
    tenant_id: str
    preferred_name: str | None = None
    timezone: str | None = None
    bot_name: str | None = None
    profile_image_data: str | None = None


class UserPreferenceUpdateRequest(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=120)
    timezone: str | None = Field(default=None, max_length=64)
    bot_name: str | None = Field(default=None, max_length=255)


class ProfileImageUploadResponse(BaseModel):
    ok: bool = True
    user_id: str
    tenant_id: str
    profile_image_data: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class ForgotPasswordRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3, max_length=64)
    email: EmailStr


class ForgotPasswordResponse(BaseModel):
    ok: bool = True
    message: str


class ResetPasswordRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3, max_length=64)
    email: EmailStr | None = None
    reset_token: str | None = Field(default=None, min_length=20, max_length=512)
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _validate_new_password(cls, value: str) -> str:
        return validate_password_input(value)


class ResetPasswordResponse(BaseModel):
    ok: bool = True
    message: str


class DeleteAccountResponse(BaseModel):
    ok: bool = True
    message: str
