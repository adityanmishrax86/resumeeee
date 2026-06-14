// screens/screen7_interview_prep.js – Interview Preparation screen

import { createCard } from '../components/card.js';
import { getJson } from '../api.js';
import { getOrchestratorResult, listStoredRuns } from '../state.js';
import { createRegenPanel } from '../components/regen_panel.js';
import { createQACard } from '../components/qa_card.js';
import {
  getUserInterviewQuestions,
  addUserInterviewQuestion,
  removeUserInterviewQuestion,
  patchUserInterviewQuestion,
  getProfileInterviewQuestions,
  setProfileInterviewQuestions,
  removeProfileInterviewQuestion,
  patchProfileInterviewQuestion,
} from '../state.js';
import { showToast } from '../components/toast.js';

export function loadScreen7(container) {
  const title = document.createElement('h2');
  title.textContent = 'Interview Preparation';
  container.appendChild(title);

  const selCard = createCard('Select Analysis Run', null);
  selCard.style.marginBottom = '1rem';

  const jobSelect = document.createElement('select');
  const resumeSelect = document.createElement('select');
  const loadBtn = document.createElement('button');
  loadBtn.textContent = 'Load Interview Prep';

  selCard.appendChild(document.createTextNode('Job: '));
  selCard.appendChild(jobSelect);
  selCard.appendChild(document.createTextNode('  Resume: '));
  selCard.appendChild(resumeSelect);
  selCard.appendChild(loadBtn);
  container.appendChild(selCard);

  const resultCard = createCard('Interview Preparation Guide', null);
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

    const interviewData = saved.interview_research;
    if (!interviewData) {
      resultDiv.innerHTML =
        '<p style="color:#fb923c">⚠️ Interview research data is not available. The pipeline may have skipped this step (check <code>skip_interview_research</code> flag).</p>';
      return;
    }

    renderInterviewPrep(resultDiv, interviewData);
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

export function renderInterviewPrep(container, data, ctx = {}) {
  container.innerHTML = '';

  if (ctx.jobAnalysisId && (typeof ctx.onRegen === 'function' || typeof ctx.onMore === 'function')) {
    const extras = [];
    if (typeof ctx.onMore === 'function') {
      extras.push({
        label: 'Generate 10 more questions',
        onClick: (instructions) => ctx.onMore(10, instructions),
        onSuccess: (result) => renderInterviewPrep(container, result, ctx),
      });
    }
    container.appendChild(createRegenPanel({
      title: 'Regenerate interview prep',
      placeholder: 'e.g. focus on system design, add 5 SQL window-function questions, skip behavioural…',
      required: false,
      buttonLabel: 'Regenerate (replace)',
      onSubmit: (instructions) => ctx.onRegen(instructions || 'No additional instructions.'),
      onSuccess: (result) => renderInterviewPrep(container, result, ctx),
      extraActions: extras,
    }));
  }

  // Company snapshot section
  renderSection(container, '🏢 Company Snapshot', data.company_snapshot || data.company_overview || data.company, '#38bdf8');

  // Tech stack
  renderSection(container, '🛠️ Tech Stack', data.tech_stack || data.technologies, '#818cf8');

  // Resume-based questions (only when we have both ids and the generator hook)
  if (ctx.jobAnalysisId && ctx.resumeId && typeof ctx.onGenerateProfileQuestions === 'function') {
    renderProfileQuestionsSection(container, data, ctx);
  }

  // Company / expected interview questions — new two-column Q/A list
  renderQuestionsList(
    container,
    '❓ Expected Interview Questions',
    data.interview_questions || data.questions || data.expected_questions || data.role_specific_questions,
    data,
    ctx,
  );

  // Behavioral questions (legacy fallback – uses simple list)
  renderLegacyQuestions(container, '💬 Behavioral Questions', data.behavioral_questions);

  // Technical questions (legacy fallback)
  renderLegacyQuestions(container, '💻 Technical Questions', data.technical_questions);

  // Tips
  renderSection(container, '💡 Preparation Tips', data.tips || data.preparation_tips || data.advice, '#4ade80');

  // Culture fit
  renderSection(container, '🤝 Culture & Values', data.culture || data.culture_fit || data.company_culture, '#fb923c');

  // Red flags
  renderSection(container, '🚩 Things to Watch Out For', data.red_flags || data.cautions, '#f87171');

  // If nothing was rendered above, fall back to generic JSON
  if (container.children.length === 0) {
    const pre = document.createElement('pre');
    pre.style.cssText = 'background:rgba(0,0,0,0.2);padding:1rem;border-radius:8px;white-space:pre-wrap;font-size:0.85rem;line-height:1.6;';
    pre.textContent = JSON.stringify(data, null, 2);
    container.appendChild(pre);
  }
}

function renderSection(container, heading, value, color = '#fff') {
  if (!value) return;

  const section = document.createElement('div');
  section.className = 'section-grid';

  const headerContainer = document.createElement('div');
  headerContainer.className = 'section-header';
  const h4 = document.createElement('h4');
  h4.style.cssText = `color:${color};font-size:1.1rem;`;
  h4.textContent = heading;
  headerContainer.appendChild(h4);
  section.appendChild(headerContainer);

  const contentContainer = document.createElement('div');

  if (Array.isArray(value)) {
    const ul = document.createElement('ul');
    ul.style.cssText = 'margin:0;padding-left:1.2rem;line-height:1.8;';
    value.forEach(item => {
      const li = document.createElement('li');
      li.textContent = typeof item === 'object' ? JSON.stringify(item) : item;
      ul.appendChild(li);
    });
    contentContainer.appendChild(ul);
  } else if (typeof value === 'object') {
    const pre = document.createElement('pre');
    pre.style.cssText = 'background:rgba(0,0,0,0.2);padding:0.75rem;border-radius:8px;white-space:pre-wrap;font-size:0.85rem;';
    pre.textContent = JSON.stringify(value, null, 2);
    contentContainer.appendChild(pre);
  } else {
    const p = document.createElement('div');
    p.style.lineHeight = '1.7';
    p.innerHTML = window.marked ? window.marked.parse(String(value)) : String(value);
    contentContainer.appendChild(p);
  }

  section.appendChild(contentContainer);
  container.appendChild(section);
}

// Legacy collapsible <details> renderer for behavioral/technical arrays which
// may carry plain strings or simple objects and aren't part of the new Q/A
// schema. Kept untouched on purpose.
function renderLegacyQuestions(container, heading, questions) {
  if (!questions || (Array.isArray(questions) && questions.length === 0)) return;

  const section = document.createElement('div');
  section.className = 'section-grid';

  const headerContainer = document.createElement('div');
  headerContainer.className = 'section-header';
  const h4 = document.createElement('h4');
  h4.style.cssText = 'color:#fbbf24;font-size:1.1rem;';
  h4.textContent = heading;
  headerContainer.appendChild(h4);
  section.appendChild(headerContainer);

  const contentContainer = document.createElement('div');

  const items = Array.isArray(questions) ? questions : [questions];
  items.forEach((q, idx) => {
    const details = document.createElement('details');
    details.style.cssText = `
      border:1px solid rgba(255,255,255,0.1);border-radius:8px;
      margin-bottom:0.4rem;padding:0.5rem 0.75rem;
      background:rgba(255,255,255,0.03);
    `;
    const summary = document.createElement('summary');
    summary.style.cssText = 'cursor:pointer;font-weight:500;line-height:1.5;list-style:none;';
    let questionText = '';
    let answerHint = '';
    if (typeof q === 'string') {
      questionText = `Q${idx + 1}: ${q}`;
    } else if (typeof q === 'object') {
      questionText = q.question || q.q || `Q${idx + 1}`;
      answerHint = q.strong_answer_tips || q.answer || q.hint || q.guidance || '';
    }
    summary.innerHTML = window.marked ? window.marked.parseInline(questionText) : questionText;
    details.appendChild(summary);
    if (answerHint) {
      const hint = document.createElement('div');
      hint.style.cssText = 'margin-top:0.5rem;opacity:0.75;font-size:0.9rem;line-height:1.6;padding-top:0.5rem;border-top:1px solid rgba(255,255,255,0.1);';
      if (Array.isArray(answerHint)) {
        const ul = document.createElement('ul');
        ul.style.paddingLeft = '1.2rem';
        answerHint.forEach((tip) => {
          const li = document.createElement('li');
          li.innerHTML = window.marked ? window.marked.parseInline(tip) : tip;
          ul.appendChild(li);
        });
        hint.appendChild(ul);
      } else if (typeof answerHint === 'object') {
        hint.textContent = JSON.stringify(answerHint, null, 2);
      } else {
        hint.innerHTML = window.marked ? window.marked.parse(String(answerHint)) : answerHint;
      }
      details.appendChild(hint);
    }
    contentContainer.appendChild(details);
  });

  section.appendChild(contentContainer);
  container.appendChild(section);
}

// ── New two-column Q/A list with composer + streaming Ask AI ──────────────

function _buildAskAIHandler(ctx, q) {
  if (typeof ctx.onAskAIStream !== 'function') return undefined;
  return async (onChunk, signal) => {
    await ctx.onAskAIStream(
      {
        question: q.question,
        category: q.category,
        why_asked: q.why_asked,
        existing_tips: q.strong_answer_tips || [],
      },
      onChunk,
      { signal },
    );
  };
}

function renderQuestionsList(container, heading, questions, data, ctx) {
  // Pull local-only user questions (prepended) — these survive reloads via
  // localStorage but don't hit the DB unless explicitly saved.
  const jobAnalysisId = ctx.jobAnalysisId || null;
  const localUserQs = jobAnalysisId
    ? getUserInterviewQuestions(jobAnalysisId)
    : [];

  const incoming = Array.isArray(questions) ? questions : (questions ? [questions] : []);
  // De-dupe: if a user question was already promoted into role_specific_questions
  // (source==="user"), don't show the local copy too.
  const incomingTexts = new Set(
    incoming.map((q) => (q.question || '').trim().toLowerCase()),
  );
  const filteredLocal = localUserQs.filter(
    (q) => !incomingTexts.has((q.question || '').trim().toLowerCase()),
  );

  // Nothing to render at all (and no composer hook either)? Skip section.
  if (!filteredLocal.length && !incoming.length && !ctx.onSaveUserQuestion) return;

  const section = document.createElement('div');
  section.className = 'section-grid';

  const headerContainer = document.createElement('div');
  headerContainer.className = 'section-header';
  const h4 = document.createElement('h4');
  h4.style.cssText = 'color:#fbbf24;font-size:1.1rem;';
  h4.textContent = heading;
  headerContainer.appendChild(h4);
  const sub = document.createElement('div');
  sub.style.cssText = 'font-size:0.78rem;opacity:0.7;margin-top:0.25rem;';
  sub.textContent = 'Click any card for a streamed detailed answer.';
  headerContainer.appendChild(sub);
  section.appendChild(headerContainer);

  const content = document.createElement('div');

  // Composer (only when the screen wired up a save handler)
  if (jobAnalysisId) {
    content.appendChild(_buildComposer(container, data, ctx));
  }

  const list = document.createElement('div');
  list.className = 'qa-list';

  let runningIdx = 1;

  // Local user-added questions first (numbered #1, #2, …)
  filteredLocal.forEach((q) => {
    const card = createQACard({
      index: runningIdx++,
      question: q.question,
      category: q.category || 'user',
      whyAsked: q.why_asked || '',
      tips: q.strong_answer_tips || [],
      detailedAnswer: q.detailed_answer || null,
      source: 'user',
      onAskAI: _buildAskAIHandler(ctx, q),
      onSaveAnswer: typeof ctx.onSaveAnswer === 'function'
        ? async (detailedAnswer) => {
            // Persist locally first (so a refresh keeps it),
            patchUserInterviewQuestion(jobAnalysisId, q.question, { detailed_answer: detailedAnswer });
            // …then optionally promote to the DB row.
            await ctx.onSaveAnswer({ question: q.question, detailed_answer: detailedAnswer });
          }
        : async (detailedAnswer) => {
            patchUserInterviewQuestion(jobAnalysisId, q.question, { detailed_answer: detailedAnswer });
          },
      onSaveQuestion: typeof ctx.onSaveUserQuestion === 'function'
        ? async () => {
            await ctx.onSaveUserQuestion({
              question: q.question,
              category: q.category || 'user',
              why_asked: q.why_asked || '',
              strong_answer_tips: q.strong_answer_tips || [],
              detailed_answer: q.detailed_answer || null,
            });
            removeUserInterviewQuestion(jobAnalysisId, q.question);
          }
        : undefined,
      onRemove: () => {
        removeUserInterviewQuestion(jobAnalysisId, q.question);
        renderInterviewPrep(container, data, ctx);
      },
    });
    list.appendChild(card);
  });

  // Existing role-specific questions
  incoming.forEach((q) => {
    const obj = typeof q === 'string' ? { question: q } : (q || {});
    const source = obj.source === 'user' ? 'user' : obj.source === 'profile' ? 'profile' : 'company';
    const card = createQACard({
      index: runningIdx++,
      question: obj.question || obj.q || '',
      category: obj.category || '',
      whyAsked: obj.why_asked || '',
      tips: Array.isArray(obj.strong_answer_tips) ? obj.strong_answer_tips : [],
      detailedAnswer: obj.detailed_answer || null,
      source,
      onAskAI: _buildAskAIHandler(ctx, obj),
      onSaveAnswer: typeof ctx.onSaveAnswer === 'function'
        ? async (detailedAnswer) => {
            await ctx.onSaveAnswer({ question: obj.question, detailed_answer: detailedAnswer });
          }
        : undefined,
    });
    list.appendChild(card);
  });

  content.appendChild(list);
  section.appendChild(content);
  container.appendChild(section);
}

function _buildComposer(container, data, ctx) {
  const wrap = document.createElement('div');
  wrap.className = 'qa-composer';

  const row = document.createElement('div');
  row.className = 'qa-composer__row';

  const ta = document.createElement('textarea');
  ta.placeholder = 'Add your own practice question — appears at the top of the list…';
  ta.rows = 1;

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.className = 'btn-secondary';
  addBtn.textContent = 'Add';
  addBtn.addEventListener('click', () => {
    const text = ta.value.trim();
    if (!text) {
      showToast('Type a question first.', 'error');
      return;
    }
    addUserInterviewQuestion(ctx.jobAnalysisId, { question: text });
    ta.value = '';
    renderInterviewPrep(container, data, ctx);
  });

  row.appendChild(ta);
  row.appendChild(addBtn);
  wrap.appendChild(row);

  const hint = document.createElement('div');
  hint.className = 'qa-composer__hint';
  hint.textContent = 'Stays on this device only until you click Save to research on the card.';
  wrap.appendChild(hint);

  return wrap;
}

function renderProfileQuestionsSection(container, data, ctx) {
  const section = document.createElement('div');
  section.className = 'section-grid';

  const headerContainer = document.createElement('div');
  headerContainer.className = 'section-header';
  const h4 = document.createElement('h4');
  h4.style.cssText = 'color:#a78bfa;font-size:1.1rem;';
  h4.textContent = '🧠 Resume-Based Questions';
  headerContainer.appendChild(h4);
  const sub = document.createElement('div');
  sub.style.cssText = 'font-size:0.78rem;opacity:0.7;margin-top:0.25rem;';
  sub.textContent = 'Grounded in your selected resume. Local until you Save.';
  headerContainer.appendChild(sub);
  section.appendChild(headerContainer);

  const content = document.createElement('div');

  const existing = getProfileInterviewQuestions(ctx.jobAnalysisId, ctx.resumeId);

  // Trigger row (always visible so the user can regenerate)
  const trigger = document.createElement('div');
  trigger.className = 'qa-profile-trigger';

  const label = document.createElement('label');
  label.textContent = 'How many?';
  const count = document.createElement('input');
  count.type = 'number';
  count.min = '1';
  count.max = '20';
  count.value = '8';
  label.appendChild(count);
  trigger.appendChild(label);

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.className = 'btn-secondary';
  btn.textContent = existing.length
    ? 'Regenerate from my resume'
    : 'Generate questions from my resume';

  const status = document.createElement('span');
  status.className = 'qa-profile-trigger__status';

  btn.addEventListener('click', async () => {
    const n = Math.max(1, Math.min(20, parseInt(count.value, 10) || 8));
    btn.disabled = true;
    status.textContent = 'Generating…';
    try {
      const questions = await ctx.onGenerateProfileQuestions(n);
      setProfileInterviewQuestions(ctx.jobAnalysisId, ctx.resumeId, questions || []);
      status.textContent = '';
      renderInterviewPrep(container, data, ctx);
    } catch (e) {
      status.textContent = '';
      showToast(`Generation failed: ${e.message}`, 'error');
    } finally {
      btn.disabled = false;
    }
  });

  trigger.appendChild(btn);
  trigger.appendChild(status);
  content.appendChild(trigger);

  // Render the cards
  if (existing.length) {
    const list = document.createElement('div');
    list.className = 'qa-list';
    existing.forEach((q, i) => {
      const card = createQACard({
        index: i + 1,
        question: q.question,
        category: q.category || 'profile',
        whyAsked: q.why_asked || '',
        tips: q.strong_answer_tips || [],
        detailedAnswer: q.detailed_answer || null,
        source: 'profile',
        onAskAI: _buildAskAIHandler(ctx, q),
        onSaveAnswer: async (detailedAnswer) => {
          patchProfileInterviewQuestion(
            ctx.jobAnalysisId, ctx.resumeId, q.question,
            { detailed_answer: detailedAnswer },
          );
          if (typeof ctx.onSaveAnswer === 'function') {
            try { await ctx.onSaveAnswer({ question: q.question, detailed_answer: detailedAnswer }); }
            catch (_) { /* answer is still stored locally */ }
          }
        },
        onSaveQuestion: typeof ctx.onSaveUserQuestion === 'function'
          ? async () => {
              await ctx.onSaveUserQuestion({
                question: q.question,
                category: q.category || 'profile',
                why_asked: q.why_asked || '',
                strong_answer_tips: q.strong_answer_tips || [],
                detailed_answer: q.detailed_answer || null,
                source: 'profile',
              });
              removeProfileInterviewQuestion(ctx.jobAnalysisId, ctx.resumeId, q.question);
            }
          : undefined,
        onRemove: () => {
          removeProfileInterviewQuestion(ctx.jobAnalysisId, ctx.resumeId, q.question);
          renderInterviewPrep(container, data, ctx);
        },
      });
      list.appendChild(card);
    });
    content.appendChild(list);
  }

  section.appendChild(content);
  container.appendChild(section);
}
