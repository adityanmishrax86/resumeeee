// services/orchestrator.js – shared orchestrator run + polling UI
// Renders a DAG-style pipeline flow graph instead of a linear stepper.

import { postJson, getJson } from '../api.js';
import { createProgressBar } from '../components/progress.js';
import { saveOrchestratorResult, setActiveRun } from '../state.js';
import { buildHash } from '../utils/hash.js';

// ─── Agent metadata ──────────────────────────────────────────────────────────
// Each agent knows its key (matches status response), display label, and SVG
// icon path data. The DAG layout is defined separately in PIPELINE_ROWS.

const AGENTS = {
  job_analysis: {
    label: 'JD Analyzer',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
    description: 'Analyzes the job description to extract key requirements',
  },
  resume_analysis: {
    label: 'Resume Analyzer',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><rect x="8" y="2" width="8" height="4" rx="1" ry="1"/><path d="M9 14l2 2 4-4"/></svg>`,
    description: 'Parses and evaluates your resume content',
  },
  resume_match: {
    label: 'Resume Matcher',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><path d="M11 8v6"/><path d="M8 11h6"/></svg>`,
    description: 'Matches resume skills against job requirements',
  },
  gap_analysis: {
    label: 'Gap Analysis',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21.21 15.89A10 10 0 1 1 8 2.83"/><path d="M22 12A10 10 0 0 0 12 2v10z"/></svg>`,
    description: 'Identifies gaps between your profile and the role',
  },
  resume_rewrite: {
    label: 'Resume Rewriter',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>`,
    description: 'Rewrites your resume tailored to the job',
  },
  cover_letter: {
    label: 'Cover Letter',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg>`,
    description: 'Generates a tailored cover letter',
  },
  interview_research: {
    label: 'Interview Prep',
    icon: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><line x1="12" y1="19" x2="12" y2="23"/><line x1="8" y1="23" x2="16" y2="23"/></svg>`,
    description: 'Researches company & prepares interview questions',
  },
};

// The DAG layout — each row is a tier of agents that run in parallel.
// `connectorType` indicates how this row connects to the row above.
const PIPELINE_ROWS = [
  { agents: ['job_analysis', 'resume_analysis'], connectorType: null },
  { agents: ['resume_match'], connectorType: 'merge' },    // 2→1: merge
  { agents: ['gap_analysis'], connectorType: 'single' },   // 1→1
  { agents: ['resume_rewrite', 'cover_letter', 'interview_research'], connectorType: 'fan' }, // 1→3: fan-out
];

const STATUS_LABELS = {
  pending: 'Waiting',
  running: 'Running…',
  complete: 'Done',
  failed: 'Failed',
  skipped: 'Skipped',
};

const STATUS_ICONS = {
  pending: '⏳',
  running: '⚡',
  complete: '✓',
  failed: '✗',
  skipped: '⏭',
};

// ─── Build the pipeline flow DOM ─────────────────────────────────────────────

function buildPipelineFlow(statusDiv, stepStatus, idPrefix) {
  const flow = document.createElement('div');
  flow.className = 'pipeline-flow';
  flow.id = `${idPrefix}-pipeline`;

  PIPELINE_ROWS.forEach((row, rowIdx) => {
    // Connector between rows
    if (row.connectorType && rowIdx > 0) {
      const connector = document.createElement('div');
      connector.className = `pipeline-connector pipeline-connector--${row.connectorType}`;
      connector.id = `${idPrefix}-conn-${rowIdx}`;

      if (row.connectorType === 'merge') {
        // Two lines merging into one
        connector.innerHTML = `
          <svg class="pipeline-conn-svg" viewBox="0 0 200 32" preserveAspectRatio="none">
            <path d="M 50,0 L 100,32" class="pipeline-conn-line" />
            <path d="M 150,0 L 100,32" class="pipeline-conn-line" />
          </svg>`;
      } else if (row.connectorType === 'fan') {
        // One line fanning into three
        const count = row.agents.length;
        let paths = '';
        for (let i = 0; i < count; i++) {
          const x = (100 / (count + 1)) * (i + 1);
          paths += `<path d="M 50,0 L ${x},32" class="pipeline-conn-line" />`;
        }
        connector.innerHTML = `
          <svg class="pipeline-conn-svg" viewBox="0 0 100 32" preserveAspectRatio="none">
            ${paths}
          </svg>`;
      } else {
        // Single vertical line
        connector.innerHTML = `
          <svg class="pipeline-conn-svg" viewBox="0 0 100 32" preserveAspectRatio="none">
            <path d="M 50,0 L 50,32" class="pipeline-conn-line" />
          </svg>`;
      }
      flow.appendChild(connector);
    }

    // Row of agent nodes
    const rowDiv = document.createElement('div');
    rowDiv.className = 'pipeline-row';
    if (row.agents.length > 1) rowDiv.classList.add('pipeline-row--parallel');

    row.agents.forEach((agentKey) => {
      const meta = AGENTS[agentKey];
      const status = stepStatus[agentKey]?.status || 'pending';

      const node = document.createElement('div');
      node.className = `pipeline-node pipeline-node--${status}`;
      node.id = `${idPrefix}-node-${agentKey}`;
      node.setAttribute('data-agent', agentKey);

      // Icon container
      const iconWrap = document.createElement('div');
      iconWrap.className = 'pipeline-node__icon';
      iconWrap.innerHTML = meta.icon;

      // Status badge
      const badge = document.createElement('div');
      badge.className = `pipeline-node__badge pipeline-node__badge--${status}`;
      badge.id = `${idPrefix}-badge-${agentKey}`;
      badge.textContent = STATUS_ICONS[status] || '⏳';

      // Label
      const label = document.createElement('div');
      label.className = 'pipeline-node__label';
      label.textContent = meta.label;

      // Status text
      const statusText = document.createElement('div');
      statusText.className = 'pipeline-node__status';
      statusText.id = `${idPrefix}-status-${agentKey}`;
      statusText.textContent = STATUS_LABELS[status] || 'Waiting';

      // Tooltip (shown on hover)
      const tooltip = document.createElement('div');
      tooltip.className = 'pipeline-tooltip';
      tooltip.id = `${idPrefix}-tip-${agentKey}`;
      tooltip.innerHTML = `
        <div class="pipeline-tooltip__title">${meta.label}</div>
        <div class="pipeline-tooltip__desc">${meta.description}</div>
        <div class="pipeline-tooltip__status">Status: <strong>${STATUS_LABELS[status]}</strong></div>
      `;

      node.appendChild(iconWrap);
      node.appendChild(badge);
      node.appendChild(label);
      node.appendChild(statusText);
      node.appendChild(tooltip);
      rowDiv.appendChild(node);
    });

    flow.appendChild(rowDiv);
  });

  // Elapsed timer
  const elapsedNote = document.createElement('p');
  elapsedNote.className = 'pipeline-elapsed';
  elapsedNote.textContent = 'Analysis running — you can stay on this page.';

  const startTime = Date.now();
  const elapsedTimer = setInterval(() => {
    const secs = Math.floor((Date.now() - startTime) / 1000);
    const mins = Math.floor(secs / 60);
    const rem = secs % 60;
    elapsedNote.textContent = `Running (${mins}:${String(rem).padStart(2, '0')}) — you can stay on this page.`;
  }, 1000);

  statusDiv.appendChild(flow);
  statusDiv.appendChild(elapsedNote);

  return { flow, elapsedTimer };
}


// ─── Update pipeline nodes in real-time ──────────────────────────────────────

function updatePipelineUI(stepStatus, agentStatuses, idPrefix) {
  for (const agentKey in stepStatus) {
    const step = stepStatus[agentKey];
    const node = document.getElementById(`${idPrefix}-node-${agentKey}`);
    const badge = document.getElementById(`${idPrefix}-badge-${agentKey}`);
    const statusEl = document.getElementById(`${idPrefix}-status-${agentKey}`);
    const tip = document.getElementById(`${idPrefix}-tip-${agentKey}`);
    if (!node) continue;

    let status = 'pending';
    const agentDetail = agentStatuses?.[agentKey] || agentStatuses?.[`${agentKey}`];

    if (step.done) {
      status = agentDetail?.status === 'failed' ? 'failed'
             : agentDetail?.status === 'skipped' ? 'skipped'
             : 'complete';
    } else if (agentDetail?.status === 'running') {
      status = 'running';
    } else if (agentDetail?.status === 'failed') {
      status = 'failed';
      step.done = true;
    }

    // Remove old status classes and apply new
    node.className = `pipeline-node pipeline-node--${status}`;
    if (badge) {
      badge.className = `pipeline-node__badge pipeline-node__badge--${status}`;
      badge.textContent = STATUS_ICONS[status] || '⏳';
    }
    if (statusEl) {
      statusEl.textContent = STATUS_LABELS[status] || 'Waiting';
    }
    if (tip) {
      let tipHTML = `
        <div class="pipeline-tooltip__title">${AGENTS[agentKey]?.label || agentKey}</div>
        <div class="pipeline-tooltip__desc">${AGENTS[agentKey]?.description || ''}</div>
        <div class="pipeline-tooltip__status">Status: <strong>${STATUS_LABELS[status]}</strong></div>
      `;
      if (status === 'failed' && agentDetail?.error_detail) {
        tipHTML += `<div class="pipeline-tooltip__error">${agentDetail.error_detail}</div>`;
      }
      if (agentDetail?.updated_at) {
        tipHTML += `<div class="pipeline-tooltip__time">Updated: ${new Date(agentDetail.updated_at).toLocaleTimeString()}</div>`;
      }
      tip.innerHTML = tipHTML;
    }
  }
}


// ─── Result navigation ───────────────────────────────────────────────────────

function appendResultNav(statusDiv, jobId, resumeId) {
  const navContainer = document.createElement('div');
  navContainer.className = 'result-nav';

  const links = [
    { text: '📊 All Results', hash: buildHash('#/results', { job: jobId, resume: resumeId, tab: 'match' }) },
    { text: '🎯 Match Score', hash: buildHash('#/results/match', { job: jobId, resume: resumeId }) },
    { text: '📋 Gap Analysis', hash: buildHash('#/results/gaps', { job: jobId, resume: resumeId }) },
    { text: '📝 Resume Variants', hash: buildHash('#/results/variants', { job: jobId, resume: resumeId }) },
    { text: '🎤 Interview Prep', hash: buildHash('#/results/interview', { job: jobId, resume: resumeId }) },
    { text: '✉️ Cover Letter', hash: buildHash('#/results/cover', { job: jobId, resume: resumeId }) },
  ];

  links.forEach(({ text, hash }) => {
    const btn = document.createElement('button');
    btn.textContent = text;
    btn.onclick = () => { window.location.hash = hash; };
    navContainer.appendChild(btn);
  });

  statusDiv.appendChild(navContainer);
}


// ─── Main orchestrator runner ────────────────────────────────────────────────

function cloneStepStatus() {
  const status = {};
  for (const key in AGENTS) {
    status[key] = { done: false };
  }
  return status;
}

/**
 * Drive the orchestrator's background-only status polling UI.
 * The backend always runs in the background now, so this function:
 *   - POSTs `/api/orchestrate` (which is idempotent — a running run for this
 *     pair is returned as-is rather than starting a duplicate)
 *   - polls `/api/orchestrate/status/{job}/{resume}` until status is `complete`
 *     or `failed`
 *   - renders the pipeline flow graph with per-agent status updates
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
  const totalSteps = Object.keys(AGENTS).length;

  try {
    // Idempotent: backend returns the existing run (running or complete) for
    // this pair unless `force=true`.
    await postJson('/api/orchestrate', orchestrateBody);
    const stepStatus = cloneStepStatus();
    ({ elapsedTimer } = buildPipelineFlow(statusDiv, stepStatus, idPrefix));

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

        updatePipelineUI(stepStatus, statusRes.agent_statuses, idPrefix);
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
