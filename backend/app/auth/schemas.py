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
    tenant_id: str
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


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=20)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=20)
