// screens/screen8_quick_start.js – Quick Start (existing job + existing resume only)

import { createCard } from '../components/card.js';
import { showToast } from '../components/toast.js';
import { getJson } from '../api.js';
import { runOrchestrator } from '../services/orchestrator.js';

export function loadScreen8(container) {
  const title = document.createElement('h2');
  title.textContent = 'Quick Start: Run Analysis';
  container.appendChild(title);

  const helper = document.createElement('p');
  helper.className = 'field-helper';
  helper.textContent = 'Pick an existing job and resume from your library, then run the analysis pipeline.';
  container.appendChild(helper);

  const card = createCard('Pick Job & Resume', null);
  const form = document.createElement('form');
  form.className = 'quick-start-form';

  // ── Job picker ───────────────────────────────────────────────────────────
  const jobSection = document.createElement('div');
  jobSection.className = 'quick-section';
  const jobTitle = document.createElement('h3');
  jobTitle.textContent = '1. Job';
  jobSection.appendChild(jobTitle);

  const jobLabel = document.createElement('label');
  jobLabel.textContent = 'Select Job';
  const jobSelect = document.createElement('select');
  jobSelect.required = true;
  jobSection.appendChild(jobLabel);
  jobSection.appendChild(jobSelect);

  const jobsHelp = document.createElement('p');
  jobsHelp.className = 'field-helper';
  jobsHelp.innerHTML = 'Need to add one? Open <a href="#/jobs">Jobs</a>.';
  jobSection.appendChild(jobsHelp);
  form.appendChild(jobSection);

  // ── Resume picker ────────────────────────────────────────────────────────
  const resSection = document.createElement('div');
  resSection.className = 'quick-section';
  const resTitle = document.createElement('h3');
  resTitle.textContent = '2. Resume';
  resSection.appendChild(resTitle);

  const resLabel = document.createElement('label');
  resLabel.textContent = 'Select Resume';
  const resumeSelect = document.createElement('select');
  resumeSelect.required = true;
  resSection.appendChild(resLabel);
  resSection.appendChild(resumeSelect);

  const resHelp = document.createElement('p');
  resHelp.className = 'field-helper';
  resHelp.innerHTML = 'Need to upload one? Open <a href="#/resumes">Resumes</a>.';
  resSection.appendChild(resHelp);
  form.appendChild(resSection);

  // ── Submit ───────────────────────────────────────────────────────────────
  const analyzeBtn = document.createElement('button');
  analyzeBtn.type = 'submit';
  analyzeBtn.textContent = 'Analyze';
  analyzeBtn.className = 'btn-primary-lg';
  form.appendChild(analyzeBtn);

  const statusDiv = document.createElement('div');
  statusDiv.className = 'orchestrator-status';
  form.appendChild(statusDiv);

  card.appendChild(form);
  container.appendChild(card);

  // ── Populate ─────────────────────────────────────────────────────────────
  getJson('/api/jobs').then((jobs) => {
    jobSelect.innerHTML = '';
    if (!jobs.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— No jobs yet — add one on the Jobs screen —';
      opt.disabled = true;
      opt.selected = true;
      jobSelect.appendChild(opt);
      analyzeBtn.disabled = true;
      return;
    }
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select a job…';
    placeholder.disabled = true;
    placeholder.selected = true;
    jobSelect.appendChild(placeholder);
    jobs.forEach((j) => {
      const opt = document.createElement('option');
      opt.value = j.id;
      opt.textContent = `${j.role_title || 'Untitled'} @ ${j.company_name || 'Unknown'}`;
      jobSelect.appendChild(opt);
    });
  }).catch((err) => showToast('Failed to load jobs: ' + err.message, 'error'));

  getJson('/api/resumes').then((resumes) => {
    resumeSelect.innerHTML = '';
    if (!resumes.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '— No resumes yet — upload one on the Resumes screen —';
      opt.disabled = true;
      opt.selected = true;
      resumeSelect.appendChild(opt);
      analyzeBtn.disabled = true;
      return;
    }
    const placeholder = document.createElement('option');
    placeholder.value = '';
    placeholder.textContent = 'Select a resume…';
    placeholder.disabled = true;
    resumeSelect.appendChild(placeholder);
    let preselected = false;
    resumes.forEach((r) => {
      const opt = document.createElement('option');
      opt.value = r.id;
      opt.textContent = `${r.name}${r.is_master ? ' (Master)' : ''}`;
      if (r.is_master && !preselected) {
        opt.selected = true;
        preselected = true;
      }
      resumeSelect.appendChild(opt);
    });
    if (!preselected) placeholder.selected = true;
  }).catch((err) => showToast('Failed to load resumes: ' + err.message, 'error'));

  // ── Submit handler ───────────────────────────────────────────────────────
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const jobId = jobSelect.value;
    const resumeId = resumeSelect.value;
    if (!jobId || !resumeId) {
      showToast('Pick a job and a resume first.', 'error');
      return;
    }
    analyzeBtn.disabled = true;
    statusDiv.innerHTML = '';
    try {
      await runOrchestrator({
        jobId,
        resumeId,
        body: {
          skip_job_analysis: false,
          skip_resume_analysis: false,
          skip_interview_research: false,
        },
        statusDiv,
        idPrefix: 'qs',
      });
    } catch (err) {
      showToast('Error during analysis: ' + err.message, 'error');
    } finally {
      analyzeBtn.disabled = false;
    }
  });
}
