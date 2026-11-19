"""Health check endpoint."""

import time

from fastapi import APIRouter

from app.config import settings
from app.models.schemas import HealthResponse
from app.services.llm_service import llm_service
from app.services.stt_service import stt_service
from app.services.tts_service import tts_service

router = APIRouter(tags=["Health"])

_START_TIME = time.monotonic()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Return service readiness and server uptime."""
    services = {
        "stt": "ready" if stt_service.is_loaded else "unavailable",
        "llm": "ready" if llm_service.is_ready else "unavailable",
        "tts": "ready" if tts_service.is_loaded else "unavailable",
    }
    overall_status = "healthy" if all(state == "ready" for state in services.values()) else "degraded"
    return HealthResponse(
        status=overall_status,
        services=services,
        version=settings.app_version,
        uptime=round(time.monotonic() - _START_TIME, 2),
    )

