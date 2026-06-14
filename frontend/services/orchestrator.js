// services/orchestrator.js – shared orchestrator run + polling UI

import { postJson, getJson } from '../api.js';
import { createProgressBar } from '../components/progress.js';
import { saveOrchestratorResult, setActiveRun } from '../state.js';
import { buildHash } from '../utils/hash.js';

const STEP_STATUS = {
  job_analysis: { label: 'JD Analyzer', done: false, active: true },
  resume_analysis: { label: 'Resume Analyzer', done: false, active: true },
  resume_match: { label: 'Resume Matcher', done: false, active: false },
  gap_analysis: { label: 'Gap Analysis', done: false, active: false },
  interview_research: { label: 'Interview Research', done: false, active: false },
  resume_rewrite: { label: 'Resume Rewrite', done: false, active: false },
  cover_letter: { label: 'Cover Letter', done: false, active: false },
};

function cloneStepStatus() {
  return Object.fromEntries(
    Object.entries(STEP_STATUS).map(([key, val]) => [key, { ...val }])
  );
}

function buildStepper(statusDiv, stepStatus, idPrefix) {
  const stepsList = document.createElement('div');
  stepsList.className = 'stepper';
  stepsList.setAttribute('aria-live', 'polite');
  statusDiv.appendChild(stepsList);

  const elapsedNote = document.createElement('p');
  elapsedNote.className = 'orchestrator-elapsed';
  elapsedNote.textContent = 'Analysis running in the background — you can stay on this page.';
  statusDiv.appendChild(elapsedNote);

  const startTime = Date.now();
  const elapsedTimer = setInterval(() => {
    const secs = Math.floor((Date.now() - startTime) / 1000);
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    elapsedNote.textContent = `Running in background (${mins}:${String(rem).padStart(2, '0')}) — you can stay on this page.`;
  }, 1000);

  let stepCounter = 1;
  for (const key in stepStatus) {
    const stepDiv = document.createElement('div');
    stepDiv.className = 'step';
    if (stepStatus[key].active) stepDiv.classList.add('active');
    stepDiv.id = `${idPrefix}-step-${key}`;

    const indicator = document.createElement('div');
    indicator.className = 'step-indicator';
    indicator.textContent = stepCounter++;
    indicator.id = `${idPrefix}-ind-${key}`;

    const label = document.createElement('div');
    label.className = 'step-label';
    label.textContent = stepStatus[key].label;

    stepDiv.appendChild(indicator);
    stepDiv.appendChild(label);
    stepsList.appendChild(stepDiv);
  }

  return { stepsList, elapsedTimer };
}

function updateStepperUI(stepStatus, idPrefix) {
  for (const key in stepStatus) {
    if (!stepStatus[key].done) continue;
    const stepDiv = document.getElementById(`${idPrefix}-step-${key}`);
    const ind = document.getElementById(`${idPrefix}-ind-${key}`);
    if (!stepDiv || !ind) continue;
    stepDiv.classList.remove('active');
    stepDiv.classList.add('completed');
    ind.textContent = '✓';
  }

  if (stepStatus.job_analysis.done && stepStatus.resume_analysis.done && !stepStatus.resume_match.done) {
    document.getElementById(`${idPrefix}-step-resume_match`)?.classList.add('active');
  }
  if (stepStatus.resume_match.done && !stepStatus.gap_analysis.done) {
    document.getElementById(`${idPrefix}-step-gap_analysis`)?.classList.add('active');
    document.getElementById(`${idPrefix}-step-interview_research`)?.classList.add('active');
  }
  if (stepStatus.gap_analysis.done && !stepStatus.resume_rewrite.done) {
    document.getElementById(`${idPrefix}-step-resume_rewrite`)?.classList.add('active');
  }
  if (stepStatus.resume_rewrite.done && !stepStatus.cover_letter.done) {
    document.getElementById(`${idPrefix}-step-cover_letter`)?.classList.add('active');
  }
}

function appendResultNav(statusDiv, jobId, resumeId) {
  const navContainer = document.createElement('div');
  navContainer.className = 'result-nav';

  const links = [
    { text: 'View All Results', hash: buildHash('#/results', { job: jobId, resume: resumeId, tab: 'match' }) },
    { text: 'Match Score', hash: buildHash('#/results/match', { job: jobId, resume: resumeId }) },
    { text: 'Gap Analysis', hash: buildHash('#/results/gaps', { job: jobId, resume: resumeId }) },
    { text: 'Resume Variants', hash: buildHash('#/results/variants', { job: jobId, resume: resumeId }) },
    { text: 'Interview Prep', hash: buildHash('#/results/interview', { job: jobId, resume: resumeId }) },
  ];

  links.forEach(({ text, hash }) => {
    const btn = document.createElement('button');
    btn.textContent = text;
    btn.onclick = () => { window.location.hash = hash; };
    navContainer.appendChild(btn);
  });

  statusDiv.appendChild(navContainer);
}


