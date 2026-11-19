"""LLM service powered by Groq LLaMA 3.1 and LangChain conversation memory."""

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory

try:
    from langchain_groq import ChatGroq
except Exception:  # pragma: no cover - handles mismatched langchain-groq / pydantic versions
    ChatGroq = None  # type: ignore[assignment]

from app.config import settings
from app.memory.sqlite_memory import memory_manager
from app.utils.logger import get_logger

logger = get_logger(__name__)

SYSTEM_PROMPT = """You are TS, a friendly, intelligent AI voice assistant.
Give concise, natural, conversational responses (2-3 sentences max for voice).
Be warm and engaging — your responses will be spoken aloud."""


class LLMService:
    """Manages Groq LLM client, prompt template, and LangChain SQLite session history."""

    def __init__(self) -> None:
        self.llm: Any = None
        self.chain: Any = None
        self.groq_client: Any = None
        self.is_ready: bool = False

    async def initialize(self) -> None:
        """Initialize ChatGroq + RunnableWithMessageHistory (or AsyncGroq fallback)."""
        api_key = (settings.groq_api_key or "").strip()
        if not api_key or api_key == "gsk_your_key_here":
            logger.warning("GROQ_API_KEY is missing or placeholder; LLM service is not ready.")
            self.is_ready = False
            return

        chat_groq_cls = ChatGroq
        if chat_groq_cls is None:
            try:
                from langchain_groq import ChatGroq as _ChatGroq
                chat_groq_cls = _ChatGroq
            except Exception:
                chat_groq_cls = None

        if chat_groq_cls is not None:
            try:
                self.llm = chat_groq_cls(
                    api_key=api_key,
                    model=settings.groq_model,
                    temperature=0.7,
                    streaming=True,
                    max_tokens=512,
                )

                prompt = ChatPromptTemplate.from_messages(
                    [
                        ("system", SYSTEM_PROMPT),
                        MessagesPlaceholder(variable_name="history"),
                        ("human", "{input}"),
                    ]
                )

                base_chain = prompt | self.llm

                self.chain = RunnableWithMessageHistory(
                    base_chain,
                    get_session_history=memory_manager.get_history,
                    input_messages_key="input",
                    history_messages_key="history",
                )
                self.is_ready = True
                logger.info("LLM service initialized with LangChain ChatGroq ('%s').", settings.groq_model)
                return
            except Exception as exc:
                logger.warning("ChatGroq init failed (%s); falling back to AsyncGroq.", exc)

        try:
            import httpx
            from groq import AsyncGroq

            try:
                self.groq_client = AsyncGroq(api_key=api_key, http_client=httpx.AsyncClient())
            except Exception:
                self.groq_client = AsyncGroq(api_key=api_key)

            self.chain = None
            self.is_ready = True
            logger.info("LLM service initialized successfully ('%s').", settings.groq_model)
        except Exception as exc:
            logger.error("Failed to initialize LLM service: %s", exc)
            self.is_ready = False

    def _build_config(self, session_id: str) -> dict[str, Any]:
        return {"configurable": {"session_id": session_id}}

    def _build_groq_messages(self, session_id: str, user_input: str) -> list[dict[str, str]]:
        history = memory_manager.get_history(session_id)
        msgs: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        recent = history.messages[-settings.max_history_messages :] if settings.max_history_messages > 0 else history.messages
        for m in recent:
            role = "user" if isinstance(m, HumanMessage) else "assistant"
            msgs.append({"role": role, "content": str(m.content)})
        msgs.append({"role": "user", "content": user_input})
        return msgs

    async def astream_response(self, user_input: str, session_id: str) -> AsyncIterator[str]:
        """Stream AI response tokens asynchronously for a given session."""
        if not self.is_ready or (self.chain is None and self.groq_client is None):
            raise RuntimeError("LLM service is not initialized. Check GROQ_API_KEY configuration.")

        if self.chain is not None:
            config = self._build_config(session_id)
            async for chunk in self.chain.astream({"input": user_input}, config=config):
                content = getattr(chunk, "content", None)
                if content:
                    yield content
            return

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
        history = memory_manager.get_history(session_id)
        history.add_message(HumanMessage(content=user_input))
        history.add_message(AIMessage(content=full_reply))

    async def get_response(self, user_input: str, session_id: str) -> str:
        """Return a complete AI response string for REST /api/chat."""
        if not self.is_ready or (self.chain is None and self.groq_client is None):
            raise RuntimeError("LLM service is not initialized. Check GROQ_API_KEY configuration.")

        if self.chain is not None:
            config = self._build_config(session_id)
            result = await self.chain.ainvoke({"input": user_input}, config=config)
            return getattr(result, "content", str(result))

        messages = self._build_groq_messages(session_id, user_input)
        completion = await self.groq_client.chat.completions.create(
            model=settings.groq_model,
            messages=messages,
            temperature=0.7,
            max_tokens=512,
            stream=False,
        )
        reply = completion.choices[0].message.content or ""
        history = memory_manager.get_history(session_id)
        history.add_message(HumanMessage(content=user_input))
        history.add_message(AIMessage(content=reply))
        return reply


llm_service = LLMService()
