// screens/screen5_gap_analysis.js – Gap Analysis screen

import { createCard } from '../components/card.js';
import { getJson } from '../api.js';
import { getOrchestratorResult, listStoredRuns } from '../state.js';

export function loadScreen5(container) {
  const title = document.createElement('h2');
  title.textContent = 'Gap Analysis';
  container.appendChild(title);

  const selCard = createCard('Select Analysis Run', null);
  selCard.style.marginBottom = '1rem';

  const jobSelect = document.createElement('select');
  const resumeSelect = document.createElement('select');
  const loadBtn = document.createElement('button');
  loadBtn.textContent = 'Load Gap Analysis';

  selCard.appendChild(document.createTextNode('Job: '));
  selCard.appendChild(jobSelect);
  selCard.appendChild(document.createTextNode('  Resume: '));
  selCard.appendChild(resumeSelect);
  selCard.appendChild(loadBtn);
  container.appendChild(selCard);

  const resultCard = createCard('Gap Analysis Results', null);
  const resultDiv = document.createElement('div');
  resultCard.appendChild(resultDiv);
  container.appendChild(resultCard);

  async function populateSelects() {
    try {
      const jobs = await getJson('/api/jobs');
      jobSelect.innerHTML = '';
      jobs.forEach((j) => {
        const opt = document.createElement('option');
        opt.value = j.id;
        opt.textContent = `${j.role_title || 'Untitled'} @ ${j.company_name || 'Unknown'}`;
        jobSelect.appendChild(opt);
      });
      const resumes = await getJson('/api/resumes');
      resumeSelect.innerHTML = '';
      resumes.forEach((r) => {
        const opt = document.createElement('option');
        opt.value = r.id;
        opt.textContent = `${r.name}${r.is_master ? ' (Master)' : ''}`;
        resumeSelect.appendChild(opt);
      });
    } catch (e) {
      console.error('Failed to populate selects', e);
    }
  }

  populateSelects();

  loadBtn.addEventListener('click', () => {
    const jobId = jobSelect.value;
    const resumeId = resumeSelect.value;
    if (!jobId || !resumeId) {
      alert('Select job and resume');
      return;
    }

    const saved = getOrchestratorResult(jobId, resumeId);
    if (!saved) {
      resultDiv.innerHTML =
        '<p style="color:#f87171">⚠️ No analysis found for this pair. Run an analysis from <a href="#/quick-start">Quick Start</a> first.</p>';
      return;
    }

    const gapData = saved.gap_analysis;
    if (!gapData) {
      resultDiv.innerHTML =
        '<p style="color:#fb923c">⚠️ Gap analysis data is not available in the saved result.</p>';
      return;
    }

    renderGapAnalysis(resultDiv, gapData);
  });

  // Auto-load if only one run is stored
  const runs = listStoredRuns();
  if (runs.length === 1) {
    const run = runs[0];
    setTimeout(() => {
      if (run.jobId) jobSelect.value = run.jobId;
      if (run.resumeId) resumeSelect.value = run.resumeId;
    }, 500);
  }
}


// ── Renderers ────────────────────────────────────────────────────────────────

const GAP_BUCKETS = [
  { key: 'critical_gaps', label: 'Critical Gaps', color: '#f87171' },
  { key: 'moderate_gaps', label: 'Moderate Gaps', color: '#fb923c' },
  { key: 'minor_gaps', label: 'Minor Gaps', color: '#fbbf24' },
];


function renderGapList(container, items, accent) {
  if (!Array.isArray(items) || items.length === 0) {
    const p = document.createElement('p');
    p.style.cssText = 'opacity:0.7;margin:0;';
    p.textContent = 'None reported.';
    container.appendChild(p);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'gap-item';
    card.style.cssText = `border-left:3px solid ${accent};padding:0.6rem 0.9rem;margin:0.5rem 0;background:rgba(255,255,255,0.04);border-radius:6px;`;

    // Object form (preferred): {skill, severity, reason, bridge_suggestion}
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const head = document.createElement('div');
      head.style.cssText = 'display:flex;justify-content:space-between;align-items:baseline;gap:0.5rem;';
      const skill = document.createElement('strong');
      skill.textContent = item.skill || '—';
      head.appendChild(skill);
      if (item.severity) {
        const sev = document.createElement('span');
        sev.textContent = item.severity;
        sev.style.cssText = `font-size:0.75rem;padding:0.1rem 0.5rem;border-radius:10px;background:${accent};color:#0f172a;text-transform:uppercase;`;
        head.appendChild(sev);
      }
      card.appendChild(head);

      if (item.reason) {
        const reason = document.createElement('p');
        reason.style.cssText = 'margin:0.4rem 0 0;line-height:1.5;';
        reason.textContent = item.reason;
        card.appendChild(reason);
      }
      if (item.bridge_suggestion) {
        const bridge = document.createElement('p');
        bridge.style.cssText = 'margin:0.4rem 0 0;line-height:1.5;opacity:0.85;';
        const lbl = document.createElement('em');
        lbl.textContent = 'Bridge: ';
        bridge.appendChild(lbl);
        bridge.appendChild(document.createTextNode(item.bridge_suggestion));
        card.appendChild(bridge);
      }
    } else {
      // String fallback
      card.textContent = String(item);
    }
    container.appendChild(card);
  });
}


