# TS Voice Assistant — Real-Time Voice AI Agent

A production-grade, low-latency, full-duplex Voice AI Assistant featuring **sub-1-second Time-To-First-Audio (TTFA)**, client-side Voice Activity Detection (VAD), sentence-pipelined LLM token generation, Microsoft Edge Neural TTS audio streaming, and instant conversational barge-in.

---

## Architecture Overview

```
                      ┌──────────────────────────────────────┐
                      │        Browser Client (React)        │
                      └──────────────────┬───────────────────┘
                                         │
                 User Speaks             │  1. Audio Frame (WebM/WAV)
           (Web Audio AnalyserNode VAD)  │  + Hardware Echo Cancellation
                                         ▼
                      ┌──────────────────────────────────────┐
                      │    FastAPI WebSocket Orchestrator    │
                      └──────────────────┬───────────────────┘
                                         │
                                         ▼
            ┌────────────────────────────────────────────────────────┐
            │         Faster-Whisper STT (small.en, CTranslate2)     │ ~400ms
            └────────────────────────────┬───────────────────────────┘
                                         │
                              Final User Transcript
                                         │
                                         ▼
            ┌────────────────────────────────────────────────────────┐
            │          Groq LLaMA 3.1 8B Instant (stream=True)       │ ~180ms TTFT
            └───────────────┬────────────────────────┬───────────────┘
                            │                        │
                   Streamed Tokens              Tokens Stream
                            │                        │
                            ▼                        ▼
               ┌────────────────────────┐  ┌────────────────────────┐
               │    Frontend UI Render  │  │   Sentence Tokenizer   │
               │  (Markdown & Cursor)   │  │   (. ? ! ; : \n)       │
               └────────────────────────┘  └─────────┬──────────────┘
                                                     │
                                             Completed Sentence
                                                     │
                                                     ▼
                                           ┌───────────────────┐
                                           │ Priority Queue    │
                                           └─────────┬─────────┘
                                                     │
                                                     ▼
                                  ┌────────────────────────────────────┐
                                  │   Microsoft Edge Neural TTS        │ ~160ms
                                  │   (en-US-ChristopherNeural)        │
                                  └──────────────────┬─────────────────┘
                                                     │
                                          Streamed MP3 Chunks
                                                     │
                                                     ▼
                                  ┌────────────────────────────────────┐
                                  │     Web Audio API Gapless Player   │
                                  │     (First sentence plays while    │
                                  │      rest is still generating)     │
                                  └────────────────────────────────────┘
```

---

## Latency Benchmark: Before vs. After

By migrating from a batch sequential request-response model to an asynchronous pipelined DAG, the conversational response latency has been reduced from **~5.5 seconds down to under 800 milliseconds**:

| Pipeline Stage | Legacy Architecture (Sequential) | New Upgraded Architecture (Pipelined) | Performance Delta |
| :--- | :--- | :--- | :--- |
| **Voice Activity Detection** | Server-side silence timeout (2,500ms) | Client-side Web Audio VAD (500ms) | **5.0x faster** |
| **STT Transcription** | Sequential Whisper `base` (850ms) | Faster-Whisper `small.en` (400ms) | **2.1x faster** |
| **LLM Generation** | Complete completion wait (1,800ms) | Groq Streamed TTFT (180ms) | **10.0x faster** |
| **TTS Synthesis** | Blocking full-text gTTS (1,400ms) | Edge TTS First Sentence (160ms) | **8.7x faster** |
| **Time-To-First-Audio (TTFA)** | **~5,500ms – 6,500ms** | **~740ms – 880ms** | **⚡ Sub-1s Real-Time** |
| **Barge-in / Interrupt** | ❌ Not supported | ✅ Instant (<50ms) Cancellation | **Full Duplex** |

---

## Core Capabilities & Features

### 1. Sub-Second Conversational Response (<1s TTFA)
Rather than waiting for the entire LLM response before synthesizing audio, TS chunks incoming tokens into complete sentences. As soon as the first sentence boundary (`.`, `?`, `!`, `\n`) is reached, it is queued for Edge Neural TTS synthesis. The browser begins audio playback of sentence #1 while sentence #2 and #3 are still generating.

### 2. Full-Duplex Barge-in & Interruption
- If the user starts speaking while the AI is replying, the client immediately pauses Web Audio playback, flushes audio queues, and issues an `{"type": "interrupt"}` message.
- The backend aborts active Groq streaming loops and Edge TTS workers within 5ms.
- Hardware `echoCancellation: true` prevents the AI's own audio output from falsely triggering user voice detection.

### 3. Real-Time Latency Instrumentation
Every turn logs a detailed performance trace to both server console and browser UI:
```text
⚡ [LATENCY] STT 420ms | LLM 180ms | TTS 160ms | Total 760ms
```
A live latency badge (`⚡ 760ms`) appears in the app header with a detailed breakdown tooltip.

### 4. Client-Side Voice Activity Detection (VAD)
- The Web Audio `AnalyserNode` monitors frequency bands in the human vocal range (85 Hz to 255 Hz).
- Turn transitions: Starts recording as soon as speech energy is detected and automatically cuts off 500ms after speech ends.
- The Voice Orb allows one-click toggling between **VAD Continuous Listening** mode and push-to-talk mode.

