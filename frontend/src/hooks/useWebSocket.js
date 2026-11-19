import { useCallback, useEffect, useRef, useState } from 'react';

const MAX_RECONNECT_ATTEMPTS = 5;
const KEEPALIVE_INTERVAL_MS = 30000;

function resolveWsUrl(sessionId) {
  const configured = import.meta.env.VITE_WS_URL;
  if (configured) {
    return `${configured.replace(/\/$/, '')}/ws/voice/${sessionId}`;
  }
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws/voice/${sessionId}`;
}

export function useWebSocket(sessionId, onMessage) {
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [lastMessage, setLastMessage] = useState(null);

  const wsRef = useRef(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef(null);
  const keepaliveTimerRef = useRef(null);
  const manualCloseRef = useRef(false);
  const onMessageRef = useRef(onMessage);

  useEffect(() => {
    onMessageRef.current = onMessage;
  }, [onMessage]);

  useEffect(() => {
    if (!sessionId) return undefined;

    manualCloseRef.current = false;
    reconnectAttemptsRef.current = 0;

    const clearTimers = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      if (keepaliveTimerRef.current) {
        clearInterval(keepaliveTimerRef.current);
        keepaliveTimerRef.current = null;
      }
    };

    const connect = () => {
      clearTimers();
      setConnectionStatus('connecting');

      const ws = new WebSocket(resolveWsUrl(sessionId));
      wsRef.current = ws;

      ws.onopen = () => {
        setConnectionStatus('connected');
        reconnectAttemptsRef.current = 0;
        keepaliveTimerRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: 'ping' }));
          }
        }, KEEPALIVE_INTERVAL_MS);
      };

      ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data);
          setLastMessage(parsed);
          if (onMessageRef.current) {
            onMessageRef.current(parsed);
          }
        } catch {
          // Ignore malformed payloads
        }
      };

      ws.onerror = () => {
        setConnectionStatus('error');
      };

      ws.onclose = () => {
        clearTimers();
        if (manualCloseRef.current) {
          setConnectionStatus('disconnected');
          return;
        }
        setConnectionStatus('disconnected');
        if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          const delayMs = 1000 * 2 ** reconnectAttemptsRef.current;
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = setTimeout(connect, delayMs);
        }
      };
    };

    connect();

    return () => {
      manualCloseRef.current = true;
      clearTimers();
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [sessionId]);

  const sendMessage = useCallback((payload) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }, []);

  return { sendMessage, lastMessage, connectionStatus };
}

