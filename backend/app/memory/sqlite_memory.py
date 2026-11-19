"""LangChain SQLite conversation history and ORM message persistence."""

from datetime import datetime, timezone
from typing import Any

from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal
from app.models.db_models import Message, Session


class SessionMemoryManager:
    """Manages per-session LangChain history and SQLAlchemy session/message records."""

    def __init__(self, sync_db_url: str | None = None):
        self.sync_db_url = sync_db_url or settings.sync_db_url

    def get_history(self, session_id: str) -> SQLChatMessageHistory:
        """Return LangChain SQLChatMessageHistory for a session."""
        return SQLChatMessageHistory(
            session_id=session_id,
            connection=self.sync_db_url,
        )

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Return all LangChain messages as a list of {role, content} dicts."""
        history = self.get_history(session_id)
        messages = history.messages
        if settings.max_history_messages > 0:
            messages = messages[-settings.max_history_messages :]
        return [
            {
                "role": "user" if isinstance(m, HumanMessage) else "assistant",
                "content": m.content,
            }
            for m in messages
        ]

    async def clear_session(self, session_id: str) -> None:
        """Delete all LangChain stored messages for a session."""
        history = self.get_history(session_id)
        history.clear()

    async def record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        audio_duration: float | None = None,
        db: AsyncSession | None = None,
    ) -> None:
        """Persist session metadata and user/assistant messages in ORM tables."""
        async def _persist(session_db: AsyncSession) -> None:
            result = await session_db.execute(select(Session).where(Session.id == session_id))
            db_session = result.scalar_one_or_none()
            now = datetime.now(timezone.utc)
            if db_session is None:
                title = user_text.strip()[:60]
                if len(user_text.strip()) > 60:
                    title += "..."
                db_session = Session(
                    id=session_id,
                    title=title or "New Conversation",
                    created_at=now,
                    updated_at=now,
                )
                session_db.add(db_session)
            else:
                if not db_session.title and user_text.strip():
                    title = user_text.strip()[:60]
                    db_session.title = title + ("..." if len(user_text.strip()) > 60 else "")
                db_session.updated_at = now

            session_db.add(
                Message(
                    session_id=session_id,
                    role="user",
                    content=user_text,
                    audio_duration=audio_duration,
                    created_at=now,
                )
            )
            session_db.add(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content=assistant_text,
                    created_at=now,
                )
            )
            await session_db.commit()

        if db is not None:
            await _persist(db)
        else:
            async with AsyncSessionLocal() as session_db:
                await _persist(session_db)


memory_manager = SessionMemoryManager()

