"""Real-time voice pipeline with sentence pipelining, Edge TTS streaming, and latency instrumentation."""

import asyncio
import json
import re
import time
from typing import Any

from fastapi import WebSocket

from app.memory.sqlite_memory import memory_manager
from app.services.llm_service import llm_service
from app.services.stt_service import stt_service
from app.services.tts_service import tts_service
from app.utils.audio import mp3_to_base64, validate_audio
from app.utils.logger import get_logger

logger = get_logger(__name__)

SENTENCE_SPLIT_REGEX = re.compile(r'([.?!;:\n]+)')


class VoicePipeline:
    """Coordinates real-time STT, pipelined LLM token streaming, Edge TTS, and latency metrics."""

    def __init__(self) -> None:
        self._interrupted_sessions: set[str] = set()

    def request_interrupt(self, session_id: str) -> None:
        """Flag session to abort active LLM generation and audio playback immediately."""
        self._interrupted_sessions.add(session_id)

    def clear_interrupt(self, session_id: str) -> None:
        """Clear interrupt flag before starting a new turn."""
        self._interrupted_sessions.discard(session_id)

    def _is_interrupted(self, session_id: str) -> bool:
        return session_id in self._interrupted_sessions

    async def _send_json(self, ws: WebSocket, payload: dict[str, Any]) -> None:
        try:
            await ws.send_text(json.dumps(payload))
        except Exception:
            pass

    async def process_audio(
        self,
        audio_bytes: bytes,
        session_id: str,
        ws: WebSocket,
        tts_enabled: bool = True,
        language: str | None = None,
    ) -> None:
        """Run real-time STT -> Pipelined LLM -> Edge TTS with sub-second TTFA."""
        self.clear_interrupt(session_id)
        t_user_stopped = time.perf_counter()

        try:
            is_valid = await validate_audio(audio_bytes)
        except Exception as exc:
            logger.warning("Audio validation failed for session=%s: %s", session_id, exc)
            await self._send_json(
                ws,
                {"type": "error", "message": f"Transcription failed: invalid audio ({exc})"},
            )
            return

        if not is_valid:
            await self._send_json(
                ws,
                {"type": "error", "message": "Transcription failed: audio too short or silent"},
            )
            return

        try:
            stt_result = await stt_service.transcribe(audio_bytes, language=language)
        except Exception as exc:
            logger.error("STT error for session=%s: %s", session_id, exc)
            await self._send_json(
                ws,
                {"type": "error", "message": f"Transcription failed: {exc}"},
            )
            return

        transcript = (stt_result.get("text") or "").strip()
        duration = stt_result.get("duration")
        t_stt_done = time.perf_counter()

        if not transcript:
            await self._send_json(
                ws,
                {"type": "error", "message": "Transcription failed: no speech detected"},
            )
            return

        # Notify UI of confirmed user transcript
        await self._send_json(ws, {"type": "transcript", "text": transcript})

        await self._stream_pipelined_response(
            user_text=transcript,
            session_id=session_id,
            ws=ws,
            audio_duration=duration,
            tts_enabled=tts_enabled,
            language=language,
            t_user_stopped=t_user_stopped,
            t_stt_done=t_stt_done,
        )

    async def process_text(
        self,
        text: str,
        session_id: str,
        ws: WebSocket,
        tts_enabled: bool = True,
        language: str | None = None,
    ) -> None:
        """Run pipelined LLM -> Edge TTS directly from text input."""
        self.clear_interrupt(session_id)
        cleaned = text.strip()
        if not cleaned:
            await self._send_json(ws, {"type": "error", "message": "Message cannot be empty"})
            return

        t_start = time.perf_counter()
        await self._stream_pipelined_response(
            user_text=cleaned,
            session_id=session_id,
            ws=ws,
            audio_duration=None,
            tts_enabled=tts_enabled,
            language=language,
            t_user_stopped=t_start,
            t_stt_done=t_start,
        )

    async def _stream_pipelined_response(
        self,
        user_text: str,
        session_id: str,
        ws: WebSocket,
        audio_duration: float | None,
        tts_enabled: bool,
        language: str | None,
        t_user_stopped: float,
        t_stt_done: float,
    ) -> None:
        """Stream LLM tokens and concurrently synthesize sentences with Edge TTS."""
        tokens: list[str] = []
        t_first_token: float | None = None
        t_first_audio: float | None = None

        tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
        sentence_buffer = ""

        # Concurrent TTS worker that plays sentences as soon as they complete
        async def tts_worker() -> None:
            nonlocal t_first_audio
            sentence_index = 0
            while not self._is_interrupted(session_id):
                item = await tts_queue.get()
                if item is None:
                    tts_queue.task_done()
                    break

                sentence_text = item
                if tts_enabled and sentence_text.strip() and not self._is_interrupted(session_id):
                    try:
                        await self._send_json(
                            ws,
                            {
                                "type": "audio_start",
                                "sentence_index": sentence_index,
                                "text": sentence_text,
                            },
                        )

                        # Stream audio chunks for this sentence
                        async for chunk in tts_service.stream_sentence_audio(
                            sentence_text, language=language
                        ):
                            if self._is_interrupted(session_id):
                                break
                            if t_first_audio is None:
                                t_first_audio = time.perf_counter()

                            b64 = await mp3_to_base64(chunk)
                            await self._send_json(
                                ws,
                                {
                                    "type": "audio",
                                    "data": b64,
                                    "sentence_index": sentence_index,
                                },
                            )

                        await self._send_json(
                            ws,
                            {
                                "type": "audio_end",
                                "sentence_index": sentence_index,
                            },
                        )
                        sentence_index += 1
                    except Exception as exc:
                        logger.warning("TTS sentence stream error for session=%s: %s", session_id, exc)

                tts_queue.task_done()

        tts_worker_task = asyncio.create_task(tts_worker())

        try:
            async for token in llm_service.astream_response(user_text, session_id):
                if self._is_interrupted(session_id):
                    logger.info("Turn interrupted for session=%s", session_id)
                    break

                if t_first_token is None:
                    t_first_token = time.perf_counter()

                tokens.append(token)

                # Send token in both formats for complete compatibility
                await self._send_json(
                    ws,
                    {
                        "type": "token",
                        "text": token,
                        "content": token,  # backward compatibility
                    },
                )

                sentence_buffer += token

                # If sentence boundary reached, immediately push sentence to TTS queue
                if any(punct in token for punct in ('.', '?', '!', '\n', ':')):
                    parts = SENTENCE_SPLIT_REGEX.split(sentence_buffer)
                    while len(parts) >= 3:
                        complete_sentence = (parts.pop(0) + parts.pop(0)).strip()
                        if complete_sentence:
                            await tts_queue.put(complete_sentence)
                    sentence_buffer = "".join(parts)

            # Flush trailing sentence buffer
            if sentence_buffer.strip() and not self._is_interrupted(session_id):
                await tts_queue.put(sentence_buffer.strip())

        except Exception as exc:
            logger.error("LLM streaming error for session=%s: %s", session_id, exc)
            await self._send_json(ws, {"type": "error", "message": f"LLM error: {exc}"})
        finally:
            # Signal end to TTS worker
            await tts_queue.put(None)
            try:
                await tts_worker_task
            except asyncio.CancelledError:
                pass

        if self._is_interrupted(session_id):
            await self._send_json(ws, {"type": "interrupted"})
            return

        full_response = "".join(tokens).strip()

        # Latency instrumentation
        t_done = time.perf_counter()
        stt_ms = int(max(0, (t_stt_done - t_user_stopped) * 1000))
        llm_ms = int(max(0, ((t_first_token - t_stt_done) if t_first_token else 0) * 1000))
        tts_ms = int(max(0, ((t_first_audio - t_first_token) if (t_first_audio and t_first_token) else 0) * 1000))
        total_ms = int(max(0, (t_done - t_user_stopped) * 1000))

        summary_log = f"STT {stt_ms}ms | LLM {llm_ms}ms | TTS {tts_ms}ms | Total {total_ms}ms"
        logger.info("Latency Summary: %s", summary_log)
        print(f"\n⚡ [LATENCY] {summary_log}\n")

        # Send latency metrics to frontend
        await self._send_json(
            ws,
            {
                "type": "latency",
                "stt_ms": stt_ms,
                "llm_ms": llm_ms,
                "tts_ms": tts_ms,
                "total_ms": total_ms,
                "summary": summary_log,
            },
        )

        # Persist conversation turn in SQLite
        if full_response:
            try:
                await memory_manager.record_turn(
                    session_id=session_id,
                    user_text=user_text,
                    assistant_text=full_response,
                    audio_duration=audio_duration,
                )
            except Exception as exc:
                logger.warning("Failed to record turn in DB: %s", exc)

        await self._send_json(ws, {"type": "done", "text": full_response})


voice_pipeline = VoicePipeline()
