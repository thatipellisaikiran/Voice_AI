"""REST chat endpoint (text-only fallback)."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.memory.sqlite_memory import memory_manager
from app.models.schemas import ChatRequest, ChatResponse
from app.services.llm_service import llm_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Chat"])


@router.post("/chat", response_model=ChatResponse)
async def text_chat(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    """Process a text-only chat turn and persist conversation history."""
    session_id = request.session_id or str(uuid4())
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="Message cannot be empty.")

    try:
        response_text = await llm_service.get_response(user_message, session_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Chat error for session=%s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail=f"LLM request failed: {exc}") from exc

    await memory_manager.record_turn(
        session_id=session_id,
        user_text=user_message,
        assistant_text=response_text,
        db=db,
    )

    return ChatResponse(
        session_id=session_id,
        message=user_message,
        response=response_text,
        timestamp=datetime.now(timezone.utc),
    )

