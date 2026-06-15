// screens/screen4_match_score.js – Match Score Overview screen

import { createCard } from '../components/card.js';
import { getJson, postJson } from '../api.js';
import { getOrchestratorResult } from '../state.js';

export function loadScreen4(container) {
  const title = document.createElement('h2');
  title.textContent = 'Match Score Overview';
  container.appendChild(title);

  const selCard = createCard('Select Job & Resume', null);
  selCard.style.marginBottom = '1rem';

  const jobSelect = document.createElement('select');
  const resumeSelect = document.createElement('select');
  const loadBtn = document.createElement('button');
  loadBtn.textContent = 'Load Match Score';

  selCard.appendChild(document.createTextNode('Job: '));
  selCard.appendChild(jobSelect);
  selCard.appendChild(document.createTextNode('  Resume: '));
  selCard.appendChild(resumeSelect);
  selCard.appendChild(loadBtn);
  container.appendChild(selCard);

  const resultCard = createCard('Resume Match Result', null);
  const resultDiv = document.createElement('div');
  resultCard.appendChild(resultDiv);
  container.appendChild(resultCard);

  async function populateSelects() {
    try {
      const jobs = await getJson('/api/jobs');
      jobSelect.innerHTML = '';
      jobs.forEach(j => {
        const opt = document.createElement('option');
        opt.value = j.id;
        opt.textContent = `${j.role_title || 'Untitled'} @ ${j.company_name || 'Unknown'}`;
        jobSelect.appendChild(opt);
      });
      const resumes = await getJson('/api/resumes');
      resumeSelect.innerHTML = '';
      resumes.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.name}${r.is_master ? ' (Master)' : ''}`;
        resumeSelect.appendChild(opt);
      });
    } catch (e) {
      console.error('Failed to load selects', e);
    }
  }

  populateSelects();

  loadBtn.addEventListener('click', async () => {
    const jobId = jobSelect.value;
    const resumeId = resumeSelect.value;
    if (!jobId || !resumeId) {
      alert('Select job and resume');
      return;
    }
    resultDiv.innerHTML = 'Loading…';
    loadBtn.disabled = true;

    try {
      // Resolve job_analysis_id: prefer saved orchestrator state, fall back to analysis endpoint
      let jobAnalysisId = null;
      const saved = getOrchestratorResult(jobId, resumeId);
      if (saved?.job_analysis_id) {
        jobAnalysisId = saved.job_analysis_id;
      } else {
        // Try to get it from the analysis endpoint (it should have an `id` field)
        try {
          const analysis = await getJson(`/api/jobs/${jobId}/analysis`);
          jobAnalysisId = analysis?.id ?? analysis?.job_analysis_id ?? null;
        } catch (_) {}
      }

      if (!jobAnalysisId) {
        resultDiv.innerHTML =
          '<p style="color:#f87171">⚠️ No job analysis found for this job. Please run <strong>Analysis (Screen 3)</strong> first.</p>';
        return;
      }

      let match = null;
      if (saved && saved.resume_match) {
        match = saved.resume_match;
      } else {
        match = await postJson('/api/resumes/match', {
          resume_id: resumeId,
          job_analysis_id: jobAnalysisId,
        });
      }

      renderMatch(resultDiv, match);
    } catch (e) {
      resultDiv.innerHTML = `<p style="color:#f87171">Failed to load match result: ${e.message}</p>`;
    } finally {
      loadBtn.disabled = false;
    }
  });
}

export function renderMatch(container, match) {
  container.innerHTML = '';

  // Score cards row
  const scores = document.createElement('div');
  scores.style.cssText = 'display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem;';

  [
    { label: 'Overall', value: match.overall_score },
    { label: 'Skills', value: match.skills_match_score },
    { label: 'Experience', value: match.experience_match_score },
  ].forEach(({ label, value }) => {
    const chip = document.createElement('div');
    chip.style.cssText = `
      flex:1;min-width:120px;padding:1rem;border-radius:12px;text-align:center;
      background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.15);
    `;
    const num = document.createElement('div');
    num.style.cssText = 'font-size:2rem;font-weight:700;color:#818cf8;';
    num.textContent = `${value}`;
    const lbl = document.createElement('div');
    lbl.style.cssText = 'font-size:0.8rem;opacity:0.7;margin-top:0.25rem;';
    lbl.textContent = label;
    chip.appendChild(num);
    chip.appendChild(lbl);
    scores.appendChild(chip);
  });
  container.appendChild(scores);

  // Summary
  if (match.match_summary) {
    const summary = document.createElement('div');
    summary.style.cssText = 'margin-bottom:1rem;line-height:1.6;opacity:0.85;';
    summary.innerHTML = window.marked ? window.marked.parse(match.match_summary) : match.match_summary;
    container.appendChild(summary);
  }

  // Experience fit
  if (match.experience_fit) {
    const ef = document.createElement('div');
    ef.style.marginBottom = '0.75rem';
    
    // Create a wrapper for the title
    const efTitle = document.createElement('strong');
    efTitle.textContent = 'Experience Fit: ';
    ef.appendChild(efTitle);

    // Create a container for the markdown content, inline if possible
    const efContent = document.createElement('span');
    efContent.innerHTML = window.marked ? window.marked.parse(match.experience_fit) : match.experience_fit;
    ef.appendChild(efContent);
    
    container.appendChild(ef);
  }

  // Two-column skill grid
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem;';

  const addList = (title, items, color) => {
    const section = document.createElement('div');
    const h4 = document.createElement('h4');
    h4.style.cssText = `color:${color};margin-bottom:0.4rem;`;
    h4.textContent = title;
    section.appendChild(h4);
    const ul = document.createElement('ul');
    ul.style.cssText = 'margin:0;padding-left:1.2rem;';
    (items || []).forEach(item => {
      const li = document.createElement('li');
      li.textContent = item;
      ul.appendChild(li);
    });
    if ((items || []).length === 0) {
      ul.innerHTML = '<li style="opacity:0.5">None</li>';
    }
    section.appendChild(ul);
    return section;
  };

  grid.appendChild(addList('✅ Matched Required Skills', match.matched_required_skills, '#4ade80'));
  grid.appendChild(addList('❌ Missing Required Skills', match.missing_required_skills, '#f87171'));
  grid.appendChild(addList('⭐ Matched Preferred Skills', match.matched_preferred_skills, '#a78bfa'));
  grid.appendChild(addList('⚠️ Missing Preferred Skills', match.missing_preferred_skills, '#fb923c'));
  container.appendChild(grid);

  // Strengths
  if ((match.strengths || []).length > 0) {
    const sec = addList('💪 Strengths', match.strengths, '#4ade80');
    sec.style.marginBottom = '0.75rem';
    container.appendChild(sec);
  }

  // Improvement suggestions
  if ((match.improvement_suggestions || []).length > 0) {
    const sec = addList('🔧 Improvement Suggestions', match.improvement_suggestions, '#fb923c');
    sec.style.marginBottom = '0.75rem';
    container.appendChild(sec);
  }

  // ATS panel
  const atsPanel = document.createElement('details');
  const atsSummary = document.createElement('summary');
  atsSummary.style.cssText = 'cursor:pointer;font-weight:600;margin-bottom:0.5rem;';
  atsSummary.textContent = '🔍 ATS Keyword Coverage';
  atsPanel.appendChild(atsSummary);

  const table = document.createElement('table');
  table.style.cssText = 'width:100%;border-collapse:collapse;font-size:0.9rem;';
  table.innerHTML = `
    <thead>
      <tr>
        <th style="text-align:left;padding:0.5rem;border-bottom:1px solid rgba(255,255,255,0.15);color:#4ade80;">Covered</th>
        <th style="text-align:left;padding:0.5rem;border-bottom:1px solid rgba(255,255,255,0.15);color:#f87171;">Gaps</th>
      </tr>
    </thead>
  `;
  const tbody = document.createElement('tbody');
  const covered = match.ats_keyword_coverage || [];
  const gaps = match.ats_keyword_gaps || [];
  const maxRows = Math.max(covered.length, gaps.length, 1);
  for (let i = 0; i < maxRows; i++) {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td style="padding:0.3rem 0.5rem;opacity:0.85;">${covered[i] || ''}</td>
      <td style="padding:0.3rem 0.5rem;opacity:0.85;">${gaps[i] || ''}</td>
    `;
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  atsPanel.appendChild(table);
  container.appendChild(atsPanel);
}
