// api.js – simple wrapper around fetch for the backend

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export { BASE_URL };

export async function getJson(path) {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  return res.json();
}

export async function postJson(path, body, timeoutMs = 330_000) {
  const controller = new AbortController();
  const timerId = setTimeout(() => controller.abort(), timeoutMs);
  let res;
  try {
    res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timerId);
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  return res.json();
}

/** DELETE request. Returns null on 204 No Content. */
export async function deleteJson(path) {
  const res = await fetch(`${BASE_URL}${path}`, { method: 'DELETE' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  if (res.status === 204) return null;
  return res.json().catch(() => null);
}

/**
 * POST a JSON body and consume an SSE response stream.
 *
 * Each `data: <token>` event is unescaped (\\n → \n) and passed to `onChunk`.
 * The promise resolves once the server emits `data: [DONE]` or the stream
 * ends. Pass an `AbortSignal` to cancel mid-stream.
 *
 * @param {string} path
 * @param {object} body
 * @param {(chunk: string) => void} onChunk
 * @param {{ signal?: AbortSignal }} [opts]
 */
export async function streamPost(path, body, onChunk, opts = {}) {
  const { signal } = opts;
  const res = await fetch(`${BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify(body),
    signal,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Error ${res.status}`);
  }
  if (!res.body) {
    throw new Error('Streaming not supported by this browser');
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE events are separated by a blank line (\n\n).
      let sepIdx;
      while ((sepIdx = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, sepIdx);
        buffer = buffer.slice(sepIdx + 2);

        const dataLines = [];
        let isError = false;
        for (const line of rawEvent.split('\n')) {
          if (line.startsWith('event:') && line.slice(6).trim() === 'error') {
            isError = true;
          } else if (line.startsWith('data:')) {
            dataLines.push(line.slice(5).trimStart());
          }
        }
        if (dataLines.length === 0) continue;

        const payload = dataLines.join('\n');
        if (isError) throw new Error(payload || 'Stream error');
        if (payload === '[DONE]') return;
        // Restore escaped newlines from the server.
        const text = payload.replace(/\\n/g, '\n');
        onChunk(text);
      }
    }
  } finally {
    try { reader.releaseLock(); } catch (_) {}
  }
}

/** Lightweight backend connectivity check. */
export async function checkBackendHealth() {
  try {
    const res = await fetch(`${BASE_URL}/docs`, { method: 'HEAD' });
    return res.ok;
  } catch {
    try {
      const res = await fetch(`${BASE_URL}/api/jobs`, { method: 'GET' });
      return res.status !== 0;
    } catch {
      return false;
    }
  }
}
