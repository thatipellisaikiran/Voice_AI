"""Tests for LLMService and REST endpoints."""

import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.config import settings
from app.services.llm_service import LLMService


class TestLLMService(unittest.IsolatedAsyncioTestCase):
    async def test_initialize_without_api_key_sets_not_ready(self):
        service = LLMService()
        with patch.object(settings, "gemini_api_key", ""), patch.object(settings, "groq_api_key", ""):
            await service.initialize()
        self.assertFalse(service.is_ready)

    async def test_initialize_with_gemini_key_sets_ready(self):
        service = LLMService()
        with patch.object(settings, "gemini_api_key", "AQ.test_key"), patch.object(settings, "gemini_model", "gemini-2.0-flash"):
            await service.initialize()
        self.assertTrue(service.is_ready)
        self.assertEqual(service.provider, "gemini")


class TestRestEndpoints(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = os.path.join(self.tmpdir.name, "test.db")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_health_chat_and_sessions_flow(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from app import database
        from app.main import app
        from app.memory.sqlite_memory import memory_manager

        test_engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}", echo=False)
        test_session_factory = async_sessionmaker(
            test_engine, class_=AsyncSession, expire_on_commit=False
        )

        async def _override_get_db():
            async with test_session_factory() as s:
                yield s

        app.dependency_overrides[database.get_db] = _override_get_db

        with (
            patch.object(database, "engine", test_engine),
            patch.object(database, "AsyncSessionLocal", test_session_factory),
            patch.object(memory_manager, "sync_db_url", f"sqlite:///{self.db_path}"),
            patch("app.main.stt_service.load_model", new=AsyncMock()),
            patch("app.main.tts_service.load_model", new=AsyncMock()),
            patch("app.main.llm_service.initialize", new=AsyncMock()),
            patch("app.api.routes.chat.llm_service.get_response", new=AsyncMock(return_value="Paris is the capital.")),
        ):
            with TestClient(app) as client:
                health = client.get("/health")
                self.assertEqual(health.status_code, 200)
                self.assertIn("services", health.json())

                chat_res = client.post(
                    "/api/chat",
                    json={"session_id": "test-sess", "message": "Capital of France?"},
                )
                self.assertEqual(chat_res.status_code, 200)
                data = chat_res.json()
                self.assertEqual(data["session_id"], "test-sess")
                self.assertEqual(data["response"], "Paris is the capital.")

                sessions_res = client.get("/api/sessions")
                self.assertEqual(sessions_res.status_code, 200)
                sessions = sessions_res.json()
                self.assertEqual(len(sessions), 1)
                self.assertEqual(sessions[0]["id"], "test-sess")
                self.assertEqual(sessions[0]["message_count"], 2)

                history_res = client.get("/api/sessions/test-sess/history")
                self.assertEqual(history_res.status_code, 200)
                messages = history_res.json()["messages"]
                self.assertEqual(len(messages), 2)
                self.assertEqual(messages[0]["role"], "user")
                self.assertEqual(messages[1]["role"], "assistant")

                del_res = client.delete("/api/sessions/test-sess")
                self.assertEqual(del_res.status_code, 200)
                self.assertEqual(del_res.json(), {"message": "deleted"})

                sessions_after = client.get("/api/sessions")
                self.assertEqual(sessions_after.json(), [])

        asyncio.run(test_engine.dispose())
        app.dependency_overrides.clear()


if __name__ == "__main__":
    unittest.main()
