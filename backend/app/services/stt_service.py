"""Speech-to-Text service powered by faster-whisper (local, free)."""

import asyncio
import os
import re
import tempfile
from collections import Counter
from typing import Any

from app.config import settings
from app.utils.audio import webm_to_wav_bytes
from app.utils.logger import get_logger

logger = get_logger(__name__)


class STTService:
    """Transcribes audio bytes to text dynamically using faster-whisper."""

    def __init__(self) -> None:
        self.model: Any = None
        self.is_loaded: bool = False

    async def load_model(self) -> None:
        """Load the Whisper model in a thread pool executor."""
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
        except ImportError as exc:
            logger.warning("faster-whisper is not installed; STT service unavailable: %s", exc)
            self.is_loaded = False
            return

        loop = asyncio.get_running_loop()
        logger.info(
            "Loading faster-whisper model '%s' on device '%s'...",
            settings.whisper_model_size,
            settings.whisper_device,
        )
        try:
            compute_type = "int8" if settings.whisper_device == "cpu" else "float16"

            def _load():
                cache_dir = os.path.expanduser(f"~/.cache/faster-whisper/{settings.whisper_model_size}")
                if os.path.exists(os.path.join(cache_dir, "model.bin")):
                    model_path = cache_dir
                else:
                    os.makedirs(cache_dir, exist_ok=True)
                    try:
                        model_path = download_model(settings.whisper_model_size, output_dir=cache_dir)
                    except Exception:
                        model_path = settings.whisper_model_size
                return WhisperModel(
                    model_path,
                    device=settings.whisper_device,
                    compute_type=compute_type,
                )

            self.model = await loop.run_in_executor(None, _load)
            self.is_loaded = True
            logger.info("Whisper STT model loaded successfully.")
        except Exception as exc:
            logger.error("Failed to load Whisper STT model: %s", exc)
            self.is_loaded = False

    def _transcribe_file_sync(self, wav_path: str, language: str | None = "en") -> dict[str, Any]:
        """Dynamically transcribe audio using faster-whisper with Silero VAD."""
        target_lang = language if (language and language.lower() not in ("auto", "none")) else "en"
        raw_text = ""
        info: Any = None

        try:
            segments, info = self.model.transcribe(
                wav_path,
                language=target_lang,
                beam_size=5,
                temperature=0.0,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                no_speech_threshold=0.5,
                log_prob_threshold=-1.0,
                compression_ratio_threshold=2.4,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.35,
                    min_speech_duration_ms=200,
                    min_silence_duration_ms=400,
                    speech_pad_ms=200,
                ),
                condition_on_previous_text=False,
            )
            raw_text = " ".join(segment.text for segment in segments).strip()
        except Exception as exc:
            logger.warning("Transcription exception: %s", exc)
            raw_text = ""

        # Dynamic cleaning
        cleaned = re.sub(r"^[\s\.\,\-\_…\?]+", "", raw_text).strip()
        cleaned = re.sub(r"[\s\.\,\-\_…]+$", "", cleaned).strip()
        cleaned = re.sub(r"\.{2,}", "", cleaned).strip()

        # Dynamic repetitive loop detection
        words = cleaned.split()
        if len(words) >= 4:
            counts = Counter(w.lower() for w in words)
            _, top_count = counts.most_common(1)[0]
            if (top_count / len(words)) >= 0.4:
                logger.warning("Discarded repetitive loop hallucination: %r", cleaned)
                cleaned = ""

        # Only discard if no alphanumeric characters exist
        if not any(c.isalnum() for c in cleaned):
            cleaned = ""

        lang = getattr(info, "language", target_lang) if info else target_lang
        conf = float(getattr(info, "language_probability", 0.0)) if info else 0.0
        dur = float(getattr(info, "duration", 0.0)) if info else 0.0

        logger.info(
            "STT result: text=%r (lang=%s, conf=%.2f, dur=%.2fs)",
            cleaned,
            lang,
            conf,
            dur,
        )

        return {
            "text": cleaned,
            "language": lang,
            "confidence": conf,
            "duration": dur,
        }

    async def transcribe(self, audio_bytes: bytes, language: str | None = "en") -> dict[str, Any]:
        """Convert raw audio bytes to 16kHz mono WAV and transcribe with Whisper."""
        if not self.is_loaded or self.model is None:
            raise RuntimeError("STT model is not loaded.")

        wav_bytes = await webm_to_wav_bytes(audio_bytes)
        temp_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(wav_bytes)
                temp_path = temp_file.name

            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._transcribe_file_sync, temp_path, language)
        finally:
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass


stt_service = STTService()
