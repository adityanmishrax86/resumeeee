// screens/screen6_resume_variants.js – Resume Variants / Rewrite screen

import { createCard } from '../components/card.js';
import { getJson } from '../api.js';
import { getOrchestratorResult, listStoredRuns } from '../state.js';
import { createRegenPanel } from '../components/regen_panel.js';

export function loadScreen6(container) {
  const title = document.createElement('h2');
  title.textContent = 'Resume Variants';
  container.appendChild(title);

  const selCard = createCard('Select Analysis Run', null);
  selCard.style.marginBottom = '1rem';

  const jobSelect = document.createElement('select');
  const resumeSelect = document.createElement('select');
  const loadBtn = document.createElement('button');
  loadBtn.textContent = 'Load Resume Variants';

  selCard.appendChild(document.createTextNode('Job: '));
  selCard.appendChild(jobSelect);
  selCard.appendChild(document.createTextNode('  Resume: '));
  selCard.appendChild(resumeSelect);
  selCard.appendChild(loadBtn);
  container.appendChild(selCard);

  const resultCard = createCard('Rewritten Resume Variants', null);
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
        '<p style="color:#f87171">⚠️ No analysis found for this pair. Please run <strong>Analysis (Screen 3)</strong> first.</p>';
      return;
    }

    const rewriteData = saved.resume_rewrite;
    if (!rewriteData) {
      resultDiv.innerHTML =
        '<p style="color:#fb923c">⚠️ Resume rewrite data is not available. The pipeline may still be running or this step was skipped.</p>';
      return;
    }

    renderResumeVariants(resultDiv, rewriteData);
  });

  const runs = listStoredRuns();
  if (runs.length === 1) {
    setTimeout(() => {
      const run = runs[0];
      if (run.jobId) jobSelect.value = run.jobId;
      if (run.resumeId) resumeSelect.value = run.resumeId;
    }, 500);
  }
}

export function renderResumeVariants(container, data, ctx = {}) {
  container.innerHTML = '';

  // Regenerate panel — only when we have enough context to call the endpoint.
  if (ctx.resumeId && ctx.gapAnalysisId && ctx.jobAnalysisId && typeof ctx.onRegen === 'function') {
    container.appendChild(createRegenPanel({
      title: 'Regenerate resume variants',
      placeholder: 'e.g. emphasise BigQuery + Dataproc, trim the leadership bullets, keep ATS variant under 1 page…',
      buttonLabel: 'Regenerate variants',
      onSubmit: (instructions) => ctx.onRegen(instructions),
      onSuccess: (result) => renderResumeVariants(container, result, ctx),
    }));
  }

  let variantsList = [];
  if (Array.isArray(data.variants)) {
    variantsList = data.variants;
  } else {
    // legacy format
    const variantKeys = ['aggressive', 'conservative', 'balanced', 'variant_1', 'variant_2', 'variant_3'];
    variantsList = variantKeys.filter(k => data[k]).map(k => ({
      variant: k,
      content: data[k].markdown || data[k].content || data[k]
    }));
  }

  if (variantsList.length > 0) {
    // Render a tab-like set of variants
    const tabBar = document.createElement('div');
    tabBar.style.cssText = 'display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;';

    const panels = [];
    variantsList.forEach((v, idx) => {
      const tab = document.createElement('button');
      tab.textContent = v.variant.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
      tab.style.cssText = `
        padding:0.4rem 0.9rem;border-radius:8px;border:1px solid rgba(255,255,255,0.2);
        cursor:pointer;background:${idx === 0 ? 'linear-gradient(135deg, #6366f1, #4f46e5)' : 'rgba(255,255,255,0.05)'};
        color:#fff;font-size:0.85rem;
      `;
      tabBar.appendChild(tab);

      const panel = document.createElement('div');
      panel.style.display = idx === 0 ? 'block' : 'none';
      renderVariantContent(panel, v);
      panels.push({ tab, panel });
    });

    // Tab switching logic
    panels.forEach((p, idx) => {
      p.tab.addEventListener('click', () => {
        panels.forEach(pk => {
          pk.panel.style.display = 'none';
          pk.tab.style.background = 'rgba(255,255,255,0.05)';
        });
        p.panel.style.display = 'block';
        p.tab.style.background = 'linear-gradient(135deg, #6366f1, #4f46e5)';
      });
    });

    container.appendChild(tabBar);
    panels.forEach(p => container.appendChild(p.panel));
    return;
  }

  // Single rewrite or unknown shape – try common fields
  if (data.markdown || data.content || data.rewritten_markdown) {
    const content = data.markdown || data.content || data.rewritten_markdown;
    renderMarkdownBlock(container, 'Rewritten Resume', content);
    return;
  }

  // Generic fallback
  const pre = document.createElement('pre');
  pre.style.cssText = 'background:rgba(0,0,0,0.2);padding:1rem;border-radius:8px;white-space:pre-wrap;font-size:0.85rem;line-height:1.6;';
  pre.textContent = JSON.stringify(data, null, 2);
  container.appendChild(pre);
}

