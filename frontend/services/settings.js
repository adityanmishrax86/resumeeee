// services/settings.js – fetch/cache LLM provider settings exposed by the backend.
//
// The backend never returns the API key value, only `has_api_key`. Frontend
// gating relies on the `configured` boolean returned by GET /api/settings.

import { getJson, postJson, deleteJson } from '../api.js';

let _cache = null;
let _pending = null;

const EVENT_NAME = 'settings:updated';

/** Subscribe to settings changes. Returns an unsubscribe function. */
export function onSettingsUpdated(handler) {
  window.addEventListener(EVENT_NAME, handler);
  return () => window.removeEventListener(EVENT_NAME, handler);
}

function _broadcast() {
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: _cache }));
}

/** Synchronous accessor for the last fetched settings. May return null. */
export function getCachedSettings() {
  return _cache;
}

/** True when the backend reports a usable provider+model+key. */
export function isConfigured() {
  return Boolean(_cache?.configured);
}

/** Fetch settings, deduping concurrent calls. Pass force=true to bypass cache. */
export async function loadSettings({ force = false } = {}) {
  if (_cache && !force) return _cache;
  if (_pending) return _pending;
  _pending = (async () => {
    try {
      _cache = await getJson('/api/settings');
    } catch (err) {
      _cache = { configured: false, source: 'none', provider: null, model: null, has_api_key: false, _error: err.message };
    } finally {
      _pending = null;
    }
    _broadcast();
    return _cache;
  })();
  return _pending;
}

export async function saveSettings({ provider, model, api_key }) {
  _cache = await postJson('/api/settings', { provider, model, api_key });
  _broadcast();
  return _cache;
}

export async function clearSettings() {
  _cache = await deleteJson('/api/settings');
  _broadcast();
  return _cache;
}
