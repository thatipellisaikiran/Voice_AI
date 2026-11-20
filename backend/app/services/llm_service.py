"""LLM service powered by native AsyncGroq for high-throughput, low-latency streaming."""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings
from app.memory.sqlite_memory import memory_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are TS, a friendly, intelligent AI voice assistant.
Respond conversationally, concisely, and directly (1-2 short sentences max for voice).
Never use markdown headers or lengthy lists. Your response is spoken aloud immediately."""


class LLMService:
    """Manages Groq LLM client and persistent conversation memory."""

    def __init__(self) -> None:
        self.groq_client: Any = None
        self.is_ready: bool = False

    async def initialize(self) -> None:
        """Initialize native AsyncGroq streaming client."""
        api_key = (settings.groq_api_key or "").strip()
        if not api_key or api_key == "gsk_your_key_here":
            logger.warning("GROQ_API_KEY is missing or placeholder; LLM service is not ready.")
            self.is_ready = False
            return

        try:
            import httpx
            from groq import AsyncGroq

            try:
                self.groq_client = AsyncGroq(api_key=api_key, http_client=httpx.AsyncClient())
            except Exception:
                self.groq_client = AsyncGroq(api_key=api_key)

            self.is_ready = True
            logger.info("LLM service initialized successfully with AsyncGroq ('%s').", settings.groq_model)
        except Exception as exc:
            logger.error("Failed to initialize LLM service: %s", exc)
            self.is_ready = False

    def _build_groq_messages(self, session_id: str, user_input: str) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        try:
            history = memory_manager.get_history(session_id)
            recent = history.messages[-settings.max_history_messages :] if settings.max_history_messages > 0 else history.messages
            for m in recent:
                role = "user" if isinstance(m, HumanMessage) else "assistant"
                msgs.append({"role": role, "content": str(m.content)})
        except Exception as exc:
            logger.warning("Could not read message history for session %s: %s", session_id, exc)

        msgs.append({"role": "user", "content": user_input})
        return msgs

    async def astream_response(self, user_input: str, session_id: str) -> AsyncIterator[str]:
        """Stream AI response tokens asynchronously for a given session."""
        if not self.is_ready or self.groq_client is None:
            raise RuntimeError("LLM service is not initialized. Check GROQ_API_KEY configuration.")

        messages = self._build_groq_messages(session_id, user_input)
        stream = await self.groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
            stream=True,
        )
        chunks: list[str] = []
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                chunks.append(delta)
                yield delta

        full_reply = "".join(chunks)
        try:
            history = memory_manager.get_history(session_id)
            history.add_message(HumanMessage(content=user_input))
            history.add_message(AIMessage(content=full_reply))
        except Exception as exc:
            logger.warning("Could not persist message history for session %s: %s", session_id, exc)

    async def get_response(self, user_input: str, session_id: str) -> str:
        """Return a complete AI response string for REST /api/chat."""
        if not self.is_ready or self.groq_client is None:
            raise RuntimeError("LLM service is not initialized. Check GROQ_API_KEY configuration.")

        messages = self._build_groq_messages(session_id, user_input)
        completion = await self.groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
            stream=False,
        )
        reply = completion.choices[0].message.content or ""
        try:
            history = memory_manager.get_history(session_id)
            history.add_message(HumanMessage(content=user_input))
            history.add_message(AIMessage(content=reply))
        except Exception as exc:
            logger.warning("Could not persist message history for session %s: %s", session_id, exc)
        return reply


llm_service = LLMService()
