// components/regen_panel.js – reusable "Regenerate with custom instructions" panel.
// Renders a small collapsible card with a textarea + Submit button. Used by
// the Variants, Interview, and Cover Letter screens.

import { showToast } from './toast.js';

/**
 * Build a regen panel.
 *
 * @param {object} opts
 * @param {string} opts.title              - heading text (e.g. "Regenerate Variants")
 * @param {string} [opts.placeholder]      - textarea placeholder
 * @param {boolean} [opts.required=true]   - whether custom_instructions is required
 * @param {string} [opts.buttonLabel="Regenerate"]
 * @param {(instructions: string) => Promise<any>} opts.onSubmit
 * @param {(result: any) => void} [opts.onSuccess]
 * @param {Array<{label: string, onClick: () => Promise<any>, onSuccess?: (r:any)=>void}>} [opts.extraActions]
 * @returns {HTMLElement}
 */
export function createRegenPanel(opts) {
  const {
    title,
    placeholder = 'e.g. tighten the wording, emphasise Python over Java, drop the volunteering section…',
    required = true,
    buttonLabel = 'Regenerate',
    onSubmit,
    onSuccess,
    extraActions = [],
  } = opts;

  const wrap = document.createElement('details');
  wrap.className = 'regen-panel';
  wrap.style.cssText = `
    margin:1rem 0;border:1px solid rgba(255,255,255,0.12);
    border-radius:10px;padding:0.6rem 1rem;
    background:rgba(99,102,241,0.06);
  `;

  const summary = document.createElement('summary');
  summary.textContent = `⚙️ ${title}`;
  summary.style.cssText = 'cursor:pointer;font-weight:500;color:#a78bfa;list-style:none;';
  wrap.appendChild(summary);

  const ta = document.createElement('textarea');
  ta.placeholder = placeholder;
  ta.rows = 3;
  ta.style.cssText = 'width:100%;margin-top:0.6rem;border-radius:6px;padding:0.5rem;font-family:inherit;';

  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;gap:0.5rem;margin-top:0.5rem;flex-wrap:wrap;align-items:center;';

  const submit = document.createElement('button');
  submit.type = 'button';
  submit.textContent = buttonLabel;
  submit.className = 'btn-primary';

  const status = document.createElement('span');
  status.style.cssText = 'font-size:0.85rem;opacity:0.8;';

  submit.addEventListener('click', async () => {
    const instructions = ta.value.trim();
    if (required && !instructions) {
      showToast('Please describe what you want changed.', 'error');
      return;
    }
    submit.disabled = true;
    status.textContent = 'Working… (this can take 30–90s)';
    try {
      const result = await onSubmit(instructions);
      status.textContent = 'Done.';
      showToast('Regenerated successfully', 'success');
      onSuccess?.(result);
      // Auto-collapse after a short delay
      setTimeout(() => { wrap.open = false; status.textContent = ''; }, 1500);
    } catch (err) {
      status.textContent = '';
      showToast(`Regenerate failed: ${err.message}`, 'error');
    } finally {
      submit.disabled = false;
    }
  });

  actions.appendChild(submit);

  extraActions.forEach((extra) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = extra.label;
    btn.className = 'btn-secondary';
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      status.textContent = 'Working…';
      try {
        const result = await extra.onClick(ta.value.trim());
        status.textContent = 'Done.';
        showToast(`${extra.label}: done`, 'success');
        extra.onSuccess?.(result);
        setTimeout(() => { status.textContent = ''; }, 1500);
      } catch (err) {
        status.textContent = '';
        showToast(`${extra.label} failed: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
      }
    });
    actions.appendChild(btn);
  });

  actions.appendChild(status);
  wrap.appendChild(ta);
  wrap.appendChild(actions);
  return wrap;
}
