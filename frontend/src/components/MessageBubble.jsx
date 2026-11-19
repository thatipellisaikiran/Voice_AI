import React, { useState } from 'react';
import { MarkdownRenderer } from './MarkdownRenderer';

function formatTime(timestamp) {
  if (!timestamp) return '';
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function UserIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="8" r="4" stroke="currentColor" strokeWidth="2" />
      <path
        d="M5 20a7 7 0 0 1 14 0"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function AIIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M12 3l2.2 4.8L19 10l-4.8 2.2L12 17l-2.2-4.8L5 10l4.8-2.2L12 3Z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" strokeWidth="2" />
      <path
        d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function SpeakerIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M11 5L6 9H2v6h4l5 4V5z"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M15.54 8.46a5 5 0 0 1 0 7.07"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
      <path
        d="M19.07 4.93a10 10 0 0 1 0 14.14"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

export function MessageBubble({
  role,
  content,
  timestamp,
  audioData = null,
  isStreaming = false,
  onReplay = null,
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Ignore clipboard write failures
    }
  };

  const handleReplay = () => {
    if (onReplay) {
      onReplay(content, audioData);
    }
  };

  const isUser = role === 'user';

  return (
    <div className={`message message--${role} ${isStreaming ? 'message--streaming' : ''}`}>
      <div className="message__avatar" aria-hidden="true">
        {isUser ? <UserIcon /> : <AIIcon />}
      </div>
      <div className="message__container">
        <div className="message__bubble">
          {isUser ? (
            <p className="message__user-text">{content}</p>
          ) : (
            <>
              <MarkdownRenderer content={content} />
              {isStreaming && <span className="streaming-cursor" aria-hidden="true" />}
            </>
          )}
        </div>

        <div className="message__footer">
          {timestamp && <span className="message__time">{formatTime(timestamp)}</span>}

          {!isUser && !isStreaming && (
            <div className="message__actions">
              <button
                type="button"
                className="message-action-btn"
                onClick={handleCopy}
                aria-label="Copy AI message"
                title="Copy text"
              >
                <CopyIcon />
                <span>{copied ? 'Copied!' : 'Copy'}</span>
              </button>

              <button
                type="button"
                className="message-action-btn"
                onClick={handleReplay}
                aria-label="Replay audio for this message"
                title="Replay audio"
              >
                <SpeakerIcon />
                <span>Replay</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
