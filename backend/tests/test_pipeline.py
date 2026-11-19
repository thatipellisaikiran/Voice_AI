"""Tests for VoicePipeline and WebSocket endpoint."""

import base64
import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.services.voice_pipeline import VoicePipeline


class FakeWebSocket:
    def __init__(self):
        self.sent: list[dict] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(json.loads(text))


async def _fake_stream(text: str, session_id: str):
    for tok in ["Hello ", "world!"]:
        yield tok


async def _fake_tts_sentences(text: str, language=None, slow=False):
    yield text, b"FAKE_MP3_BYTES"


class TestVoicePipeline(unittest.IsolatedAsyncioTestCase):
    async def test_process_audio_rejects_short_audio(self):
        pipeline = VoicePipeline()
        ws = FakeWebSocket()

        with patch("app.services.voice_pipeline.validate_audio", new=AsyncMock(return_value=False)):
            await pipeline.process_audio(b"short", "sess-1", ws)

        self.assertEqual(len(ws.sent), 1)
        self.assertEqual(ws.sent[0]["type"], "error")

    async def test_process_audio_full_flow(self):
        pipeline = VoicePipeline()
        ws = FakeWebSocket()

        with (
            patch("app.services.voice_pipeline.validate_audio", new=AsyncMock(return_value=True)),
            patch(
                "app.services.voice_pipeline.stt_service.transcribe",
                new=AsyncMock(return_value={"text": "Hi ARIA", "duration": 1.2}),
            ),
            patch("app.services.voice_pipeline.llm_service.astream_response", side_effect=_fake_stream),
            patch("app.services.voice_pipeline.memory_manager.record_turn", new=AsyncMock()),
            patch("app.services.voice_pipeline.tts_service.synthesize_sentences", side_effect=_fake_tts_sentences),
        ):
            await pipeline.process_audio(b"valid-audio", "sess-1", ws)

        types_sent = [msg["type"] for msg in ws.sent]
        self.assertEqual(types_sent, ["transcript", "llm_token", "llm_token", "audio", "done"])
        self.assertEqual(ws.sent[0]["text"], "Hi ARIA")
        audio_b64 = ws.sent[3]["data"]
        self.assertEqual(base64.b64decode(audio_b64), b"FAKE_MP3_BYTES")

    async def test_process_text_flow(self):
        pipeline = VoicePipeline()
        ws = FakeWebSocket()

        with (
            patch("app.services.voice_pipeline.llm_service.astream_response", side_effect=_fake_stream),
            patch("app.services.voice_pipeline.memory_manager.record_turn", new=AsyncMock()),
            patch("app.services.voice_pipeline.tts_service.synthesize_sentences", side_effect=_fake_tts_sentences),
        ):
            await pipeline.process_text("Hello", "sess-2", ws)

        types_sent = [msg["type"] for msg in ws.sent]
        self.assertEqual(types_sent, ["llm_token", "llm_token", "audio", "done"])

    async def test_process_audio_empty_transcript_sends_error(self):
        pipeline = VoicePipeline()
        ws = FakeWebSocket()

        with (
            patch("app.services.voice_pipeline.validate_audio", new=AsyncMock(return_value=True)),
            patch(
                "app.services.voice_pipeline.stt_service.transcribe",
                new=AsyncMock(return_value={"text": "   ", "duration": 1.0}),
            ),
        ):
            await pipeline.process_audio(b"valid-audio", "sess-3", ws)

        self.assertEqual(len(ws.sent), 1)
        self.assertEqual(ws.sent[0]["type"], "error")

    async def test_process_text_respects_interrupt_and_tts_disabled(self):
        pipeline = VoicePipeline()
        ws = FakeWebSocket()

        async def _interrupting_stream(text: str, session_id: str):
            yield "First "
            pipeline.request_interrupt(session_id)
            yield "Second"

        with patch("app.services.voice_pipeline.llm_service.astream_response", side_effect=_interrupting_stream):
            await pipeline.process_text("Hi", "sess-int", ws)

        self.assertEqual(ws.sent, [{"type": "llm_token", "content": "First "}])

        ws2 = FakeWebSocket()
        with (
            patch("app.services.voice_pipeline.llm_service.astream_response", side_effect=_fake_stream),
            patch("app.services.voice_pipeline.memory_manager.record_turn", new=AsyncMock()),
        ):
            await pipeline.process_text("Hi", "sess-notts", ws2, tts_enabled=False)

        self.assertEqual(
            [m["type"] for m in ws2.sent],
            ["llm_token", "llm_token", "done"],
        )


class TestWebSocketEndpoint(unittest.TestCase):
    def test_websocket_ping_interrupt_and_text(self):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
        from app import database
        from app.main import app

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
            db_path = os.path.join(tmpdir, "ws_test.db")
            test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", echo=False)
            test_session_factory = async_sessionmaker(
                test_engine, class_=AsyncSession, expire_on_commit=False
            )

            with (
                patch.object(database, "engine", test_engine),
                patch.object(database, "AsyncSessionLocal", test_session_factory),
                patch("app.main.stt_service.load_model", new=AsyncMock()),
                patch("app.main.tts_service.load_model", new=AsyncMock()),
                patch("app.main.llm_service.initialize", new=AsyncMock()),
                patch("app.services.voice_pipeline.llm_service.astream_response", side_effect=_fake_stream),
                patch("app.services.voice_pipeline.memory_manager.record_turn", new=AsyncMock()),
                patch("app.services.voice_pipeline.tts_service.synthesize_sentences", side_effect=_fake_tts_sentences),
            ):
                with TestClient(app) as client:
                    with client.websocket_connect("/ws/voice/ws-sess-1") as ws:
                        ws.send_text(json.dumps({"type": "ping"}))
                        self.assertEqual(json.loads(ws.receive_text()), {"type": "pong"})

                        ws.send_text(json.dumps({"type": "interrupt"}))
                        self.assertEqual(json.loads(ws.receive_text()), {"type": "interrupted"})

                        ws.send_text(json.dumps({"type": "text", "content": "Hello ARIA"}))
                        received = []
                        while True:
                            msg = json.loads(ws.receive_text())
                            received.append(msg)
                            if msg["type"] in ("done", "error"):
                                break

                        self.assertEqual(
                            [m["type"] for m in received],
                            ["llm_token", "llm_token", "audio", "done"],
                        )

            import asyncio
            asyncio.run(test_engine.dispose())


if __name__ == "__main__":
    unittest.main()
