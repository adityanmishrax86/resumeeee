// polling.js – helper for simple polling of a GET endpoint until success or timeout

import { BASE_URL } from './api.js';

/**
 * Poll a URL repeatedly until the response is ok (status 200) or maxAttempts reached.
 * @param {string} path - API path (e.g., `/api/jobs/${jobId}/analysis`)
 * @param {number} intervalMs - interval between attempts (default 3000ms)
 * @param {number} maxAttempts - maximum attempts (default 20)
 * @returns {Promise<any>} - resolves with JSON data when successful
 */
export async function poll(path, intervalMs = 3000, maxAttempts = 20) {
  for (let i = 0; i < maxAttempts; i++) {
    try {
      const res = await fetch(`${BASE_URL}${path}`);
      if (res.ok) return await res.json();
    } catch (_) {
      // ignore network errors and continue polling
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error('Polling timed out');
}
