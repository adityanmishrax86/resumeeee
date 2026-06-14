// screens/screen_cover_letter.js – Cover Letter renderer + regen.

import { createRegenPanel } from '../components/regen_panel.js';

export function renderCoverLetter(container, data, ctx = {}) {
  container.innerHTML = '';

  // Header + regen panel
  const header = document.createElement('div');
  header.style.cssText = 'margin-bottom:0.5rem;';

  if (ctx.resumeId && ctx.jobAnalysisId && typeof ctx.onRegen === 'function') {
    header.appendChild(createRegenPanel({
      title: 'Regenerate cover letters',
      placeholder: 'e.g. lead with the BigQuery migration, drop the "thrilled" wording, keep it under 250 words…',
      required: false,
      buttonLabel: 'Generate cover letters',
      onSubmit: (instructions) => ctx.onRegen(instructions),
      onSuccess: (result) => renderCoverLetter(container, result, ctx),
    }));
  }
  container.appendChild(header);

  if (!data) {
    const empty = document.createElement('p');
    empty.style.cssText = 'opacity:0.75;line-height:1.6;';
    empty.innerHTML =
      'No cover letter generated yet. Run the full pipeline from <a href="#/quick-start">Quick Start</a> ' +
      'or use the regenerate panel above (after a job/gap analysis exists).';
    container.appendChild(empty);
    return;
  }

  const variants = Array.isArray(data.variants) ? data.variants : [];
  if (variants.length === 0) {
    const empty = document.createElement('p');
    empty.style.cssText = 'opacity:0.85;color:#fb923c;';
    empty.textContent = '⚠️ Cover letter response had no variants.';
    container.appendChild(empty);
    return;
  }

  // Shared notes
  if (Array.isArray(data.shared_notes) && data.shared_notes.length > 0) {
    const notes = document.createElement('div');
    notes.style.cssText = 'margin:0.5rem 0 1rem;padding:0.6rem 0.9rem;border-left:3px solid #38bdf8;background:rgba(56,189,248,0.06);border-radius:6px;';
    const h = document.createElement('strong');
    h.style.color = '#38bdf8';
    h.textContent = 'Shared research notes';
    notes.appendChild(h);
    const ul = document.createElement('ul');
    ul.style.cssText = 'margin:0.4rem 0 0;padding-left:1.2rem;line-height:1.6;';
    data.shared_notes.forEach((n) => {
      const li = document.createElement('li');
      li.textContent = n;
      ul.appendChild(li);
    });
    notes.appendChild(ul);
    container.appendChild(notes);
  }

  // Tab bar across variants
  const tabBar = document.createElement('div');
  tabBar.style.cssText = 'display:flex;gap:0.5rem;margin-bottom:1rem;flex-wrap:wrap;';

  const panels = [];
  variants.forEach((v, idx) => {
    const tab = document.createElement('button');
    tab.type = 'button';
    tab.textContent = (v.style || `Variant ${idx + 1}`).replace(/\b\w/g, (c) => c.toUpperCase());
    tab.style.cssText = `
      padding:0.4rem 0.9rem;border-radius:8px;border:1px solid rgba(255,255,255,0.2);
      cursor:pointer;color:#fff;font-size:0.85rem;
      background:${idx === 0 ? 'linear-gradient(135deg, #6366f1, #4f46e5)' : 'rgba(255,255,255,0.05)'};
    `;
    tabBar.appendChild(tab);

    const panel = document.createElement('div');
    panel.style.display = idx === 0 ? 'block' : 'none';
    renderVariant(panel, v);
    panels.push({ tab, panel });
  });

  panels.forEach((p) => {
    p.tab.addEventListener('click', () => {
      panels.forEach((pk) => {
        pk.panel.style.display = 'none';
        pk.tab.style.background = 'rgba(255,255,255,0.05)';
      });
      p.panel.style.display = 'block';
      p.tab.style.background = 'linear-gradient(135deg, #6366f1, #4f46e5)';
    });
  });

  container.appendChild(tabBar);
  panels.forEach((p) => container.appendChild(p.panel));
}


function renderVariant(container, variant) {
  const content = variant.content_md || variant.content || '';
  const why = Array.isArray(variant.why_choose_me) ? variant.why_choose_me : [];

  // Action buttons
  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;gap:0.5rem;margin-bottom:0.5rem;flex-wrap:wrap;';

  const copy = document.createElement('button');
  copy.type = 'button';
  copy.textContent = 'Copy';
  copy.className = 'btn-secondary';
  copy.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  copy.addEventListener('click', () => {
    navigator.clipboard.writeText(content).then(() => {
      copy.textContent = 'Copied!';
      setTimeout(() => { copy.textContent = 'Copy'; }, 2000);
    });
  });

  const download = document.createElement('button');
  download.type = 'button';
  download.textContent = 'Download .md';
  download.className = 'btn-secondary';
  download.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  download.addEventListener('click', () => {
    const slug = `cover-letter-${(variant.style || 'variant').toLowerCase().replace(/\s+/g, '-')}`;
    const blob = new Blob([content], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${slug}.md`;
    a.click();
    URL.revokeObjectURL(url);
  });

  const preview = document.createElement('button');
  preview.type = 'button';
  preview.textContent = 'Preview';
  preview.className = 'btn-secondary';
  preview.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:pointer;';
  preview.addEventListener('click', () => openPreview(`Cover Letter — ${variant.style || ''}`, content));

  const pdf = document.createElement('button');
  pdf.type = 'button';
  pdf.textContent = 'PDF (coming soon)';
  pdf.className = 'btn-secondary';
  pdf.disabled = true;
  pdf.title = 'PDF export will be available in a future update.';
  pdf.style.cssText = 'font-size:0.8rem;padding:0.3rem 0.7rem;border-radius:6px;cursor:not-allowed;opacity:0.6;';

  actions.appendChild(copy);
  actions.appendChild(download);
  actions.appendChild(preview);
  actions.appendChild(pdf);
  container.appendChild(actions);

  // Why choose me
  if (why.length) {
    const card = document.createElement('div');
    card.className = 'card';
    card.style.cssText = 'margin-bottom:1rem;';
    const h4 = document.createElement('h4');
    h4.style.cssText = 'color:#a78bfa;margin-bottom:0.5rem;';
    h4.textContent = 'Why you for this role';
    card.appendChild(h4);
    const ul = document.createElement('ul');
    ul.style.paddingLeft = '1.2rem';
    why.forEach((w) => {
      const li = document.createElement('li');
      li.textContent = w;
      ul.appendChild(li);
    });
    card.appendChild(ul);
    container.appendChild(card);
  }

  // Body
  const body = document.createElement('div');
  body.style.cssText = `
    background:rgba(0,0,0,0.25);padding:1rem 1.2rem;border-radius:8px;
    line-height:1.7;font-size:0.95rem;
    max-height:520px;overflow-y:auto;
    border:1px solid rgba(255,255,255,0.1);
  `;
  body.innerHTML = window.marked ? window.marked.parse(content) : content;
  container.appendChild(body);
}


function openPreview(title, content) {
  const overlay = document.createElement('div');
  overlay.style.cssText = `
    position:fixed;inset:0;background:rgba(0,0,0,0.75);z-index:9999;
    display:flex;align-items:center;justify-content:center;padding:2rem;
  `;
  const modal = document.createElement('div');
  modal.style.cssText = `
    background:#0f172a;color:#e0e0e0;border-radius:12px;max-width:900px;width:100%;
    max-height:90vh;display:flex;flex-direction:column;
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
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}
