"""SQLAlchemy ORM table definitions stored in SQLite."""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Session(Base):
    """Conversation session metadata."""

    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)
    updated_at = Column(DateTime(timezone=True), default=_utc_now, onupdate=_utc_now)

    messages = relationship(
        "Message",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )


class Message(Base):
    """Individual user or assistant message within a session."""

    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=lambda: str(uuid4()))
    session_id = Column(String, ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    audio_duration = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now)

    session = relationship("Session", back_populates="messages")

