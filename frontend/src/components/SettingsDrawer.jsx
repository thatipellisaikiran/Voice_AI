import React, { useEffect, useState } from 'react';
import { deleteSession, getHealth, getSessions } from '../services/api';

const LANGUAGES = [
  { code: 'en', label: 'English (en)' },
  { code: 'es', label: 'Spanish (es)' },
  { code: 'fr', label: 'French (fr)' },
  { code: 'de', label: 'German (de)' },
  { code: 'hi', label: 'Hindi (hi)' },
  { code: 'ja', label: 'Japanese (ja)' },
];

export function SettingsDrawer({
  sessionId,
  ttsEnabled,
  onToggleTts,
  language,
  onChangeLanguage,
  theme,
  onToggleTheme,
  onSelectSession,
  onNewSession,
  onClose,
}) {
  const [sessions, setSessions] = useState([]);
  const [health, setHealth] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadDrawerData = async () => {
    setLoading(true);
    try {
      const [sessionsRes, healthRes] = await Promise.allSettled([
        getSessions(),
        getHealth(),
      ]);
      if (sessionsRes.status === 'fulfilled') setSessions(sessionsRes.value || []);
      if (healthRes.status === 'fulfilled') setHealth(healthRes.value || null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDrawerData();
  }, [sessionId]);

  const handleDeleteSession = async (id) => {
    try {
      await deleteSession(id);
      if (id === sessionId) {
        onNewSession();
      } else {
        setSessions((prev) => prev.filter((item) => item.id !== id));
      }
    } catch {
      // Ignore delete error in UI
    }
  };

  return (
    <div className="drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        className="settings-drawer"
        onClick={(e) => e.stopPropagation()}
        aria-label="Settings and Sessions"
      >
        <div className="settings-drawer__header">
          <h3>Settings</h3>
          <button
            type="button"
            className="icon-btn close-btn"
            onClick={onClose}
            aria-label="Close settings drawer"
          >
            ✕
          </button>
        </div>

        {/* Appearance Section */}
        <section className="settings-section">
          <h4>Appearance</h4>
          <label className="setting-toggle">
            <div>
              <span className="toggle-label">Dark Mode</span>
              <p className="toggle-hint">Switch between clean light and dark themes</p>
            </div>
            <input
              type="checkbox"
              checked={theme === 'dark'}
              onChange={(e) => onToggleTheme(e.target.checked ? 'dark' : 'light')}
              aria-label="Toggle dark mode"
            />
          </label>
        </section>

        {/* Voice Preferences Section */}
        <section className="settings-section">
          <h4>Voice & Audio</h4>
          <label className="setting-toggle">
            <div>
              <span className="toggle-label">Speak AI Responses (gTTS)</span>
              <p className="toggle-hint">Synthesize voice for AI replies automatically</p>
            </div>
            <input
              type="checkbox"
              checked={ttsEnabled}
              onChange={(e) => onToggleTts(e.target.checked)}
              aria-label="Toggle AI speech synthesis"
            />
          </label>

          <label className="setting-field">
            <span className="field-label">Speech Language</span>
            <select
              value={language}
              onChange={(e) => onChangeLanguage(e.target.value)}
              aria-label="Select speech language"
            >
              {LANGUAGES.map((lang) => (
                <option key={lang.code} value={lang.code}>
                  {lang.label}
                </option>
              ))}
            </select>
          </label>
        </section>

        {/* Keyboard Shortcuts Guide */}
        <section className="settings-section">
          <h4>Keyboard Shortcuts</h4>
          <div className="shortcuts-list">
            <div className="shortcut-item">
              <kbd>Space</kbd>
              <span>Talk / Stop recording</span>
            </div>
            <div className="shortcut-item">
              <kbd>Esc</kbd>
              <span>Interrupt AI mid-reply</span>
            </div>
            <div className="shortcut-item">
              <kbd>Enter</kbd>
              <span>Send text message</span>
            </div>
          </div>
        </section>

        {/* Sessions Section */}
        <section className="settings-section">
          <div className="section-title-row">
            <h4>Conversation History</h4>
            <button
              type="button"
              className="new-chat-small-btn"
              onClick={() => {
                onNewSession();
                onClose();
              }}
              aria-label="Start new conversation"
            >
              + New
            </button>
          </div>

          {loading ? (
            <p className="settings-muted">Loading conversations…</p>
          ) : sessions.length === 0 ? (
            <p className="settings-muted">No saved conversations yet.</p>
          ) : (
            <ul className="sessions-list" role="list">
              {sessions.map((item) => (
                <li
                  key={item.id}
                  className={`session-item ${item.id === sessionId ? 'session-item--active' : ''}`}
                >
                  <button
                    type="button"
                    className="session-item__title"
                    onClick={() => {
                      onSelectSession(item.id);
                      onClose();
                    }}
                    aria-label={`Open conversation ${item.title || item.id}`}
                  >
                    <span>{item.title || `Chat ${item.id.slice(0, 8)}`}</span>
                  </button>
                  <button
                    type="button"
                    className="session-item__delete"
                    onClick={() => handleDeleteSession(item.id)}
                    aria-label="Delete conversation"
                    title="Delete session"
                  >
                    🗑
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* System Health */}
        {health && (
          <footer className="settings-drawer__footer">
            <span className="health-badge">
              Status: <strong>{health.status}</strong>
            </span>
            <span className="health-detail">
              Model: {health.whisper_model} · Groq LLaMA
            </span>
          </footer>
        )}
      </aside>
    </div>
  );
}