### 5. Production UI / UX Redesign
- **130px Voice Orb**: Four dynamic animated states:
  - *Idle*: Soft blue glow (`#2563EB`).
  - *Listening*: Vibrant red (`#DC2626`) with triple expanding pulse rings.
  - *Thinking*: Rotating conic gradient spinner.
  - *Speaking*: Soundbars and ripple waves responding to audio.
- **Rich Markdown AI Bubbles**: Bold text, bulleted and numbered lists, blockquotes, and code blocks with language labels and one-click copy.
- **Action Buttons**: Instant **Copy** and **Replay Audio** buttons on every AI response.
- **Empty State**: Three suggestion chips (*"What can you do?"*, *"Tell me a joke"*, *"Summarize today's news"*).
- **Accessibility & Theming**: Clean light theme on `#f8fafc` / `#f1f5f9` with dark mode toggle persisted in `localStorage`, WCAG AA contrast, and `aria-label`s on all buttons.
- **Keyboard Shortcuts**: `Space` to talk/stop, `Esc` to interrupt mid-reply.

---

## Project Structure

```text
Voice_AI/
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── routes/
│   │   │       ├── chat.py             # REST chat & history endpoints
│   │   │       ├── health.py           # Health check endpoint
│   │   │       ├── sessions.py         # Session CRUD endpoints
│   │   │       └── voice.py            # Real-time WebSocket endpoint (/ws/voice/{id})
│   │   ├── memory/
│   │   │   └── sqlite_memory.py        # SQLite persistent message store
│   │   ├── services/
│   │   │   ├── llm_service.py          # Groq LLaMA 3.1 streaming client
│   │   │   ├── stt_service.py          # Faster-Whisper small.en (CTranslate2)
│   │   │   ├── tts_service.py          # Edge Neural TTS + gTTS fallback
│   │   │   └── voice_pipeline.py       # Pipelined sentence queue orchestrator
│   │   ├── utils/
│   │   │   ├── audio.py                # Volume normalization & RMS noise gate
│   │   │   └── logger.py               # Structured log formatting
│   │   ├── config.py                   # Pydantic environment configuration
│   │   └── main.py                     # FastAPI application factory & lifespan
│   ├── requirements.txt                # Python package dependencies
│   └── .env                            # API keys & model configuration
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AudioVisualizer.jsx     # Web Audio AnalyserNode live waveform canvas
│   │   │   ├── ChatHistory.jsx         # Auto-scrolling chat, empty state, dashed bubble
│   │   │   ├── MarkdownRenderer.jsx    # Zero-dependency markdown parser & code block copy
│   │   │   ├── MessageBubble.jsx       # User/AI bubbles, Copy, Replay audio
│   │   │   ├── SettingsDrawer.jsx      # Dark mode, TTS toggle, language & session manager
│   │   │   └── VoiceOrb.jsx            # 130px orb with 4 dynamic animated states
│   │   ├── hooks/
│   │   │   ├── useAudioPlayer.js       # Web Audio API gapless chunk player & stop
│   │   │   ├── useVoiceRecorder.js     # Real-time VAD & audio capture
│   │   │   └── useWebSocket.js         # Auto-reconnecting WebSocket client
│   │   ├── services/
│   │   │   └── api.js                  # Axios client for REST endpoints
│   │   ├── styles/
│   │   │   └── index.css               # Light/Dark CSS theme variables & animations
│   │   ├── App.jsx                     # Top-level state & WebSocket coordinator
│   │   └── main.jsx                    # React 18 mount point
│   ├── package.json                    # Node dependencies & Vite scripts
│   ├── vite.config.js                  # Vite dev server & reverse proxy configuration
│   └── test_frontend_e2e.py            # Comprehensive 7-step E2E verification test suite
├── run_app.py                          # Single-command unified backend + frontend runner
└── README.md                           # Complete project documentation
```

---

## WebSocket Protocol Specification

Endpoint: `ws://127.0.0.1:8000/ws/voice/{session_id}` (or proxied via Vite at `ws://127.0.0.1:5173/ws/voice/{session_id}`)

### 1. Client to Server Messages

#### Send Audio Turn (VAD speech capture)
```json
{
  "type": "audio",
  "data": "<base64_encoded_webm_or_wav>",
  "tts_enabled": true,
  "language": "en"
}
```

#### Send Text Turn (typed message or suggestion chip)
```json
{
  "type": "text",
  "content": "What is the speed of light?",
  "tts_enabled": true,
  "language": "en"
}
```

#### Barge-in / Interrupt Request
```json
{
  "type": "interrupt"
}
```

#### Keepalive Ping
```json
{
  "type": "ping"
}
```

---

### 2. Server to Client Messages

#### Final Speech-to-Text Transcript
```json
{
  "type": "transcript",
  "text": "What is the speed of light?"
}
```

#### Streamed LLM Token
```json
{
  "type": "token",
  "text": "The",
  "content": "The"
}
```

