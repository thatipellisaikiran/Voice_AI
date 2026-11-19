import React, { useEffect, useRef } from 'react';
import { MessageBubble } from './MessageBubble';

const SUGGESTION_CHIPS = [
  'What can you do?',
  'Tell me a joke',
  "Summarize today's news",
];

function MicPulsingIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="2" width="6" height="12" rx="3" fill="currentColor" />
      <path
        d="M5 10a7 7 0 0 0 14 0M12 17v5M8 22h8"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function ChatHistory({
  messages,
  streamingContent,
  partialTranscript = '',
  status = 'idle',
  onQuickPrompt,
  onReplayAudio,
}) {
  const scrollContainerRef = useRef(null);
  const bottomAnchorRef = useRef(null);

  // Auto-scroll to bottom on new messages, tokens, or partial transcript
  useEffect(() => {
    if (bottomAnchorRef.current) {
      bottomAnchorRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, streamingContent, partialTranscript, status]);

  const isEmpty = messages.length === 0 && !streamingContent && !partialTranscript;
  const isAiThinking = status === 'processing' && !streamingContent;

  return (
    <div className="chat-area" ref={scrollContainerRef}>
      {isEmpty ? (
        <div className="chat-empty">
          <div className="chat-empty__orb-hint" />
          <h2 className="chat-empty__title">How can I help you today?</h2>
          <p className="chat-empty__subtitle">
            Speak naturally with TS using real-time voice, or type your message below.
          </p>
          <div className="chat-empty__chips" role="group" aria-label="Suggested questions">
            {SUGGESTION_CHIPS.map((chip) => (
              <button
                key={chip}
                type="button"
                className="suggestion-chip"
                onClick={() => onQuickPrompt?.(chip)}
              >
                {chip}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="chat-messages">
          {messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              role={msg.role}
              content={msg.content}
              timestamp={msg.timestamp}
              audioData={msg.audioData}
              onReplay={onReplayAudio}
            />
          ))}

          {/* Live partial transcript dashed bubble while user is speaking */}
          {partialTranscript && (
            <div className="message message--user message--partial">
              <div className="message__avatar" aria-hidden="true">
                <MicPulsingIcon />
              </div>
              <div className="message__container">
                <div className="message__bubble dashed-bubble">
                  <p className="message__user-text">
                    {partialTranscript}
                    <span className="live-speech-pulse" aria-hidden="true">...</span>
                  </p>
                </div>
                <span className="message__time">Listening live...</span>
              </div>
            </div>
          )}

          {/* Streaming AI response */}
          {streamingContent && (
            <MessageBubble
              role="assistant"
              content={streamingContent}
              timestamp={new Date().toISOString()}
              isStreaming
            />
          )}

          {/* Typing indicator (three bouncing dots) while AI generates before first token */}
          {isAiThinking && (
            <div className="message message--assistant message--thinking">
              <div className="message__avatar" aria-hidden="true">
                <span className="ts-small-badge">TS</span>
              </div>
              <div className="message__container">
                <div className="message__bubble typing-indicator-bubble">
                  <div className="typing-indicator" aria-label="TS is thinking">
                    <span className="dot" />
                    <span className="dot" />
                    <span className="dot" />
                  </div>
                </div>
              </div>
            </div>
          )}

          <div ref={bottomAnchorRef} style={{ height: 1 }} />
        </div>
      )}
    </div>
  );
}
