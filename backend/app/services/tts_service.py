"""Ultra-low latency Text-to-Speech service powered by Microsoft Edge Neural TTS.

Provides high-fidelity, real-time audio chunk streaming with sub-200ms latency,
plus automatic fallback to gTTS.
"""

import asyncio
import io
import re
from collections.abc import AsyncIterator

# pyrefly: ignore[missing-import]
import edge_tts
from gtts import gTTS

from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Ultra-natural Microsoft Edge Neural Voices
VOICE_MAP = {
    "en": "en-US-ChristopherNeural",
    "es": "es-ES-AlvaroNeural",
    "fr": "fr-FR-HenriNeural",
    "de": "de-DE-ConradNeural",
    "hi": "hi-IN-MadhurNeural",
    "ja": "ja-JP-KeitaNeural",
}


class TTSService:
    """Real-time Neural TTS service with chunked streaming."""

    def __init__(self) -> None:
        self.is_loaded: bool = False
        self.default_voice = "en-US-ChristopherNeural"

    async def load_model(self) -> None:
        """Mark Edge TTS service ready."""
        self.is_loaded = True
        logger.info("TTS service ready (provider=edge-tts, default_voice=%s).", self.default_voice)

    def _resolve_voice(self, language: str | None = None) -> str:
        lang = (language or settings.tts_language or "en").lower().split("-")[0]
        return VOICE_MAP.get(lang, self.default_voice)

    async def synthesize(
        self,
        text: str,
        language: str | None = None,
        slow: bool = False,
    ) -> bytes:
        """Synthesize text into full MP3 bytes using Edge TTS (with gTTS fallback)."""
        cleaned = text.strip()
        if not cleaned:
            return b""

        voice = self._resolve_voice(language)

        try:
            communicate = edge_tts.Communicate(cleaned, voice)
            audio_buffer = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_buffer.write(chunk["data"])
            audio_buffer.seek(0)
            data = audio_buffer.read()
            if data:
                return data
        except Exception as exc:
            logger.warning("Edge TTS failed for '%s...', falling back to gTTS: %s", cleaned[:30], exc)

        # Fallback to gTTS if Edge TTS encounters network issues
        lang = language or settings.tts_language or "en"
        def _gtts_sync() -> bytes:
            tts = gTTS(text=cleaned, lang=lang, slow=slow)
            buf = io.BytesIO()
            tts.write_to_fp(buf)
            buf.seek(0)
            return buf.read()

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, _gtts_sync)

    async def stream_sentence_audio(
        self,
        text: str,
        language: str | None = None,
    ) -> AsyncIterator[bytes]:
        """Stream raw MP3 audio chunks for a single sentence with minimal latency."""
        cleaned = text.strip()
        if not cleaned:
            return

        voice = self._resolve_voice(language)
        try:
            communicate = edge_tts.Communicate(cleaned, voice)
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    yield chunk["data"]
        except Exception as exc:
            logger.warning("Edge TTS stream failed for '%s...': %s", cleaned[:30], exc)
            fallback_bytes = await self.synthesize(cleaned, language=language)
            if fallback_bytes:
                yield fallback_bytes

    async def synthesize_sentences(
        self,
        text: str,
        language: str | None = None,
        slow: bool = False,
    ) -> AsyncIterator[tuple[str, bytes]]:
        """Yield (sentence, mp3_bytes) tuples split by sentence boundaries."""
        cleaned = text.strip()
        if not cleaned:
            return

        sentences = re.split(r"(?<=[.!?\n])\s+", cleaned)
        for sentence in sentences:
            part = sentence.strip()
            if part:
                mp3_bytes = await self.synthesize(part, language=language, slow=slow)
                if mp3_bytes:
                    yield part, mp3_bytes


tts_service = TTSService()
