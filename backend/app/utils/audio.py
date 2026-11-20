"""Audio conversion, validation, and base64 encoding utilities."""

import asyncio
import base64
import glob
import os
import shutil
from io import BytesIO

# Ensure ffmpeg binary installed via winget or in PATH is registered before pydub initializes
ffmpeg_bin = shutil.which("ffmpeg")
if not ffmpeg_bin:
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    if local_appdata:
        winget_pattern = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages", "*ffmpeg*", "**", "bin")
        ffmpeg_dirs = glob.glob(winget_pattern, recursive=True)
        if ffmpeg_dirs and ffmpeg_dirs[0] not in os.environ.get("PATH", ""):
            os.environ["PATH"] = ffmpeg_dirs[0] + os.pathsep + os.environ.get("PATH", "")
            ffmpeg_bin = shutil.which("ffmpeg")

try:
    from pydub import AudioSegment
    if ffmpeg_bin:
        AudioSegment.converter = ffmpeg_bin
except Exception:
    AudioSegment = None


def _get_audio_segment():
    if AudioSegment is None:
        raise RuntimeError(
            "pydub is required for audio processing. Install it with 'pip install pydub'."
        )
    return AudioSegment


def _convert_to_wav_sync(audio_bytes: bytes) -> bytes:
    AudioSegment = _get_audio_segment()
    audio = AudioSegment.from_file(BytesIO(audio_bytes))
    audio = audio.set_channels(1)
    audio = audio.set_frame_rate(16000)
    audio = audio.set_sample_width(2)
    # Dynamic speech volume normalization: only normalize if audio has actual signal (rms >= 20)
    if audio.rms >= 20 and audio.max_dBFS < -3.0:
        try:
            from pydub.effects import normalize
            audio = normalize(audio, headroom=1.0)
        except Exception:
            pass
    output = BytesIO()
    audio.export(output, format="wav")
    return output.getvalue()


def _validate_audio_sync(audio_bytes: bytes) -> bool:
    if not audio_bytes or len(audio_bytes) < 32:
        return False
    try:
        AudioSegment = _get_audio_segment()
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        # Valid speech audio must have at least 250ms duration and rms >= 10
        return len(audio) >= 250 and audio.rms >= 10
    except Exception:
        return False


def _convert_and_validate_sync(audio_bytes: bytes) -> tuple[bytes | None, bool]:
    """Single-pass ffmpeg decode, validation, normalization, and WAV export."""
    if not audio_bytes or len(audio_bytes) < 32:
        return None, False
    try:
        AudioSegment = _get_audio_segment()
        audio = AudioSegment.from_file(BytesIO(audio_bytes))
        if len(audio) < 200 or audio.rms < 8:
            return None, False

        audio = audio.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        if audio.rms >= 20 and audio.max_dBFS < -3.0:
            try:
                from pydub.effects import normalize
                audio = normalize(audio, headroom=1.0)
            except Exception:
                pass

        out = BytesIO()
        audio.export(out, format="wav")
        return out.getvalue(), True
    except Exception:
        return None, False


async def prepare_speech_audio(audio_bytes: bytes) -> tuple[bytes | None, bool]:
    """Single-pass validation and WAV conversion for ultra-low latency."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _convert_and_validate_sync, audio_bytes)


async def webm_to_wav_bytes(audio_bytes: bytes) -> bytes:
    """Convert browser audio bytes (e.g. webm/opus or wav) to 16kHz mono 16-bit WAV."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _convert_to_wav_sync, audio_bytes)


async def mp3_to_base64(mp3_bytes: bytes) -> str:
    """Encode MP3 bytes to a UTF-8 base64 string."""
    return base64.b64encode(mp3_bytes).decode("utf-8")


async def base64_to_audio_bytes(b64_str: str) -> bytes:
    """Decode a base64 audio string (optionally stripping a data URL prefix) to raw bytes."""
    if "," in b64_str and b64_str.startswith("data:"):
        b64_str = b64_str.split(",", 1)[1]
    return base64.b64decode(b64_str)


async def validate_audio(audio_bytes: bytes) -> bool:
    """Validate that audio is at least 0.5 seconds long and not completely silent."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _validate_audio_sync, audio_bytes)
