from pydantic import BaseModel, EmailStr, Field


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


class LoginRequest(BaseModel):
    tenant_id: str | None = Field(default=None, min_length=3, max_length=64)
    email: EmailStr
    # prevent bcrypt crash on long input
    password: str = Field(min_length=1, max_length=72)


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
    reset_token: str = Field(min_length=20, max_length=512)
    code: str = Field(min_length=4, max_length=16)
    new_password: str = Field(min_length=8, max_length=72)


class ResetPasswordResponse(BaseModel):
    ok: bool = True
    message: str
