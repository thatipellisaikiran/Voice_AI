import React from 'react';

function MicIcon() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
      <path
        d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function StopSquareIcon() {
  return (
    <svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" />
    </svg>
  );
}

function SpinnerCircle() {
  return (
    <svg className="orb-spinner-svg" width="40" height="40" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2.8" opacity="0.25" />
      <path
        d="M12 3a9 9 0 0 1 9 9"
        stroke="currentColor"
        strokeWidth="2.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SoundWaveIcon() {
  return (
    <div className="orb-soundbars" aria-hidden="true">
      <span className="soundbar soundbar--1" />
      <span className="soundbar soundbar--2" />
      <span className="soundbar soundbar--3" />
      <span className="soundbar soundbar--4" />
      <span className="soundbar soundbar--5" />
    </div>
  );
}

export function VoiceOrb({
  status, // 'idle' | 'recording' | 'processing' | 'speaking' | 'error'
  onStartRecording,
  onStopRecording,
  onInterrupt,
}) {
  const isListening = status === 'recording';
  const isThinking = status === 'processing';
  const isSpeaking = status === 'speaking';

  const handleClick = () => {
    if (isListening) {
      onStopRecording?.();
    } else if (isThinking || isSpeaking) {
      onInterrupt?.();
    } else {
      onStartRecording?.();
    }
  };

  const getAriaLabel = () => {
    if (isListening) return 'Listening to you. Tap to stop recording';
    if (isThinking) return 'Thinking. Tap to interrupt';
    if (isSpeaking) return 'Speaking. Tap to interrupt';
    return 'Tap to speak with TS Voice Assistant';
  };

  return (
    <div className="voice-orb-wrapper">
      {/* Outer pulsing rings for Listening state */}
      {isListening && (
        <div className="pulse-rings-container" aria-hidden="true">
          <span className="listening-pulse listening-pulse--1" />
          <span className="listening-pulse listening-pulse--2" />
          <span className="listening-pulse listening-pulse--3" />
        </div>
      )}

      {/* Rotating conic gradient ring for Thinking state */}
      {isThinking && <div className="thinking-spin-ring" aria-hidden="true" />}

      {/* Ripple wave rings for Speaking state */}
      {isSpeaking && (
        <div className="speaking-ripples" aria-hidden="true">
          <span className="speaking-ripple speaking-ripple--1" />
          <span className="speaking-ripple speaking-ripple--2" />
        </div>
      )}

      <button
        type="button"
        className={`voice-orb voice-orb--${status}`}
        onClick={handleClick}
        aria-label={getAriaLabel()}
        title={getAriaLabel()}
      >
        <span className="voice-orb__glass" />
        <span className="voice-orb__content">
          {isListening ? (
            <StopSquareIcon />
          ) : isThinking ? (
            <SpinnerCircle />
          ) : isSpeaking ? (
            <SoundWaveIcon />
          ) : (
            <MicIcon />
          )}
        </span>
      </button>
    </div>
  );
}
