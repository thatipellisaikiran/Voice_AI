"""Session management REST endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.memory.sqlite_memory import memory_manager
from app.models.db_models import Message, Session
from app.models.schemas import HistoryResponse, MessageSchema, SessionInfo

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


@router.get("", response_model=list[SessionInfo])
async def list_sessions(db: AsyncSession = Depends(get_db)) -> list[SessionInfo]:
    """List all conversation sessions ordered by most recently updated."""
    stmt = (
        select(
            Session.id,
            Session.title,
            Session.created_at,
            Session.updated_at,
            func.count(Message.id).label("message_count"),
        )
        .outerjoin(Message, Session.id == Message.session_id)
        .group_by(Session.id)
        .order_by(Session.updated_at.desc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        SessionInfo(
            id=row.id,
            title=row.title,
            message_count=row.message_count or 0,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get("/{session_id}/history", response_model=HistoryResponse)
async def get_session_history(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> HistoryResponse:
    """Retrieve all messages for a specific session."""
    session_obj = await db.get(Session, session_id)
    if session_obj is None:
        return HistoryResponse(session_id=session_id, messages=[])

    stmt = (
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = (await db.execute(stmt)).scalars().all()
    return HistoryResponse(
        session_id=session_id,
        messages=[MessageSchema.model_validate(msg) for msg in messages],
    )


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete a session, its ORM messages, and its LangChain memory."""
    session_obj = await db.get(Session, session_id)
    if session_obj is not None:
        await db.delete(session_obj)
        await db.commit()

    try:
        await memory_manager.clear_session(session_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to clear memory: {exc}") from exc

    return {"message": "deleted"}