/**
 * Drive the orchestrator's background-only status polling UI.
 * The backend always runs in the background now, so this function:
 *   - POSTs `/api/orchestrate` (which is idempotent — a running run for this
 *     pair is returned as-is rather than starting a duplicate)
 *   - polls `/api/orchestrate/status/{job}/{resume}` until status is `complete`
 *     or `failed`
 *   - renders per-agent failure banners with a "retry this agent" button
 * @returns {Promise<object>} final status result
 */
export async function runOrchestrator({
  jobId,
  resumeId,
  body,
  statusDiv,
  idPrefix = 'orch',
}) {
  const prog = createProgressBar();
  statusDiv.appendChild(prog.element);
  prog.setProgress(10);

  let skipJob = body.skip_job_analysis;
  if (skipJob == null) {
    skipJob = false;
    try {
      await getJson(`/api/jobs/${jobId}/analysis`);
      skipJob = true;
    } catch (_) { }
  }

  const orchestrateBody = {
    job_id: jobId,
    resume_id: resumeId,
    skip_job_analysis: skipJob,
    skip_resume_analysis: body.skip_resume_analysis ?? false,
    skip_interview_research: body.skip_interview_research ?? false,
    force: body.force ?? false,
  };

  prog.setProgress(20);
  let finalResult = null;
  let elapsedTimer = null;
  const totalSteps = Object.keys(STEP_STATUS).length;

  try {
    // Idempotent: backend returns the existing run (running or complete) for
    // this pair unless `force=true`.
    await postJson('/api/orchestrate', orchestrateBody);
    const stepStatus = cloneStepStatus();
    ({ elapsedTimer } = buildStepper(statusDiv, stepStatus, idPrefix));

    let attempts = 0;
    const maxAttempts = 200;

    while (attempts < maxAttempts) {
      attempts++;
      await new Promise((r) => setTimeout(r, 3000));

      try {
        const statusRes = await getJson(`/api/orchestrate/status/${jobId}/${resumeId}`);
        let stepsDone = 0;

        for (const key in stepStatus) {
          if (!stepStatus[key].done && statusRes[`${key}_id`]) {
            stepStatus[key].done = true;
          }
          if (stepStatus[key].done) stepsDone++;
        }

        updateStepperUI(stepStatus, idPrefix);
        prog.setProgress(20 + Math.floor((stepsDone / totalSteps) * 70));

        if (statusRes.status === 'complete' || statusRes.status === 'failed') {
          finalResult = statusRes;
          break;
        }
      } catch (e) {
        console.error('Polling error:', e);
      }
    }

    if (!finalResult) {
      throw new Error('Polling timed out or failed.');
    }

    saveOrchestratorResult(jobId, resumeId, finalResult);
    setActiveRun(jobId, resumeId);

    window.dispatchEvent(new CustomEvent('orchestratorDone', {
      detail: { jobId, resumeId, result: finalResult },
    }));

    prog.complete();

    if (finalResult.status === 'complete') {
      appendResultNav(statusDiv, jobId, resumeId);
    } else {
      renderFailureBanner(statusDiv, jobId, resumeId, finalResult);
    }

    return finalResult;
  } finally {
    if (elapsedTimer) clearInterval(elapsedTimer);
  }
}


/** Render a banner explaining the failed run and offering single-agent retry. */
function renderFailureBanner(statusDiv, jobId, resumeId, result) {
  const wrap = document.createElement('div');
  wrap.className = 'failure-banner';

  const heading = document.createElement('p');
  heading.className = 'error-text';
  heading.textContent = `Analysis failed${result.error_code ? ` (${result.error_code})` : ''}.`;
  wrap.appendChild(heading);

  // Find which agents are in `failed` state.
  const statuses = result.agent_statuses || {};
  const failed = Object.entries(statuses)
    .filter(([, v]) => v && v.status === 'failed')
    .map(([k, v]) => ({ agent: k, ...v }));

  if (failed.length === 0) {
    statusDiv.appendChild(wrap);
    return;
  }

  failed.forEach(({ agent, error_code, error_detail }) => {
    const row = document.createElement('div');
    row.className = 'failure-row';
    const label = document.createElement('span');
    label.textContent = `${agent}: ${error_code || 'failed'}${error_detail ? ` — ${error_detail}` : ''}`;
    const btn = document.createElement('button');
    btn.textContent = `Retry ${agent}`;
    btn.onclick = async () => {
      btn.disabled = true;
      try {
        await postJson('/api/orchestrate/retry-agent', {
          job_id: jobId,
          resume_id: resumeId,
          agent,
        });
        wrap.remove();
        const newStatus = document.createElement('div');
        newStatus.className = 'orchestrator-status';
        statusDiv.appendChild(newStatus);
        // Poll again from scratch — backend will resume from this agent.
        await runOrchestrator({
          jobId,
          resumeId,
          body: { force: false },
          statusDiv: newStatus,
          idPrefix: `${agent}-retry`,
        });
      } catch (err) {
        btn.disabled = false;
        const e = document.createElement('p');
        e.className = 'error-text';
        e.textContent = `Retry failed: ${err.message}`;
        wrap.appendChild(e);
      }
    };
    row.appendChild(label);
    row.appendChild(btn);
    wrap.appendChild(row);
  });

  statusDiv.appendChild(wrap);
}
