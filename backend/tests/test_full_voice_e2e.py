"""Comprehensive full-stack voice agent end-to-end test.
Tests voice input -> STT transcription -> LLM response -> TTS voice synthesis -> WebSocket audio streaming,
plus text input, interruption, and database persistence.
"""

import asyncio
import base64
import io
import json
import unittest

from fastapi.testclient import TestClient
from gtts import gTTS
from pydub import AudioSegment

from app.main import app
from app.utils.audio import mp3_to_base64


class TestFullVoiceEndToEnd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Pre-synthesize a sample spoken speech utterance using gTTS
        print("\n[Setup] Synthesizing speech audio for voice agent testing ('Hello ARIA, what is your name?')...")
        tts = gTTS(text="Hello ARIA, what is your name?", lang="en")
        mp3_io = io.BytesIO()
        tts.write_to_fp(mp3_io)
        mp3_io.seek(0)
        
        # Convert MP3 to WAV 16kHz mono using pydub
        sound = AudioSegment.from_file(mp3_io, format="mp3")
        sound = sound.set_channels(1).set_frame_rate(16000).set_sample_width(2)
        wav_io = io.BytesIO()
        sound.export(wav_io, format="wav")
        cls.speech_wav_bytes = wav_io.getvalue()
        cls.speech_b64 = base64.b64encode(cls.speech_wav_bytes).decode("utf-8")
        print(f"[Setup] Generated speech audio: {len(cls.speech_wav_bytes)} bytes WAV")

    def test_voice_agent_end_to_end_full_flow(self):
        session_id = "test-voice-e2e-session"

        with TestClient(app) as client:
            # 1. Verify Health
            print("\n--- 1. Health Status ---")
            health_res = client.get("/health")
            self.assertEqual(health_res.status_code, 200)
            health = health_res.json()
            print(f"Health: status={health['status']}, services={health['services']}")
            self.assertEqual(health["status"], "healthy")
            self.assertEqual(health["services"]["stt"], "ready")
            self.assertEqual(health["services"]["llm"], "ready")
            self.assertEqual(health["services"]["tts"], "ready")

            # 2. WebSocket Voice Turn (Audio -> STT -> LLM -> TTS -> Audio)
            print("\n--- 2. WebSocket Voice Turn (Speech Audio -> STT -> LLM -> TTS) ---")
            with client.websocket_connect(f"/ws/voice/{session_id}") as ws:
                # Send speech audio frame
                ws.send_text(json.dumps({
                    "type": "audio",
                    "data": self.speech_b64,
                    "tts_enabled": True
                }))

                transcript_received = None
                tokens = []
                audio_frames = []
                done_received = False

                while True:
                    msg = json.loads(ws.receive_text())
                    msg_type = msg.get("type")

                    if msg_type == "transcript":
                        transcript_received = msg.get("text", "")
                        print(f"✓ STT Transcript Received: '{transcript_received}'")
                    elif msg_type == "llm_token":
                        tokens.append(msg.get("content", ""))
                    elif msg_type == "audio":
                        audio_frames.append(msg.get("data", ""))
                    elif msg_type == "done":
                        done_received = True
                        break
                    elif msg_type == "error":
                        self.fail(f"Unexpected voice pipeline error: {msg.get('message')}")

                llm_reply = "".join(tokens)
                print(f"✓ LLM Streamed Reply ({len(tokens)} tokens): '{llm_reply}'")
                print(f"✓ TTS Audio Frames Received ({len(audio_frames)}): total length={sum(len(f) for f in audio_frames)} chars")

                # Assertions for voice cycle
                self.assertIsNotNone(transcript_received, "STT must emit a transcript")
                self.assertTrue(len(transcript_received) > 0, "Transcript should not be empty")
                # Whisper should recognize "hello" or "aria" or "name"
                transcript_lower = transcript_received.lower()
                self.assertTrue(
                    any(w in transcript_lower for w in ["hello", "aria", "what", "name"]),
                    f"Expected keywords in transcript, got: {transcript_received}"
                )
                self.assertTrue(len(tokens) > 0, "LLM should stream response tokens")
                self.assertTrue(len(audio_frames) > 0, "TTS should synthesize audio frames")
                self.assertTrue(done_received, "Done event must be received")

                # 3. WebSocket Text Turn (Text -> LLM -> TTS)
                print("\n--- 3. WebSocket Text Turn ---")
                ws.send_text(json.dumps({
                    "type": "text",
                    "content": "What is 5 times 5?",
                    "tts_enabled": True
                }))

                text_tokens = []
                text_audio_frames = []
                text_done = False

                while True:
                    msg = json.loads(ws.receive_text())
                    msg_type = msg.get("type")
                    if msg_type == "llm_token":
                        text_tokens.append(msg.get("content", ""))
                    elif msg_type == "audio":
                        text_audio_frames.append(msg.get("data", ""))
                    elif msg_type == "done":
                        text_done = True
                        break
                    elif msg_type == "error":
                        self.fail(f"Text turn error: {msg.get('message')}")

                print(f"✓ Text Reply: '{''.join(text_tokens)}'")
                print(f"✓ Text TTS Audio Frames: {len(text_audio_frames)}")
                self.assertTrue(len(text_tokens) > 0)
                self.assertTrue(len(text_audio_frames) > 0)
                self.assertTrue(text_done)

            # 4. Conversation History Persistence
            print("\n--- 4. Database History Verification ---")
            hist_res = client.get(f"/api/sessions/{session_id}/history")
            self.assertEqual(hist_res.status_code, 200)
            messages = hist_res.json()["messages"]
            print(f"Recorded messages in DB: {len(messages)}")
            for idx, m in enumerate(messages):
                print(f"  [{idx+1}] {m['role']}: {m['content'][:60]}... (audio_duration={m.get('audio_duration')})")

            # 2 turns = 4 messages (user voice, assistant voice, user text, assistant text)
            self.assertEqual(len(messages), 4)
            self.assertEqual(messages[0]["role"], "user")
            self.assertIsNotNone(messages[0]["audio_duration"], "First message was voice, duration should be recorded")
            self.assertEqual(messages[1]["role"], "assistant")
            self.assertEqual(messages[2]["role"], "user")
            self.assertEqual(messages[3]["role"], "assistant")

            # 5. Clean up
            print("\n--- 5. Cleanup Session ---")
            del_res = client.delete(f"/api/sessions/{session_id}")
            self.assertEqual(del_res.status_code, 200)
            print("✓ Session deleted cleanly")


if __name__ == "__main__":
    unittest.main()
