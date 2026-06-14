// state.js – lightweight shared state backed by localStorage
// Screens that trigger the orchestrator write here.
// Screens that consume analysis results read from here.

const STORAGE_KEY = 'ai_job_copilot_state';
const PAYLOAD_SESSION_KEY = 'ai_job_copilot_extension_payload';

function _load() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}');
  } catch {
    return {};
  }
}

function _save(state) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {
    console.warn('State save failed', e);
  }
}

/** Persist a completed orchestrator response keyed by job+resume pair. */
export function saveOrchestratorResult(jobId, resumeId, result) {
  const state = _load();
  if (!state.runs) state.runs = {};
  state.runs[`${jobId}__${resumeId}`] = { ...result, _savedAt: Date.now() };
  state.activeRun = { jobId, resumeId, updatedAt: Date.now() };
  _save(state);
}

/** Retrieve the last orchestrator response for a job+resume pair, or null. */
export function getOrchestratorResult(jobId, resumeId) {
  const state = _load();
  return state.runs?.[`${jobId}__${resumeId}`] ?? null;
}

/** Merge a partial update (e.g. fresh resume_rewrite after regen) into the saved run. */
export function patchOrchestratorResult(jobId, resumeId, patch) {
  const state = _load();
  if (!state.runs) state.runs = {};
  const key = `${jobId}__${resumeId}`;
  state.runs[key] = { ...(state.runs[key] || {}), ...patch, _savedAt: Date.now() };
  _save(state);
}

/** List all stored [jobId, resumeId] pairs. */
export function listStoredRuns() {
  const state = _load();
  return Object.keys(state.runs || {}).map((key) => {
    const [jobId, resumeId] = key.split('__');
    return { jobId, resumeId, ...state.runs[key] };
  });
}

/** Track the most recently analyzed job+resume pair. */
export function setActiveRun(jobId, resumeId) {
  const state = _load();
  state.activeRun = { jobId, resumeId, updatedAt: Date.now() };
  _save(state);
}

export function getActiveRun() {
  const state = _load();
  return state.activeRun || null;
}

/** Most recently saved orchestrator run, or null. */
export function getLastStoredRun() {
  const runs = listStoredRuns();
  if (runs.length === 0) return null;
  return runs.sort((a, b) => (b._savedAt || 0) - (a._savedAt || 0))[0];
}

/** Resolve job/resume IDs from hash params, active run, or last stored run. */
export function resolveRunContext(hashParams) {
  const jobFromHash = hashParams?.get('job');
  const resumeFromHash = hashParams?.get('resume');
  if (jobFromHash && resumeFromHash) {
    return { jobId: jobFromHash, resumeId: resumeFromHash };
  }

  const active = getActiveRun();
  if (active?.jobId && active?.resumeId) {
    return { jobId: active.jobId, resumeId: active.resumeId };
  }

  const last = getLastStoredRun();
  if (last?.jobId && last?.resumeId) {
    return { jobId: last.jobId, resumeId: last.resumeId };
  }

  return { jobId: null, resumeId: null };
}

/** Persist extension payload across in-app navigation. */
export function saveExtensionPayload(payload) {
  try {
    sessionStorage.setItem(PAYLOAD_SESSION_KEY, payload);
  } catch (e) {
    console.warn('Extension payload save failed', e);
  }
}

export function getExtensionPayload() {
  try {
    return sessionStorage.getItem(PAYLOAD_SESSION_KEY);
  } catch {
    return null;
  }
}

export function clearExtensionPayload() {
  try {
    sessionStorage.removeItem(PAYLOAD_SESSION_KEY);
  } catch (_) {}
}

/** Whether any completed analysis runs exist. */
export function hasStoredRuns() {
  return listStoredRuns().length > 0;
}

// ─── Interview prep: local-only user questions & profile questions ───────────
// These live in localStorage by default. Users opt in to persist them to the
// DB via the "Save to research" buttons in the Interview tab.

function _interviewSlot(jobAnalysisId) {
  return `iv_user_${jobAnalysisId || 'unknown'}`;
}