function renderVariantContent(container, variantData) {
  if (typeof variantData === 'string') {
    renderMarkdownBlock(container, '', variantData);
    return;
  }
  
  if (variantData.changes_summary && Array.isArray(variantData.changes_summary)) {
    const summaryDiv = document.createElement('div');
    summaryDiv.className = 'card';
    summaryDiv.style.marginBottom = '1rem';
    summaryDiv.innerHTML = '<h4 style="color:#a78bfa;margin-bottom:0.5rem;">Changes Summary</h4>';
    const ul = document.createElement('ul');
    ul.style.paddingLeft = '1.2rem';
    variantData.changes_summary.forEach(c => {
      const li = document.createElement('li');
      li.textContent = c;
      ul.appendChild(li);
    });
    summaryDiv.appendChild(ul);
    container.appendChild(summaryDiv);
  }

  const content = variantData.content_md || variantData.content || variantData.markdown || '';
  if (content) {
    renderMarkdownBlock(container, 'Resume Content', content);
    return;
  }

  const pre = document.createElement('pre');
  pre.style.cssText = 'background:rgba(0,0,0,0.2);padding:1rem;border-radius:8px;white-space:pre-wrap;font-size:0.85rem;line-height:1.6;';
  pre.textContent = JSON.stringify(variantData, null, 2);
  container.appendChild(pre);
}

function renderMarkdownBlock(container, label, content) {
  if (label) {
    const h4 = document.createElement('h4');
    h4.textContent = label;
    h4.style.marginBottom = '0.5rem';
    container.appendChild(h4);
  }

  // Copy + download buttons
  const actions = document.createElement('div');
  actions.className = 'variant-actions';
  actions.style.cssText = 'display:flex;gap:0.5rem;margin-bottom:0.5rem;flex-wrap:wrap;';

  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.textContent = 'Copy';
  copyBtn.className = 'btn-secondary';
  copyBtn.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  copyBtn.addEventListener('click', () => {
    navigator.clipboard.writeText(content).then(() => {
      copyBtn.textContent = 'Copied!';
      setTimeout(() => { copyBtn.textContent = 'Copy'; }, 2000);
    });
  });

  const downloadBtn = document.createElement('button');
  downloadBtn.type = 'button';
  downloadBtn.textContent = 'Download .md';
  downloadBtn.className = 'btn-secondary';
  downloadBtn.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  downloadBtn.addEventListener('click', () => {
    const slug = (label || 'resume-variant').toLowerCase().replace(/\s+/g, '-');
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${slug}.md`;
    a.click();
    URL.revokeObjectURL(url);
  });

  actions.appendChild(copyBtn);
  actions.appendChild(downloadBtn);

  const previewBtn = document.createElement('button');
  previewBtn.type = 'button';
  previewBtn.textContent = 'Preview';
  previewBtn.className = 'btn-secondary';
  previewBtn.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  previewBtn.addEventListener('click', () => openMarkdownPreview(label || 'Resume Variant', content));
  actions.appendChild(previewBtn);

  const pdfBtn = document.createElement('button');
  pdfBtn.type = 'button';
  pdfBtn.textContent = 'PDF (coming soon)';
  pdfBtn.className = 'btn-secondary';
  pdfBtn.disabled = true;
  pdfBtn.title = 'PDF export will be available in a future update.';
  pdfBtn.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:not-allowed;opacity:0.6;';
  actions.appendChild(pdfBtn);

  container.appendChild(actions);

  const pre = document.createElement('pre');
  pre.style.cssText = `
    background:rgba(0,0,0,0.25);padding:1rem;border-radius:8px;
    white-space:pre-wrap;font-size:0.85rem;line-height:1.7;
    max-height:500px;overflow-y:auto;
    border:1px solid rgba(255,255,255,0.1);
  `;
  pre.textContent = content;
  container.appendChild(pre);
}


function openMarkdownPreview(title, content) {
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;
    display:flex;align-items:center;justify-content:center;padding:2rem;
  `;
  const modal = document.createElement('div');
  modal.style.cssText = `
    background:#0f172a;color:#e0e0e0;border-radius:12px;max-width:900px;
    width:100%;max-height:90vh;display:flex;flex-direction:column;
    border:1px solid rgba(255,255,255,0.12);box-shadow:0 8px 40px rgba(0,0,0,0.5);
  `;
  const header = document.createElement('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;padding:1rem 1.4rem;border-bottom:1px solid rgba(255,255,255,0.08);';
  const h = document.createElement('h3');
  h.textContent = title;
  h.style.margin = '0';
  const close = document.createElement('button');
  close.textContent = '✕';
  close.style.cssText = 'background:none;border:none;color:#e0e0e0;font-size:1.4rem;cursor:pointer;';
  close.onclick = () => overlay.remove();
  header.appendChild(h);
  header.appendChild(close);
  const body = document.createElement('div');
  body.style.cssText = 'padding:1.4rem;overflow-y:auto;line-height:1.7;';
  body.innerHTML = window.marked ? window.marked.parse(content || '') : `<pre>${content || ''}</pre>`;
  modal.appendChild(header);
  modal.appendChild(body);
  overlay.appendChild(modal);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
}