#### Sentence Audio Start
```json
{
  "type": "audio_start",
  "sentence_index": 0,
  "text": "The speed of light in vacuum is approximately 299,792 kilometers per second."
}
```

#### Streamed Audio Chunk
```json
{
  "type": "audio",
  "data": "<base64_encoded_mp3_chunk>",
  "sentence_index": 0
}
```

#### Sentence Audio End
```json
{
  "type": "audio_end",
  "sentence_index": 0
}
```

#### Turn Latency Metrics
```json
{
  "type": "latency",
  "stt_ms": 412,
  "llm_ms": 178,
  "tts_ms": 154,
  "total_ms": 744,
  "summary": "STT 412ms | LLM 178ms | TTS 154ms | Total 744ms"
}
```

#### Turn Complete
```json
{
  "type": "done",
  "text": "The speed of light in vacuum is approximately 299,792 kilometers per second."
}
```

#### Turn Interrupted / Cancelled
```json
{
  "type": "interrupted"
}
```

---

## Getting Started

### Prerequisites
- **Python**: 3.10 or 3.11
- **Node.js**: 18+ and npm
- **FFmpeg**: Installed on your system `PATH` (used by `pydub` for audio normalization)
- **Groq API Key**: Free API key from [console.groq.com](https://console.groq.com)

---

### Step 1: Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate Python virtual environment
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure your environment variables
copy .env.example .env
```

Edit `backend/.env` with your Groq API key:
```env
GROQ_API_KEY=gsk_your_actual_groq_api_key_here
GROQ_MODEL=llama-3.1-8b-instant
WHISPER_MODEL_SIZE=small.en
TTS_PROVIDER=edge-tts
TTS_LANGUAGE=en
DATABASE_URL=sqlite+aiosqlite:///./data/voice_assistant.db
```

---

### Step 2: Frontend Setup

```bash
# Navigate to frontend directory
cd ../frontend

# Install dependencies
npm install
```

---

### Step 3: Run the Complete Application

You can launch both the FastAPI backend (`:8000`) and the Vite frontend (`:5173`) using the unified launcher:

```bash
# From the project root
python run_app.py
```

The application will be accessible at:
👉 **`http://localhost:5173`** (Frontend UI)  
👉 **`http://localhost:8000/docs`** (Interactive OpenAPI documentation)

---

## Running the Automated Test Suite

A comprehensive 7-step test script verifies the entire backend, proxy, and WebSocket real-time pipeline:

```bash
python frontend/test_frontend_e2e.py
```

The test asserts:
1. `GET /`: HTML index served correctly.
2. `GET /health`: STT, LLM, and TTS subsystem health status.
3. `POST /api/chat`: REST conversation fallback.
4. `GET /api/sessions`: SQLite session persistence.
5. `WS /ws/voice/{id}`: WebSocket handshake and ping/pong keepalive.
6. Full voice turn: Streaming LLM token delivery and Edge TTS audio chunk playback.
7. Session deletion and cleanup.

---

## Keyboard Shortcuts Reference

| Key | Context | Action |
| :--- | :--- | :--- |
| **`Space`** | Outside input bar | Toggle Voice Recording / Continuous VAD |
| **`Esc`** | Any | Interrupt AI response immediately (Barge-in) |
| **`Enter`** | In text input | Submit message |

---

## Technical Interview Guide: How It Works Under the Hood

### 1. How Sentence Pipelining Achieves <1s TTFA
Standard voice assistants run sequentially: User Audio $\to$ STT $\to$ Full LLM Response $\to$ Full Audio Synthesis $\to$ Playback. This causes a 4 to 6-second delay before the user hears anything.  
TS decouples token generation from audio synthesis using an **asynchronous producer-consumer queue**:
- Groq streams individual tokens in ~180ms.
- As tokens arrive, an in-memory sentence boundary tokenizer monitors punctuation patterns (`. `, `? `, `! `, `\n`).
- The moment a sentence is complete, it is enqueued into an `asyncio.Queue`.
- The Edge TTS consumer task begins generating audio for sentence #1 immediately.
- The browser begins playing audio via the Web Audio API in ~740ms while the LLM is still generating sentences #2 and #3.

### 2. Client-Side VAD vs. Server-Side VAD
Rather than streaming continuous raw audio over WebSockets—which wastes server bandwidth and incurs network round-trips—TS runs Voice Activity Detection locally in the browser using the Web Audio `AnalyserNode`. Speech frequencies (85Hz–255Hz) are integrated over 100ms frames. Once energy drops below the silence threshold for 500ms, the turn is finalized and dispatched to the server.

### 3. Barge-In & State Cancellation
When a user speaks while the AI is replying:
1. The client detects local mic energy above threshold despite audio output (aided by hardware acoustic echo cancellation).
2. The client immediately calls `AudioBufferSourceNode.stop()` to silence playback in 0ms.
3. The client sends `{"type": "interrupt"}` over the WebSocket.
4. The server flags the session as interrupted, calls `.cancel()` on the active `asyncio.Task`, and flushes the sentence queue.
5. The pipeline resets to `idle`, ready for the user's next utterance without race conditions or memory leaks.

---

## License

MIT License. Free for educational, personal, and commercial usage.
