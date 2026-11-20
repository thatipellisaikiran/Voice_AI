"""Speech-to-Text service with ultra-fast Groq Cloud Whisper and local fallback."""

import asyncio
import io
import os
import re
import tempfile
from collections import Counter
from typing import Any

import httpx

from app.config import settings
from app.utils.audio import webm_to_wav_bytes
from app.utils.logger import get_logger

logger = get_logger(__name__)


class STTService:
    """Transcribes speech using ultra-fast Groq Whisper Cloud with faster-whisper local fallback."""

    def __init__(self) -> None:
        self.model: Any = None
        self.is_loaded: bool = False

    async def load_model(self) -> None:
        """Load local faster-whisper model as a reliable fallback."""
        try:
            from faster_whisper import WhisperModel
            from faster_whisper.utils import download_model
        except ImportError as exc:
            logger.warning("faster-whisper is not installed; will rely on Groq Cloud STT: %s", exc)
            self.is_loaded = True
            return

        loop = asyncio.get_running_loop()
        model_name = settings.effective_whisper_model
        logger.info(
            "Loading faster-whisper model '%s' on device '%s'...",
            model_name,
            settings.whisper_device,
        )
        try:
            compute_type = "int8" if settings.whisper_device == "cpu" else "float16"

            def _load():
                cache_dir = os.path.expanduser(f"~/.cache/faster-whisper/{model_name}")
                if os.path.exists(os.path.join(cache_dir, "model.bin")):
                    model_path = cache_dir
                else:
                    os.makedirs(cache_dir, exist_ok=True)
                    try:
                        model_path = download_model(model_name, output_dir=cache_dir)
                    except Exception:
                        model_path = model_name
                return WhisperModel(
                    model_path,
                    device=settings.whisper_device,
                    compute_type=compute_type,
                )

            self.model = await loop.run_in_executor(None, _load)
            self.is_loaded = True
            logger.info("Whisper STT model loaded successfully.")
        except Exception as exc:
            logger.warning("Failed to load local Whisper STT model (will use Groq Cloud): %s", exc)
            self.is_loaded = True

    async def _transcribe_groq_cloud(self, wav_bytes: bytes, language: str | None = "en") -> str:
        """High-speed cloud transcription via Groq whisper-large-v3-turbo (typically ~150-350ms)."""
        api_key = (settings.groq_api_key or "").strip()
        if not api_key or api_key == "gsk_your_key_here":
            return ""

        target_lang = language if (language and language.lower() not in ("auto", "none")) else "en"
        files = {"file": ("audio.wav", wav_bytes, "audio/wav")}
        data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "json",
            "language": target_lang,
            "temperature": "0.0",
        }
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files=files,
                    data=data,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    text = (result.get("text") or "").strip()
                    if text:
                        logger.info("Groq Cloud STT transcription: %r", text)
                        return text
                else:
                    logger.warning("Groq Whisper API returned status %s: %s", resp.status_code, resp.text)
        except Exception as exc:
            logger.warning("Groq Cloud STT failed, checking Gemini / local Whisper: %s", exc)

        return ""

    async def _transcribe_gemini_cloud(self, wav_bytes: bytes, language: str | None = "en") -> str:
        """Fallback cloud speech transcription via Google Gemini Multimodal API."""
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key or api_key == "your_gemini_api_key_here":
            return ""

        import base64
        model = "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        wav_b64 = base64.b64encode(wav_bytes).decode("ascii")
        prompt = f"Transcribe the following speech audio exactly as spoken in {language or 'English'}. Output ONLY the transcribed words with no commentary, no markdown, and no quotes."
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {"inline_data": {"mime_type": "audio/wav", "data": wav_b64}},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.0, "maxOutputTokens": 256},
        }

        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    text = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                    if text:
                        logger.info("Gemini Cloud STT transcription: %r", text)
                        return text
        except Exception as exc:
            logger.warning("Gemini Cloud STT failed: %s", exc)

        return ""

    def _transcribe_file_sync(self, wav_path: str, language: str | None = "en") -> dict[str, Any]:
        """Local faster-whisper transcription (beam_size=1 for maximum speed)."""
        if not self.model:
            return {"text": "", "language": "en", "confidence": 0.0, "duration": 0.0}

        target_lang = language if (language and language.lower() not in ("auto", "none")) else "en"
        raw_text = ""
        info: Any = None

        try:
            segments, info = self.model.transcribe(
                wav_path,
                language=target_lang,
                beam_size=1,  # Greedy search: 3-5x faster than beam_size=5
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(
                    threshold=0.35,
                    min_speech_duration_ms=150,
                    min_silence_duration_ms=300,
                    speech_pad_ms=150,
                ),
                condition_on_previous_text=False,
            )
            raw_text = " ".join(segment.text for segment in segments).strip()
        except Exception as exc:
            logger.warning("Local transcription exception: %s", exc)
            raw_text = ""

        cleaned = self._clean_transcript(raw_text, target_lang)
        lang = getattr(info, "language", target_lang) if info else target_lang
        conf = float(getattr(info, "language_probability", 0.0)) if info else 0.0
        dur = float(getattr(info, "duration", 0.0)) if info else 0.0

        return {
            "text": cleaned,
            "language": lang,
            "confidence": conf,
            "duration": dur,
        }

    def _clean_transcript(self, raw_text: str, target_lang: str) -> str:
        """Filter repetitive hallucinations and strip leading/trailing noise."""
        cleaned = re.sub(r"^[\s\.\,\-\_…\?]+", "", raw_text).strip()
        cleaned = re.sub(r"[\s\.\,\-\_…]+$", "", cleaned).strip()
        cleaned = re.sub(r"\.{2,}", "", cleaned).strip()

        words = cleaned.split()
        if len(words) >= 4:
            counts = Counter(w.lower() for w in words)
            _, top_count = counts.most_common(1)[0]
            if (top_count / len(words)) >= 0.4:
                logger.warning("Discarded repetitive loop hallucination: %r", cleaned)
                return ""

        if not any(c.isalnum() for c in cleaned):
            return ""

        return cleaned

    async def transcribe(self, audio_bytes: bytes, language: str | None = "en") -> dict[str, Any]:
        """Convert audio to WAV and transcribe via ultra-fast Groq Cloud (with local fallback)."""
        if audio_bytes.startswith(b"RIFF"):
            wav_bytes = audio_bytes
        else:
            wav_bytes = await webm_to_wav_bytes(audio_bytes)

        # 1. Try ultra-fast Groq Cloud Whisper (~200ms)
        cloud_text = await self._transcribe_groq_cloud(wav_bytes, language=language)
        if not cloud_text:
            # 2. Try Gemini Multimodal Cloud Audio Transcription
            cloud_text = await self._transcribe_gemini_cloud(wav_bytes, language=language)

        if cloud_text:
            cleaned = self._clean_transcript(cloud_text, language or "en")
            if cleaned:
                return {
                    "text": cleaned,
                    "language": language or "en",
                    "confidence": 0.95,
                    "duration": 0.0,
                }

        # 3. Local fallback if cloud was empty or unavailable
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
