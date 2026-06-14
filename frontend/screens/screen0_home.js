// screens/screen0_home.js – Landing page with Workflow Guide

import { getJson } from '../api.js';
import { buildHash, getHashParams } from '../utils/hash.js';
import {
  getLastStoredRun,
  getExtensionPayload,
  hasStoredRuns,
  resolveRunContext,
} from '../state.js';

export function loadScreen0(container) {
  const heroDiv = document.createElement('div');
  heroDiv.className = 'hero-section';

  const title = document.createElement('h1');
  title.className = 'hero-title';
  title.textContent = 'Welcome to AI Job Copilot';

  const subtitle = document.createElement('p');
  subtitle.className = 'hero-subtitle';
  subtitle.textContent =
    'Your intelligent assistant for dominating the job hunt. Automate resume matching, discover skill gaps, and get personalized interview prep — from LinkedIn, Naukri, or manual paste.';

  heroDiv.appendChild(title);
  heroDiv.appendChild(subtitle);
  container.appendChild(heroDiv);

  const readinessCard = document.createElement('div');
  readinessCard.className = 'card readiness-card';
  readinessCard.id = 'readiness-card';
  readinessCard.innerHTML = '<p class="loading-text">Checking setup status…</p>';
  container.appendChild(readinessCard);

  const ctaRow = document.createElement('div');
  ctaRow.className = 'home-cta-row';
  ctaRow.id = 'home-cta-row';
  container.appendChild(ctaRow);

  const guideTitle = document.createElement('h2');
  guideTitle.textContent = 'How It Works';
  guideTitle.className = 'section-title';
  container.appendChild(guideTitle);

  const grid = document.createElement('div');
  grid.className = 'home-grid';

  const steps = [
    {
      icon: '1',
      title: 'Extract Job Details',
      desc: 'Use the Chrome extension on LinkedIn or Naukri, or paste a job description manually.',
      actionText: 'Manual Ingest',
      actionHref: '#/jobs',
    },
    {
      icon: '2',
      title: 'Setup Master Resume',
      desc: 'Upload your markdown resume. The AI uses it as a baseline for tailored variations.',
      actionText: 'Manage Resumes',
      actionHref: '#/resumes',
    },
    {
      icon: '3',
      title: 'Run Quick Start',
      desc: 'Click "Send to Dashboard" from the extension to jump into the Quick Start pipeline.',
      actionText: 'Go to Quick Start',
      actionHref: '#/quick-start',
    },
    {
      icon: '4',
      title: 'Review Results',
      desc: 'View Match Score, Skill Gaps, Resume Variants, and Interview Prep in one place.',
      actionText: 'View Results',
      actionHref: '#/results',
    },
  ];

  steps.forEach((step) => {
    const card = document.createElement('div');
    card.className = 'card home-step-card';

    const icon = document.createElement('div');
    icon.className = 'step-icon';
    icon.textContent = step.icon;

    const cardTitle = document.createElement('h3');
    cardTitle.textContent = step.title;

    const desc = document.createElement('p');
    desc.className = 'step-desc';
    desc.textContent = step.desc;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = step.actionText;
    btn.onclick = () => { window.location.hash = step.actionHref; };

    card.appendChild(icon);
    card.appendChild(cardTitle);
    card.appendChild(desc);
    card.appendChild(btn);
    grid.appendChild(card);
  });

  container.appendChild(grid);

  async function renderReadiness() {
    let jobCount = 0;
    let resumeCount = 0;
    let backendOk = false;

    try {
      const [jobs, resumes] = await Promise.all([
        getJson('/api/jobs'),
        getJson('/api/resumes'),
      ]);
      jobCount = jobs.length;
      resumeCount = resumes.length;
      backendOk = true;
    } catch (_) {
      backendOk = false;
    }

    readinessCard.innerHTML = '';
    const h3 = document.createElement('h3');
    h3.textContent = 'Setup Status';
    readinessCard.appendChild(h3);

    const list = document.createElement('ul');
    list.className = 'readiness-list';
    list.innerHTML = `
      <li class="${backendOk ? 'ready' : 'missing'}">${backendOk ? 'Backend connected' : 'Backend offline'}</li>
      <li class="${jobCount > 0 ? 'ready' : 'missing'}">${jobCount} job${jobCount === 1 ? '' : 's'} ingested</li>
      <li class="${resumeCount > 0 ? 'ready' : 'missing'}">${resumeCount} resume${resumeCount === 1 ? '' : 's'} uploaded</li>
      <li class="${hasStoredRuns() ? 'ready' : 'missing'}">${hasStoredRuns() ? 'Analysis results available' : 'No analysis runs yet'}</li>
    `;
    readinessCard.appendChild(list);

    ctaRow.innerHTML = '';
    const extPayload = getExtensionPayload() || getHashParams().get('payload');
    const lastRun = getLastStoredRun();

    if (extPayload) {
      const btn = document.createElement('button');
      btn.className = 'btn-primary-lg';
      btn.textContent = 'Continue Quick Start';
      btn.onclick = () => { window.location.hash = '#/quick-start'; };
      ctaRow.appendChild(btn);
    } else if (lastRun && hasStoredRuns()) {
      const btn = document.createElement('button');
      btn.className = 'btn-primary-lg';
      btn.textContent = 'Continue Last Analysis';
      btn.onclick = () => {
        window.location.hash = buildHash('#/results', {
          job: lastRun.jobId,
          resume: lastRun.resumeId,
          tab: 'match',
        });
      };
      ctaRow.appendChild(btn);
    }

    if (jobCount > 0 && resumeCount > 0) {
      const runBtn = document.createElement('button');
      runBtn.textContent = 'Run Analysis';
      runBtn.onclick = () => { window.location.hash = '#/analysis'; };
      ctaRow.appendChild(runBtn);
    } else if (!extPayload && !lastRun) {
      const hint = document.createElement('p');
      hint.className = 'cta-hint';
      if (jobCount === 0 && resumeCount === 0) {
        hint.textContent = 'Start by ingesting a job and uploading your resume.';
      } else if (jobCount === 0) {
        hint.innerHTML = 'Next step: <a href="#/jobs">Ingest a job</a>';
      } else {
        hint.innerHTML = 'Next step: <a href="#/resumes">Upload your resume</a>';
      }
      ctaRow.appendChild(hint);
    }

    const { jobId, resumeId } = resolveRunContext(getHashParams());
    if (hasStoredRuns() && jobId && resumeId) {
      const resultsBtn = document.createElement('button');
      resultsBtn.className = 'btn-secondary';
      resultsBtn.textContent = 'View Results';
      resultsBtn.onclick = () => {
        window.location.hash = buildHash('#/results', { job: jobId, resume: resumeId });
      };
      ctaRow.appendChild(resultsBtn);
    }
  }

  renderReadiness();
}
