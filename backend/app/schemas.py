from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=2, max_length=80)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class ProfileUpdate(BaseModel):
    industry: str = Field(max_length=120)
    job_title: str = Field(max_length=120)
    cefr_level: Literal["A1", "A2", "B1", "B2", "C1", "C2"]
    goals: list[str] = Field(max_length=10)
    preferences: dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    title: str = Field(default="New coaching session", max_length=180)
    mode: Literal["coach", "roleplay", "writing", "diagnostic", "review"] = "coach"


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)


class MemoryUpdate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    enabled: bool = True


class HumanReviewCreate(BaseModel):
    scores: dict[str, float]
    labels: list[str] = Field(default_factory=list)
    comment: str = Field(default="", max_length=4000)


class EvaluationCreate(BaseModel):
    candidate_version: str = Field(default="coach-v1", max_length=40)


class MCPToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = False


class ImprovementCreate(BaseModel):
    proposal_type: Literal["prompt", "routing", "knowledge", "rubric"]
    base_version: str = "coach-v1"
    changes: dict[str, Any]


class ReviewDecision(BaseModel):
    note: str = Field(default="", max_length=2000)


class TraceEventOut(BaseModel):
    sequence: int
    event_type: str
    name: str
    status: str
    duration_ms: int
    payload: dict[str, Any]
    created_at: datetime
