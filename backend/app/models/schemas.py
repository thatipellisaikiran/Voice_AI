"""Pydantic request and response schemas."""

from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ChatRequest(BaseModel):
    """Request body for POST /api/chat."""

    session_id: str | None = None
    message: str = Field(..., min_length=1, description="User's text message")


class ChatResponse(BaseModel):
    """Response body for POST /api/chat."""

    session_id: str
    message: str
    response: str
    timestamp: datetime


class MessageSchema(BaseModel):
    """Serialized conversation message."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    role: str
    content: str
    audio_duration: float | None = None
    created_at: datetime


class SessionInfo(BaseModel):
    """Session summary item for GET /api/sessions."""

    id: str
    title: str | None = None
    message_count: int
    created_at: datetime
    updated_at: datetime


class HistoryResponse(BaseModel):
    """Full conversation history for GET /api/sessions/{id}/history."""

    session_id: str
    messages: list[MessageSchema]


class HealthResponse(BaseModel):
    """Response schema for GET /health."""

    status: str  # "healthy" | "degraded"
    services: dict[str, str]
    version: str
    uptime: float