function _profileSlot(jobAnalysisId, resumeId) {
  return `iv_profile_${jobAnalysisId || 'none'}__${resumeId || 'none'}`;
}

function _readSlot(slot) {
  const state = _load();
  return Array.isArray(state[slot]) ? state[slot] : [];
}

function _writeSlot(slot, list) {
  const state = _load();
  state[slot] = list;
  _save(state);
}

/** Get user-added interview questions for a job_analysis_id (oldest-first). */
export function getUserInterviewQuestions(jobAnalysisId) {
  return _readSlot(_interviewSlot(jobAnalysisId));
}

/** Prepend a new user-added interview question. Returns the updated list. */
export function addUserInterviewQuestion(jobAnalysisId, question) {
  const slot = _interviewSlot(jobAnalysisId);
  const list = _readSlot(slot);
  const text = (question?.question || '').trim();
  if (!text) return list;
  // Dedupe by trimmed/lowered text.
  const exists = list.some((q) => (q.question || '').trim().toLowerCase() === text.toLowerCase());
  if (exists) return list;
  const item = {
    question: text,
    category: question?.category || 'user',
    why_asked: question?.why_asked || '',
    strong_answer_tips: question?.strong_answer_tips || [],
    detailed_answer: question?.detailed_answer || null,
    source: 'user',
    _addedAt: Date.now(),
  };
  const next = [item, ...list];
  _writeSlot(slot, next);
  return next;
}

/** Remove a user-added interview question by trimmed/lowered text. */
export function removeUserInterviewQuestion(jobAnalysisId, questionText) {
  const slot = _interviewSlot(jobAnalysisId);
  const key = (questionText || '').trim().toLowerCase();
  const next = _readSlot(slot).filter(
    (q) => (q.question || '').trim().toLowerCase() !== key,
  );
  _writeSlot(slot, next);
  return next;
}

/** Patch a user-added question in place (e.g. attach a streamed detailed_answer). */
export function patchUserInterviewQuestion(jobAnalysisId, questionText, patch) {
  const slot = _interviewSlot(jobAnalysisId);
  const key = (questionText || '').trim().toLowerCase();
  const next = _readSlot(slot).map((q) =>
    (q.question || '').trim().toLowerCase() === key ? { ...q, ...patch } : q,
  );
  _writeSlot(slot, next);
  return next;
}

/** Get profile-generated questions for a (job_analysis_id, resume_id) pair. */
export function getProfileInterviewQuestions(jobAnalysisId, resumeId) {
  return _readSlot(_profileSlot(jobAnalysisId, resumeId));
}

/** Replace the profile-question list for a pair (e.g. after Generate). */
export function setProfileInterviewQuestions(jobAnalysisId, resumeId, questions) {
  const slot = _profileSlot(jobAnalysisId, resumeId);
  const list = (questions || []).map((q) => ({
    question: q.question,
    category: q.category || 'technical',
    why_asked: q.why_asked || '',
    strong_answer_tips: q.strong_answer_tips || [],
    detailed_answer: q.detailed_answer || null,
    source: 'profile',
    _addedAt: Date.now(),
  }));
  _writeSlot(slot, list);
  return list;
}

/** Remove one profile question by question text. */
export function removeProfileInterviewQuestion(jobAnalysisId, resumeId, questionText) {
  const slot = _profileSlot(jobAnalysisId, resumeId);
  const key = (questionText || '').trim().toLowerCase();
  const next = _readSlot(slot).filter(
    (q) => (q.question || '').trim().toLowerCase() !== key,
  );
  _writeSlot(slot, next);
  return next;
}

/** Patch a profile question in place (e.g. attach a streamed detailed_answer). */
export function patchProfileInterviewQuestion(jobAnalysisId, resumeId, questionText, patch) {
  const slot = _profileSlot(jobAnalysisId, resumeId);
  const key = (questionText || '').trim().toLowerCase();
  const next = _readSlot(slot).map((q) =>
    (q.question || '').trim().toLowerCase() === key ? { ...q, ...patch } : q,
  );
  _writeSlot(slot, next);
  return next;
}
