"""WebSocket endpoint for real-time voice and text streaming."""

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.voice_pipeline import voice_pipeline
from app.utils.audio import base64_to_audio_bytes
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/ws", tags=["Voice"])


@router.websocket("/voice/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str) -> None:
    """Handle real-time bidirectional voice/text communication."""
    await websocket.accept()
    logger.info("WebSocket connected: session=%s", session_id)
    active_task: asyncio.Task[None] | None = None

    async def _cancel_active_task() -> None:
        nonlocal active_task
        if active_task and not active_task.done():
            voice_pipeline.request_interrupt(session_id)
            active_task.cancel()
            try:
                await active_task
            except asyncio.CancelledError:
                pass
        active_task = None

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON payload"})
                )
                continue

            msg_type = message.get("type")

            if msg_type == "audio":
                await _cancel_active_task()
                b64_data = message.get("data", "")
                if not b64_data:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Missing audio data"})
                    )
                    continue
                audio_bytes = await base64_to_audio_bytes(b64_data)
                tts_enabled = bool(message.get("tts_enabled", True))
                language = message.get("language")
                active_task = asyncio.create_task(
                    voice_pipeline.process_audio(
                        audio_bytes=audio_bytes,
                        session_id=session_id,
                        ws=websocket,
                        tts_enabled=tts_enabled,
                        language=language,
                    )
                )

            elif msg_type == "text":
                await _cancel_active_task()
                content = message.get("content", "")
                tts_enabled = bool(message.get("tts_enabled", True))
                language = message.get("language")
                active_task = asyncio.create_task(
                    voice_pipeline.process_text(
                        text=content,
                        session_id=session_id,
                        ws=websocket,
                        tts_enabled=tts_enabled,
                        language=language,
                    )
                )

            elif msg_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

            elif msg_type == "interrupt":
                await _cancel_active_task()
                await websocket.send_text(json.dumps({"type": "interrupted"}))

            else:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": f"Unknown message type: {msg_type}"})
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: session=%s", session_id)
        await _cancel_active_task()
    except Exception as exc:
        logger.error("WebSocket error for session=%s: %s", session_id, exc)
        await _cancel_active_task()
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(exc)}))
        except Exception:
            pass

