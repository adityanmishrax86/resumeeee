// services/results_loaders.js – load result data for the results hub tabs

import { getJson, postJson } from '../api.js';
import { getOrchestratorResult } from '../state.js';

export async function loadMatchData(jobId, resumeId) {
  let jobAnalysisId = null;
  const saved = getOrchestratorResult(jobId, resumeId);
  if (saved?.job_analysis_id) {
    jobAnalysisId = saved.job_analysis_id;
  } else {
    try {
      const analysis = await getJson(`/api/jobs/${jobId}/analysis`);
      jobAnalysisId = analysis?.id ?? analysis?.job_analysis_id ?? null;
    } catch (_) {}
  }

  if (!jobAnalysisId) {
    throw new Error('No job analysis found. Run analysis first.');
  }

  if (saved?.resume_match) {
    return saved.resume_match;
  }

  return postJson('/api/resumes/match', {
    resume_id: resumeId,
    job_analysis_id: jobAnalysisId,
  });
}

export function loadGapData(jobId, resumeId) {
  const saved = getOrchestratorResult(jobId, resumeId);
  if (!saved) throw new Error('No analysis found for this pair. Run analysis first.');
  if (!saved.gap_analysis) {
    throw new Error('Gap analysis data is not available yet.');
  }
  return saved.gap_analysis;
}

export function loadVariantsData(jobId, resumeId) {
  const saved = getOrchestratorResult(jobId, resumeId);
  if (!saved) throw new Error('No analysis found for this pair. Run analysis first.');
  if (!saved.resume_rewrite) {
    throw new Error('Resume rewrite data is not available yet.');
  }
  return saved.resume_rewrite;
}

export function loadInterviewData(jobId, resumeId) {
  const saved = getOrchestratorResult(jobId, resumeId);
  if (!saved) throw new Error('No analysis found for this pair. Run analysis first.');
  if (!saved.interview_research) {
    throw new Error('Interview research data is not available yet.');
  }
  return saved.interview_research;
}

export function loadCoverLetterData(jobId, resumeId) {
  const saved = getOrchestratorResult(jobId, resumeId);
  if (!saved) return null;
  return saved.cover_letter || null;
}

/** Populate job/resume dropdowns; returns { jobs, resumes }. */
export async function fetchJobResumeOptions() {
  const [jobs, resumes] = await Promise.all([
    getJson('/api/jobs'),
    getJson('/api/resumes'),
  ]);
  return { jobs, resumes };
}

export function fillJobSelect(select, jobs, selectedId) {
  select.innerHTML = '';
  if (!jobs.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No jobs — ingest one first';
    select.appendChild(opt);
    return;
  }
  jobs.forEach((j) => {
    const opt = document.createElement('option');
    opt.value = j.id;
    opt.textContent = `${j.role_title || 'Untitled'} @ ${j.company_name || 'Unknown'}`;
    if (selectedId && j.id === selectedId) opt.selected = true;
    select.appendChild(opt);
  });
}

export function fillResumeSelect(select, resumes, selectedId) {
  select.innerHTML = '';
  if (!resumes.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = 'No resumes — upload one first';
    select.appendChild(opt);
    return;
  }
  resumes.forEach((r) => {
    const opt = document.createElement('option');
    opt.value = r.id;
    opt.textContent = `${r.name}${r.is_master ? ' (Master)' : ''}`;
    if (selectedId && r.id === selectedId) opt.selected = true;
    select.appendChild(opt);
  });
}