export function renderGapAnalysis(container, data) {
  container.innerHTML = '';

  if (typeof data === 'string') {
    try {
      data = JSON.parse(data);
    } catch (e) {
      const div = document.createElement('div');
      div.style.cssText = 'line-height:1.6;opacity:0.85;';
      div.innerHTML = window.marked ? window.marked.parse(data) : data;
      container.appendChild(div);
      return;
    }
  }

  // 1. Three nested gap buckets
  let anyGaps = false;
  GAP_BUCKETS.forEach(({ key, label, color }) => {
    const items = data[key];
    if (!Array.isArray(items) || items.length === 0) return;
    anyGaps = true;
    const section = document.createElement('div');
    section.className = 'section-grid';
    const header = document.createElement('div');
    header.className = 'section-header';
    const h4 = document.createElement('h4');
    h4.style.cssText = `color:${color};font-size:1.1rem;`;
    h4.textContent = `${label} (${items.length})`;
    header.appendChild(h4);
    section.appendChild(header);
    const content = document.createElement('div');
    renderGapList(content, items, color);
    section.appendChild(content);
    container.appendChild(section);
  });

  if (!anyGaps) {
    const noGaps = document.createElement('p');
    noGaps.style.cssText = 'color:#4ade80;';
    noGaps.textContent = '✅ No gaps reported.';
    container.appendChild(noGaps);
  }

  // 2. Quick wins (flat list of strings)
  if (Array.isArray(data.quick_wins) && data.quick_wins.length) {
    const section = document.createElement('div');
    section.className = 'section-grid';
    const header = document.createElement('div');
    header.className = 'section-header';
    const h4 = document.createElement('h4');
    h4.style.cssText = 'color:#4ade80;font-size:1.1rem;';
    h4.textContent = '💡 Quick Wins';
    header.appendChild(h4);
    section.appendChild(header);
    const content = document.createElement('div');
    const ul = document.createElement('ul');
    ul.style.cssText = 'margin:0;padding-left:1.2rem;line-height:1.7;';
    data.quick_wins.forEach((w) => {
      const li = document.createElement('li');
      li.textContent = w;
      ul.appendChild(li);
    });
    content.appendChild(ul);
    section.appendChild(content);
    container.appendChild(section);
  }

  // 3. Resume strategy / Cover letter angle (free text)
  [
    { key: 'resume_strategy', label: '📝 Resume Strategy', color: '#818cf8' },
    { key: 'cover_letter_angle', label: '✉️ Cover Letter Angle', color: '#38bdf8' },
  ].forEach(({ key, label, color }) => {
    const value = data[key];
    if (!value) return;
    const section = document.createElement('div');
    section.className = 'section-grid';
    const header = document.createElement('div');
    header.className = 'section-header';
    const h4 = document.createElement('h4');
    h4.style.cssText = `color:${color};font-size:1.1rem;`;
    h4.textContent = label;
    header.appendChild(h4);
    section.appendChild(header);
    const content = document.createElement('div');
    content.style.cssText = 'line-height:1.6;';
    content.innerHTML = window.marked ? window.marked.parse(String(value)) : String(value);
    section.appendChild(content);
    container.appendChild(section);
  });

  // 4. Honesty flag (optional)
  if (data.honesty_flag) {
    const banner = document.createElement('div');
    banner.style.cssText = 'margin-top:1rem;padding:0.7rem 1rem;border-left:3px solid #fbbf24;background:rgba(251,191,36,0.08);border-radius:6px;';
    const strong = document.createElement('strong');
    strong.style.color = '#fbbf24';
    strong.textContent = '⚠️ Honesty note: ';
    banner.appendChild(strong);
    banner.appendChild(document.createTextNode(data.honesty_note || ''));
    container.appendChild(banner);
  }
}
