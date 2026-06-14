// utils/hash.js – hash routing helpers

/** Route path without query string (e.g. "#/quick-start"). */
export function getRoutePath() {
  const hash = location.hash || '#/home';
  return hash.split('?')[0] || '#/home';
}

/** Query params from the hash fragment. */
export function getHashParams() {
  const hash = location.hash || '';
  const query = hash.split('?')[1];
  if (!query) return new URLSearchParams();
  return new URLSearchParams(query);
}

/** Build a hash URL with optional query params. */
export function buildHash(path, params = {}) {
  const base = path.split('?')[0];
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== '');
  if (entries.length === 0) return base;
  const qs = new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
  return `${base}?${qs}`;
}
