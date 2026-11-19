import axios from 'axios';

const baseURL = import.meta.env.VITE_API_URL || '';

const api = axios.create({
  baseURL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export async function getHealth() {
  const { data } = await api.get('/health');
  return data;
}

export async function sendTextChat(sessionId, message) {
  const { data } = await api.post('/api/chat', {
    session_id: sessionId,
    message,
  });
  return data;
}

export async function getSessions() {
  const { data } = await api.get('/api/sessions');
  return data;
}

export async function getSessionHistory(sessionId) {
  const { data } = await api.get(`/api/sessions/${sessionId}/history`);
  return data;
}

export async function deleteSession(sessionId) {
  const { data } = await api.delete(`/api/sessions/${sessionId}`);
  return data;
}

export default api;

