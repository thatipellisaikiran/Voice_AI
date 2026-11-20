"""LLM service powered by Google Gemini (gemini-2.0-flash) with fallback support."""

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
from langchain_core.messages import AIMessage, HumanMessage

from app.config import settings
from app.memory.sqlite_memory import memory_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are TS, a friendly, intelligent AI voice assistant.
Respond conversationally, concisely, and directly (1-2 short sentences max for voice).
Never use markdown headers or lengthy lists. Your response is spoken aloud immediately."""


def _resolve_gemini_model(model: str) -> str:
    """Resolve model name, automatically mapping deprecated aliases."""
    raw = (model or "").strip()
    if raw in ("gemini-2.0-flash", "gemini-2.0-flash-exp"):
        return "gemini-2.5-flash"
    return raw or "gemini-2.5-flash"


class LLMService:
    """Manages Google Gemini and Groq LLM clients and persistent conversation memory."""

    def __init__(self) -> None:
        self.provider: str = "gemini"
        self.gemini_key: str = ""
        self.gemini_model: str = "gemini-2.5-flash"
        self.groq_client: Any = None
        self.is_ready: bool = False

    async def initialize(self) -> None:
        """Initialize LLM service with Google Gemini or Groq fallback."""
        gemini_key = (settings.gemini_api_key or "").strip()
        groq_key = (settings.groq_api_key or "").strip()

        if gemini_key and gemini_key != "your_gemini_api_key_here":
            self.provider = "gemini"
            self.gemini_key = gemini_key
            self.gemini_model = _resolve_gemini_model(settings.gemini_model)
            self.is_ready = True
            logger.info(
                "LLM service initialized successfully with Google Gemini (configured='%s', active='%s').",
                settings.gemini_model,
                self.gemini_model,
            )
            return

        if groq_key and groq_key != "gsk_your_key_here":
            self.provider = "groq"
            try:
                from groq import AsyncGroq
                try:
                    self.groq_client = AsyncGroq(api_key=groq_key, http_client=httpx.AsyncClient())
                except Exception:
                    self.groq_client = AsyncGroq(api_key=groq_key)
                self.is_ready = True
                logger.info("LLM service initialized successfully with AsyncGroq ('%s').", settings.groq_model)
                return
            except Exception as exc:
                logger.error("Failed to initialize Groq LLM service: %s", exc)

        logger.warning("No valid GEMINI_API_KEY or GROQ_API_KEY found; LLM service is not ready.")
        self.is_ready = False

    def _build_gemini_payload(self, session_id: str, user_input: str) -> dict[str, Any]:
        """Construct Google Generative Language multi-turn contents payload."""
        contents: list[dict[str, Any]] = []
        try:
            history = memory_manager.get_history(session_id)
            recent = (
                history.messages[-settings.max_history_messages :]
                if settings.max_history_messages > 0
                else history.messages
            )
            for m in recent:
                role = "user" if isinstance(m, HumanMessage) else "model"
                contents.append({"role": role, "parts": [{"text": str(m.content)}]})
        except Exception as exc:
            logger.warning("Could not read message history for session %s: %s", session_id, exc)

        contents.append({"role": "user", "parts": [{"text": user_input}]})

        return {
            "system_instruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": contents,
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 512,
            },
        }

    def _build_groq_messages(self, session_id: str, user_input: str) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        try:
            history = memory_manager.get_history(session_id)
            recent = (
                history.messages[-settings.max_history_messages :]
                if settings.max_history_messages > 0
                else history.messages
            )
            for m in recent:
                role = "user" if isinstance(m, HumanMessage) else "assistant"
                msgs.append({"role": role, "content": str(m.content)})
        except Exception as exc:
            logger.warning("Could not read message history for session %s: %s", session_id, exc)

        msgs.append({"role": "user", "content": user_input})
        return msgs

    async def astream_response(self, user_input: str, session_id: str) -> AsyncIterator[str]:
        """Stream AI response tokens asynchronously for a given session."""
        if not self.is_ready:
            raise RuntimeError("LLM service is not initialized. Check GEMINI_API_KEY configuration.")

        chunks: list[str] = []

        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:streamGenerateContent?alt=sse&key={self.gemini_key}"
            payload = self._build_gemini_payload(session_id, user_input)

            async with httpx.AsyncClient(timeout=20.0) as client:
                async with client.stream("POST", url, json=payload) as resp:
                    if resp.status_code != 200:
                        error_body = await resp.aread()
                        logger.error("Gemini stream error (%s): %s", resp.status_code, error_body.decode(errors="ignore"))
                        raise RuntimeError(f"Gemini API returned status {resp.status_code}")

                    async for line in resp.aiter_lines():
                        if line.startswith("data:"):
                            raw = line[5:].strip()
                            if not raw:
                                continue
                            try:
                                chunk = json.loads(raw)
                                parts = chunk.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                                for p in parts:
                                    delta = p.get("text", "")
                                    if delta:
                                        chunks.append(delta)
                                        yield delta
                            except Exception:
                                continue
        else:
            messages = self._build_groq_messages(session_id, user_input)
            stream = await self.groq_client.chat.completions.create(
                model=settings.groq_model,
                messages=messages,
                temperature=0.7,
                max_tokens=512,
                stream=True,
            )
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
        if not self.is_ready:
            raise RuntimeError("LLM service is not initialized. Check GEMINI_API_KEY configuration.")

        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.gemini_model}:generateContent?key={self.gemini_key}"
            payload = self._build_gemini_payload(session_id, user_input)

            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code != 200:
                    logger.error("Gemini error (%s): %s", resp.status_code, resp.text)
                    raise RuntimeError(f"Gemini API returned status {resp.status_code}")
                data = resp.json()
                reply = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        else:
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
