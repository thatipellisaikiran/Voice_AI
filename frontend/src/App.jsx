import React, { useCallback, useEffect, useRef, useState } from 'react';
import { v4 as uuidv4 } from 'uuid';
import { AudioVisualizer } from './components/AudioVisualizer';
import { ChatHistory } from './components/ChatHistory';
import { SettingsDrawer } from './components/SettingsDrawer';
import { VoiceOrb } from './components/VoiceOrb';
import { useAudioPlayer } from './hooks/useAudioPlayer';
import { useVoiceRecorder } from './hooks/useVoiceRecorder';
import { useWebSocket } from './hooks/useWebSocket';
import { getSessionHistory, sendTextChat } from './services/api';

/**
 * Convert ArrayBuffer to Base64 string for audio transmission over WebSocket.
 */
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += chunkSize) {
    const chunk = bytes.subarray(i, i + chunkSize);
    binary += String.fromCharCode.apply(null, chunk);
  }
  return btoa(binary);
}

export default function App() {
  // Session ID persisted across page reloads
  const [sessionId, setSessionId] = useState(() => {
    const saved = localStorage.getItem('session_id');
    if (saved) return saved;
    const fresh = uuidv4();
    localStorage.setItem('session_id', fresh);
    return fresh;
  });

  // Theme: 'light' or 'dark'
  const [theme, setTheme] = useState(() => {
    return localStorage.getItem('ts_theme') || 'light';
  });

  // Chat, Voice, and Latency States
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle'); // 'idle' | 'recording' | 'processing' | 'speaking' | 'error'
  const [errorMessage, setErrorMessage] = useState('');
  const [streamingContent, setStreamingContent] = useState('');
  const [partialTranscript, setPartialTranscript] = useState('');
  const [latencyStats, setLatencyStats] = useState(null);
  const [textInput, setTextInput] = useState('');
  const [showSettings, setShowSettings] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [language, setLanguage] = useState('en');

  // Refs for tracking state without stale closures
  const streamingContentRef = useRef('');
  const currentTurnAudioRef = useRef([]);
  const speechRecognitionRef = useRef(null);

  // Sync theme attribute to HTML document root
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('ts_theme', theme);
  }, [theme]);

  // Audio Player Hook (progressive sentence playback & interruption)
  const { isPlaying, playAudio, stopAudio } = useAudioPlayer();

  // Handle Barge-in: if user starts speaking while AI speaks, interrupt immediately
  const handleBargeIn = useCallback(() => {
    if (isPlaying || status === 'speaking' || status === 'processing') {
      stopAudio();
      // Will be sent via WebSocket
    }
  }, [isPlaying, status, stopAudio]);

  // Audio Recording Hook with Real-Time VAD Turn Detection
  const {
    isRecording,
    isAlwaysListening,
    toggleAlwaysListening,
    startRecording,
    stopRecording,
    audioBlob,
    clearAudioBlob,
    mediaStream,
    error: recorderError,
  } = useVoiceRecorder({
    silenceThreshold: 12,
    silenceDurationMs: 600,
    onSpeechDetected: handleBargeIn,
  });

  /**
   * Append a completed message to the conversation history.
   */
  const appendMessage = useCallback(
    (role, content, timestamp = new Date().toISOString(), audioData = null) => {
      if (!content) return;
      setMessages((prev) => [
        ...prev,
        {
          id: uuidv4(),
          role,
          content,
          timestamp,
          audioData,
        },
      ]);
    },
    []
  );

  /**
   * =========================================================================
   * WEBSOCKET MESSAGE HANDLER
   * Handles:
   * - 'partial_transcript': Live user speech token/chunk while speaking
   * - 'transcript': Final STT result from Faster-Whisper
   * - 'token' / 'llm_token': Streamed LLM token from Google Gemini 2.0 Flash
   * - 'audio_start': New sentence synthesis initiated by Edge TTS
   * - 'audio': Synthesized base64 MP3 chunk from Edge TTS
   * - 'audio_end': Sentence synthesis complete
   * - 'latency': Real-time turn latency metrics (STT, LLM, TTS, Total)
   * - 'done': Generation cycle complete
   * - 'interrupted': Agent acknowledged user barge-in / interrupt
   * - 'error': Pipeline or model exception
   * =========================================================================
   */
  const handleWsMessage = useCallback(
    (msg) => {
      switch (msg.type) {
        // Live partial STT
        case 'partial_transcript':
          if (msg.text) {
            setPartialTranscript(msg.text);
          }
          break;

        // Final user transcript from Faster-Whisper
        case 'transcript':
          setPartialTranscript('');
          appendMessage('user', msg.text);
          setStatus('processing');
          streamingContentRef.current = '';
          currentTurnAudioRef.current = [];
          setStreamingContent('');
          break;

        // Real-time LLM token streaming from Google Gemini 2.0 Flash
        case 'token':
        case 'llm_token': {
          const tokenText = msg.text || msg.content || '';
          streamingContentRef.current += tokenText;
          setStreamingContent(streamingContentRef.current);
          break;
        }

        // Sentence audio stream start
        case 'audio_start':
          setStatus('speaking');
          break;

        // Progressive audio chunk from Edge TTS
        case 'audio':
          if (ttsEnabled && msg.data) {
            currentTurnAudioRef.current.push(msg.data);
            setStatus('speaking');
            playAudio(msg.data);
          }
          break;

        // Sentence audio stream end
        case 'audio_end':
          break;

        // Turn latency report from backend
        case 'latency':
          setLatencyStats(msg);
          break;

        // Turn completion signal
        case 'done': {
          const finalContent = (msg.text || streamingContentRef.current).trim();
          const turnAudio =
            currentTurnAudioRef.current.length > 0
              ? currentTurnAudioRef.current[0]
              : null;

          if (finalContent) {
            appendMessage('assistant', finalContent, new Date().toISOString(), turnAudio);
          }
          streamingContentRef.current = '';
          setStreamingContent('');
          setStatus((prev) => (prev === 'speaking' ? 'speaking' : 'idle'));
          break;
        }

        // Barge-in / Interrupt acknowledged
        case 'interrupted':
          if (streamingContentRef.current.trim()) {
            appendMessage('assistant', streamingContentRef.current.trim());
          }
          streamingContentRef.current = '';
          currentTurnAudioRef.current = [];
          setStreamingContent('');
          stopAudio();
          setStatus('idle');
          break;

        // Error message from server
        case 'error': {
          streamingContentRef.current = '';
          setStreamingContent('');
          const errText = msg.message || 'Pipeline error';
          if (
            errText.toLowerCase().includes('no speech detected') ||
            errText.toLowerCase().includes('audio too short')
          ) {
            setErrorMessage('No speech detected. Speak clearly into your mic or type below.');
          } else {
            setErrorMessage(errText);
          }
          setStatus('error');
          setTimeout(() => {
            setStatus((cur) => (cur === 'error' ? 'idle' : cur));
            setErrorMessage('');
          }, 3500);
          break;
        }

        default:
          break;
      }
    },
    [appendMessage, playAudio, stopAudio, ttsEnabled]
  );

  // Initialize WebSocket connection
  const { sendMessage, connectionStatus } = useWebSocket(sessionId, handleWsMessage);

  // Return to idle state when audio playback finishes
  useEffect(() => {
    if (!isPlaying && status === 'speaking' && !streamingContent) {
      setStatus('idle');
    }
  }, [isPlaying, status, streamingContent]);

  // Display microphone capture errors
  useEffect(() => {
    if (recorderError) {
      setErrorMessage(recorderError);
      setStatus('error');
    }
  }, [recorderError]);

  // Load session history from SQLite backend
  useEffect(() => {
    let cancelled = false;
    localStorage.setItem('session_id', sessionId);
    streamingContentRef.current = '';
    currentTurnAudioRef.current = [];
    setStreamingContent('');
    setPartialTranscript('');

    getSessionHistory(sessionId)
      .then((res) => {
        if (cancelled) return;
        const loaded = (res.messages || []).map((item) => ({
          id: item.id,
          role: item.role,
          content: item.content,
          timestamp: item.created_at,
          audioData: null,
        }));
        setMessages(loaded);
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  // Send recorded audio over WebSocket once VAD finishes detecting turn
  useEffect(() => {
    if (!audioBlob) return;

    let cancelled = false;
    audioBlob.arrayBuffer().then((buffer) => {
      if (cancelled) return;
      const base64 = arrayBufferToBase64(buffer);
      clearAudioBlob();

      // Send audio message to backend WebSocket
      const sent = sendMessage({
        type: 'audio',
        data: base64,
        tts_enabled: ttsEnabled,
        language,
      });

      if (sent) {
        setErrorMessage('');
        setStatus('processing');
      } else {
        setErrorMessage('WebSocket disconnected. Reconnecting...');
        setStatus('error');
      }
    });

    return () => {
      cancelled = true;
    };
  }, [audioBlob, clearAudioBlob, language, sendMessage, ttsEnabled]);

  /**
   * Start microphone recording with live partial transcript support.
   */
  const handleStartRecording = async () => {
    if (isPlaying || status === 'speaking' || status === 'processing') {
      handleInterrupt();
    } else {
      stopAudio();
    }

    setErrorMessage('');
    setPartialTranscript('');

    try {
      await startRecording();
      setStatus('recording');

      // Browser Web Speech API for instant live partial transcript
      const SpeechRecognition =
        window.SpeechRecognition || window.webkitSpeechRecognition;
      if (SpeechRecognition) {
        try {
          const recognizer = new SpeechRecognition();
          recognizer.continuous = true;
          recognizer.interimResults = true;
          recognizer.lang = language === 'en' ? 'en-US' : language;

          recognizer.onresult = (event) => {
            let interim = '';
            for (let i = event.resultIndex; i < event.results.length; i++) {
              interim += event.results[i][0].transcript;
            }
            if (interim) {
              setPartialTranscript(interim);
            }
          };

          recognizer.onerror = () => {};
          recognizer.start();
          speechRecognitionRef.current = recognizer;
        } catch {
          // Fallback silent
        }
      }
    } catch {
      setStatus('error');
    }
  };

  /**
   * Stop recording speech.
   */
  const handleStopRecording = () => {
    if (speechRecognitionRef.current) {
      try {
        speechRecognitionRef.current.stop();
      } catch {
        // Ignore stop error
      }
      speechRecognitionRef.current = null;
    }
    stopRecording();
  };

  /**
   * Interrupt AI mid-reply (barge-in / cancel).
   */
  const handleInterrupt = () => {
    stopAudio();
    sendMessage({ type: 'interrupt' });
    setStatus('idle');
  };

  /**
   * Toggle TTS audio mute.
   */
  const handleToggleMute = () => {
    if (isPlaying) {
      stopAudio();
    }
    setTtsEnabled((prev) => !prev);
  };

  /**
   * Submit text message from input bar or quick suggestion chip.
   */
  const submitTextMessage = async (rawText) => {
    const content = rawText.trim();
    if (!content) return;

    stopAudio();
    setErrorMessage('');
    setPartialTranscript('');
    appendMessage('user', content);
    setTextInput('');
    setStatus('processing');
    streamingContentRef.current = '';
    currentTurnAudioRef.current = [];
    setStreamingContent('');

    const sentViaWs = sendMessage({
      type: 'text',
      content,
      tts_enabled: ttsEnabled,
      language,
    });

    if (!sentViaWs) {
      try {
        const res = await sendTextChat(sessionId, content);
        appendMessage('assistant', res.response, res.timestamp);
        setStatus('idle');
      } catch (err) {
        setErrorMessage(err?.response?.data?.detail || 'Failed to reach backend');
        setStatus('error');
      }
    }
  };

  /**
   * Start a fresh conversation.
   */
  const handleNewSession = () => {
    stopAudio();
    const fresh = uuidv4();
    setSessionId(fresh);
    setMessages([]);
    setStatus('idle');
    setErrorMessage('');
    setPartialTranscript('');
    setLatencyStats(null);
    streamingContentRef.current = '';
    setStreamingContent('');
  };

  /**
   * Replay an AI response audio.
   */
  const handleReplayAudio = (content, audioData) => {
    stopAudio();
    if (audioData) {
      setStatus('speaking');
      playAudio(audioData);
    } else if ('speechSynthesis' in window) {
      const utterance = new SpeechSynthesisUtterance(content);
      utterance.lang = language === 'en' ? 'en-US' : language;
      utterance.onstart = () => setStatus('speaking');
      utterance.onend = () => setStatus('idle');
      utterance.onerror = () => setStatus('idle');
      window.speechSynthesis.speak(utterance);
    }
  };

  /**
   * Keyboard shortcuts:
   * Space: Talk / Stop (when not in an input/textarea)
   * Esc: Interrupt AI mid-reply
   */
  useEffect(() => {
    const handleKeyDown = (e) => {
      const activeTag = document.activeElement?.tagName;
      const isInputFocused =
        activeTag === 'INPUT' ||
        activeTag === 'TEXTAREA' ||
        document.activeElement?.isContentEditable;

      if (e.key === 'Escape') {
        if (status === 'speaking' || status === 'processing' || isPlaying) {
          e.preventDefault();
          handleInterrupt();
        }
        return;
      }

      if (e.code === 'Space' && !isInputFocused) {
        e.preventDefault();
        if (isRecording) {
          handleStopRecording();
        } else {
          handleStartRecording();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleStartRecording, handleStopRecording, handleInterrupt, isPlaying, isRecording, status]);

  const orbStatus = isRecording ? 'recording' : status;

  const getStateLabel = () => {
    if (orbStatus === 'recording') return 'Listening…';
    if (orbStatus === 'processing') return 'Thinking…';
    if (orbStatus === 'speaking') return 'Speaking…';
    if (isAlwaysListening) return 'Always listening (Speak anytime)';
    return 'Tap orb to speak';
  };

  return (
    <div className="app-container">
      {/* Reconnecting banner if WebSocket drops */}
      {connectionStatus !== 'connected' && (
        <div className="reconnecting-banner" role="alert">
          <span className="reconnecting-dot" />
          <span>
            {connectionStatus === 'connecting'
              ? 'Reconnecting to TS Voice Assistant…'
              : 'Connection lost. Reconnecting automatically…'}
          </span>
        </div>
      )}

      {/* Slim Header */}
      <header className="slim-header">
        <div className="brand">
          <div className="brand__logo-badge">TS</div>
          <div className="brand__title-row">
            <h1 className="brand__title">
              <span className="brand__title-full">TS Voice Assistant</span>
              <span className="brand__title-short">TS Voice</span>
            </h1>
            <span
              className={`status-dot status-dot--${
                connectionStatus === 'connected' ? 'connected' : 'reconnecting'
              }`}
              title={
                connectionStatus === 'connected'
                  ? 'Connected to server'
                  : 'Reconnecting to server'
              }
              aria-label={
                connectionStatus === 'connected'
                  ? 'Connected status'
                  : 'Reconnecting status'
              }
            />
          </div>
        </div>

        <div className="header-actions">
          {/* Latency instrumentation pill */}
          {latencyStats && (
            <span
              className="latency-pill"
              title={latencyStats.summary}
              aria-label="Turn latency summary"
            >
              ⚡ {latencyStats.total_ms}ms
            </span>
          )}

          <button
            type="button"
            className="header-btn header-btn--new-chat"
            onClick={handleNewSession}
            aria-label="Start new chat"
          >
            + <span className="header-btn-text">New chat</span>
          </button>
          <button
            type="button"
            className="header-btn header-btn--icon"
            onClick={() => setShowSettings(true)}
            aria-label="Settings"
            title="Settings"
          >
            ⚙
          </button>
        </div>
      </header>

      {/* Chat Area - flex 1, scrolls, auto-scrolls to newest message */}
      <ChatHistory
        messages={messages}
        streamingContent={streamingContent}
        partialTranscript={partialTranscript}
        status={status}
        onQuickPrompt={submitTextMessage}
        onReplayAudio={handleReplayAudio}
      />

      {/* Bottom Voice Panel */}
      <section className="voice-panel">
        {/* Live waveform driven by AnalyserNode */}
        <AudioVisualizer
          isActive={isRecording}
          stream={mediaStream}
          isSpeaking={status === 'speaking' || isPlaying}
        />

        {/* 130px Voice Orb with 4 animated states */}
        <VoiceOrb
          status={orbStatus}
          onStartRecording={handleStartRecording}
          onStopRecording={handleStopRecording}
          onInterrupt={handleInterrupt}
        />

        {/* State label under orb */}
        <div className="state-label-container">
          <p className="state-label">{getStateLabel()}</p>
        </div>

        {/* Quick Voice Controls: Mute & Interrupt & VAD toggle */}
        <div className="voice-controls-bar">
          <button
            type="button"
            className={`control-pill-btn ${isAlwaysListening ? 'control-pill-btn--listening-mode' : ''}`}
            onClick={toggleAlwaysListening}
            aria-label="Toggle always listening VAD mode"
            title="Toggle always listening VAD"
          >
            {isAlwaysListening ? '🎙 VAD Active' : '🎙 Tap Mode'}
          </button>

          <button
            type="button"
            className={`control-pill-btn ${!ttsEnabled ? 'control-pill-btn--active' : ''}`}
            onClick={handleToggleMute}
            aria-label={ttsEnabled ? 'Mute AI voice output' : 'Unmute AI voice output'}
            title={ttsEnabled ? 'Mute AI voice' : 'Unmute AI voice'}
          >
            {ttsEnabled ? '🔊 Mute' : '🔇 Muted'}
          </button>

          {(status === 'speaking' || status === 'processing' || isPlaying) && (
            <button
              type="button"
              className="control-pill-btn control-pill-btn--interrupt"
              onClick={handleInterrupt}
              aria-label="Interrupt AI response"
              title="Interrupt AI (Esc)"
            >
              ⏹ Interrupt
            </button>
          )}
        </div>

        {/* Error notification banner if any */}
        {errorMessage && (
          <div className="voice-error-toast" role="alert">
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Text Input Bar */}
        <form
          className="text-input-form"
          onSubmit={(e) => {
            e.preventDefault();
            submitTextMessage(textInput);
          }}
        >
          <input
            type="text"
            className="text-input"
            value={textInput}
            onChange={(e) => setTextInput(e.target.value)}
            placeholder="Type a message or press Space to speak..."
            disabled={status === 'processing'}
            aria-label="Type message"
          />
          <button
            type="submit"
            className="send-button"
            disabled={!textInput.trim() || status === 'processing'}
            aria-label="Send message"
          >
            Send
          </button>
        </form>
      </section>

      {/* Settings Drawer Modal */}
      {showSettings && (
        <SettingsDrawer
          sessionId={sessionId}
          ttsEnabled={ttsEnabled}
          onToggleTts={setTtsEnabled}
          language={language}
          onChangeLanguage={setLanguage}
          theme={theme}
          onToggleTheme={setTheme}
          onSelectSession={setSessionId}
          onNewSession={handleNewSession}
          onClose={() => setShowSettings(false)}
        />
      )}
    </div>
  );
}
