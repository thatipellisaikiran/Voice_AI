"""Tests for STTService."""

import sys
import types
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.stt_service import STTService


class TestSTTService(unittest.IsolatedAsyncioTestCase):
    async def test_transcribe_raises_when_not_loaded(self):
        service = STTService()
        with self.assertRaises(RuntimeError):
            await service.transcribe(b"dummy-audio")

    async def test_load_model_and_transcribe_success(self):
        service = STTService()

        class FakeWhisperModel:
            def __init__(self, model_size, device="cpu", compute_type="int8"):
                self.model_size = model_size
                self.device = device
                self.compute_type = compute_type

            def transcribe(self, wav_path, *args, **kwargs):
                segments = [
                    SimpleNamespace(text="Hello,"),
                    SimpleNamespace(text="how are you?"),
                ]
                info = SimpleNamespace(
                    language="en",
                    language_probability=0.98,
                    duration=2.15,
                )
                return segments, info

        fake_module = types.ModuleType("faster_whisper")
        fake_module.__path__ = []
        fake_module.WhisperModel = FakeWhisperModel
        fake_utils = types.ModuleType("faster_whisper.utils")
        fake_utils.download_model = lambda *args, **kwargs: "dummy-model"

        with patch.dict(sys.modules, {"faster_whisper": fake_module, "faster_whisper.utils": fake_utils}):
            await service.load_model()

        self.assertTrue(service.is_loaded)

        with patch("app.services.stt_service.webm_to_wav_bytes", new=AsyncMock(return_value=b"RIFF....")):
            result = await service.transcribe(b"webm-bytes")

        self.assertEqual(result["text"], "Hello, how are you?")
        self.assertEqual(result["language"], "en")
        self.assertAlmostEqual(result["confidence"], 0.98)
        self.assertAlmostEqual(result["duration"], 2.15)


class TestAudioUtils(unittest.IsolatedAsyncioTestCase):
    async def test_base64_helpers(self):
        from app.utils.audio import base64_to_audio_bytes, mp3_to_base64

        encoded = await mp3_to_base64(b"hello-mp3")
        self.assertEqual(await base64_to_audio_bytes(encoded), b"hello-mp3")
        self.assertEqual(
            await base64_to_audio_bytes(f"data:audio/webm;base64,{encoded}"),
            b"hello-mp3",
        )


if __name__ == "__main__":
    unittest.main()

