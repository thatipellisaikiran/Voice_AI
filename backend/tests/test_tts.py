"""Tests for TTSService."""

import unittest
from unittest.mock import patch

from app.services.tts_service import TTSService


class FakeGTTS:
    def __init__(self, text, lang="en", slow=False):
        self.text = text
        self.lang = lang
        self.slow = slow

    def write_to_fp(self, fp):
        fp.write(f"MP3:{self.text}".encode("utf-8"))


class TestTTSService(unittest.IsolatedAsyncioTestCase):
    async def test_synthesize_empty_returns_empty_bytes(self):
        service = TTSService()
        await service.load_model()
        self.assertTrue(service.is_loaded)
        self.assertEqual(await service.synthesize("   "), b"")

    async def test_synthesize_and_sentences(self):
        service = TTSService()
        await service.load_model()

        with patch("app.services.tts_service.gTTS", FakeGTTS):
            mp3 = await service.synthesize("Hello world.")
            self.assertEqual(mp3, b"MP3:Hello world.")

            chunks = []
            async for sentence, audio in service.synthesize_sentences(
                "First sentence. Second sentence! Third?"
            ):
                chunks.append((sentence, audio))

        self.assertEqual(len(chunks), 3)
        self.assertEqual(chunks[0][0], "First sentence.")
        self.assertEqual(chunks[1][0], "Second sentence!")
        self.assertEqual(chunks[2][0], "Third?")


if __name__ == "__main__":
    unittest.main()

