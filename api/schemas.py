"""Pydantic request/response schemas for REST API."""
from pydantic import BaseModel, Field


# Auth
class AuthGoogleRequest(BaseModel):
    idToken: str | None = Field(None, alias="idToken")
    id_token: str | None = None


class AuthAppleRequest(BaseModel):
    identityToken: str | None = Field(None, alias="identityToken")
    identity_token: str | None = None
    email: str | None = None
    fullName: str | dict | None = None


class AuthRegisterRequest(BaseModel):
    email: str
    password: str = Field(..., min_length=6)
    first_name: str | None = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str


# User
class UserMeResponse(BaseModel):
    user_id: int
    first_name: str | None
    memories_count: int
    is_premium: bool
    premium_until: str | None
    chapters: list[dict]


class UserPatchRequest(BaseModel):
    first_name: str | None = None


# Chapters
class ChapterCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    period_hint: str | None = None


class ChapterRenameRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class ChaptersReorderRequest(BaseModel):
    chapter_id_a: int
    chapter_id_b: int


# Memories
class MemoryTextRequest(BaseModel):
    text: str = Field(..., min_length=1)


class MemoryCorrectRequest(BaseModel):
    instruction: str = Field(..., min_length=1)


class MemorySaveRequest(BaseModel):
    chapter_id: int | None = None


class MemoryMoveRequest(BaseModel):
    chapter_id: int


# Subscription
class PromoRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
