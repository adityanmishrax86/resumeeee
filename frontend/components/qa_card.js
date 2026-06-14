// components/qa_card.js – numbered two-column Q/A card with streaming "Ask AI" action.
//
// Left column: index badge + question + meta (category, why_asked, source, optional Remove).
// Right column: short tips bullet list (preview) + Ask-AI button. On click, the
// detailed answer area expands below the tips and streams tokens via the
// onAskAI() callback supplied by the screen. After a stream completes, Save /
// Regenerate / Copy actions appear. If a detailedAnswer is passed in already
// (e.g. already-persisted), the answer area renders immediately and the
// Ask-AI button is omitted.

import { showToast } from './toast.js';

const ACCENTS = {
  company: '#fbbf24',
  profile: '#a78bfa',
  user: '#34d399',
};

function _renderMarkdownInline(text) {
  if (!text) return '';
  if (window.marked?.parseInline) return window.marked.parseInline(text);
  return text;
}

function _renderMarkdownBlock(text) {
  if (!text) return '';
  if (window.marked?.parse) return window.marked.parse(text);
  return text;
}

/**
 * @param {object} opts
 * @param {number} opts.index                       1-based display number
 * @param {string} opts.question                    question text
 * @param {string} [opts.category]
 * @param {string} [opts.whyAsked]
 * @param {string[]} [opts.tips]                    short tip bullets (preview)
 * @param {string|null} [opts.detailedAnswer]       if present, renders immediately
 * @param {'company'|'profile'|'user'} [opts.source='company']
 * @param {(onChunk: (s:string)=>void, signal: AbortSignal) => Promise<string>} [opts.onAskAI]
 * @param {(detailedAnswer: string) => Promise<void>} [opts.onSaveAnswer]
 * @param {() => Promise<void>} [opts.onSaveQuestion]   only used for user-added cards
 * @param {() => void} [opts.onRemove]              only used for user/profile local-only cards
 * @returns {HTMLElement}
 */
export function createQACard(opts) {
  const {
    index,
    question,
    category = '',
    whyAsked = '',
    tips = [],
    detailedAnswer = null,
    source = 'company',
    onAskAI,
    onSaveAnswer,
    onSaveQuestion,
    onRemove,
  } = opts;

  const accent = ACCENTS[source] || ACCENTS.company;

  const card = document.createElement('div');
  card.className = 'qa-card';
  card.style.setProperty('--qa-accent', accent);

  // ── Left column ──────────────────────────────────────────────────────────
  const left = document.createElement('div');
  left.className = 'qa-card__left';

  const idx = document.createElement('div');
  idx.className = 'qa-card__index';
  idx.textContent = String(index);
  left.appendChild(idx);

  const leftBody = document.createElement('div');
  leftBody.className = 'qa-card__left-body';

  const qEl = document.createElement('div');
  qEl.className = 'qa-card__question';
  qEl.innerHTML = _renderMarkdownInline(question);
  leftBody.appendChild(qEl);

  const meta = document.createElement('div');
  meta.className = 'qa-card__meta';
  if (category) {
    const pill = document.createElement('span');
    pill.className = 'qa-card__pill';
    pill.textContent = category;
    meta.appendChild(pill);
  }
  if (source && source !== 'company') {
    const tag = document.createElement('span');
    tag.className = `qa-card__tag qa-card__tag--${source}`;
    tag.textContent = source === 'user' ? 'your question' : 'from resume';
    meta.appendChild(tag);
  }
  if (whyAsked) {
    const why = document.createElement('div');
    why.className = 'qa-card__why';
    why.textContent = whyAsked;
    meta.appendChild(why);
  }
  if (meta.children.length) leftBody.appendChild(meta);

  if (typeof onRemove === 'function') {
    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'qa-card__remove';
    removeBtn.textContent = 'Remove';
    removeBtn.addEventListener('click', () => onRemove());
    leftBody.appendChild(removeBtn);
  }

  if (typeof onSaveQuestion === 'function') {
    const saveQBtn = document.createElement('button');
    saveQBtn.type = 'button';
    saveQBtn.className = 'qa-card__save-q btn-secondary';
    saveQBtn.textContent = 'Save to research';
    saveQBtn.addEventListener('click', async () => {
      saveQBtn.disabled = true;
      try {
        await onSaveQuestion();
        showToast('Question saved to research', 'success');
      } catch (e) {
        showToast(`Save failed: ${e.message}`, 'error');
        saveQBtn.disabled = false;
      }
    });
    leftBody.appendChild(saveQBtn);
  }

  left.appendChild(leftBody);
  card.appendChild(left);

  // ── Right column ─────────────────────────────────────────────────────────
  const right = document.createElement('div');
  right.className = 'qa-card__right';

  // Tips preview
  const tipsBox = document.createElement('div');
  tipsBox.className = 'qa-card__tips';
  if (tips && tips.length) {
    const h = document.createElement('div');
    h.className = 'qa-card__tips-heading';
    h.textContent = 'Short answer tips';
    tipsBox.appendChild(h);
    const ul = document.createElement('ul');
    tips.forEach((t) => {
      const li = document.createElement('li');
      li.innerHTML = _renderMarkdownInline(t);
      ul.appendChild(li);
    });
    tipsBox.appendChild(ul);
  } else {
    const empty = document.createElement('div');
    empty.className = 'qa-card__tips-empty';
    empty.textContent = 'No short tips yet — click Ask AI for a detailed answer.';
    tipsBox.appendChild(empty);
  }
  right.appendChild(tipsBox);

  // Answer area + controls
  const answerArea = document.createElement('div');
  answerArea.className = 'qa-card__answer';
  answerArea.hidden = !detailedAnswer;

  const answerBody = document.createElement('div');
  answerBody.className = 'qa-card__answer-body';
  if (detailedAnswer) {
    answerBody.innerHTML = _renderMarkdownBlock(detailedAnswer);
  }
  answerArea.appendChild(answerBody);

  const cursor = document.createElement('span');
  cursor.className = 'qa-card__cursor';
  cursor.hidden = true;
  answerArea.appendChild(cursor);

  right.appendChild(answerArea);

  const controls = document.createElement('div');
  controls.className = 'qa-card__controls';
  right.appendChild(controls);

  // Track stream state
  let currentController = null;
  let bufferedAnswer = detailedAnswer || '';

  function _renderBuffered() {
    answerBody.innerHTML = _renderMarkdownBlock(bufferedAnswer);
  }

  function _setControlsForIdle({ hasAnswer }) {
    controls.innerHTML = '';
    if (typeof onAskAI === 'function') {
      const askBtn = document.createElement('button');
      askBtn.type = 'button';
      askBtn.className = 'qa-card__ask-btn btn-primary';
      askBtn.textContent = hasAnswer ? 'Ask AI again' : 'Ask AI for detailed answer';
      askBtn.addEventListener('click', () => _startStream());
      controls.appendChild(askBtn);
    }
    if (hasAnswer) {
      const copyBtn = document.createElement('button');
      copyBtn.type = 'button';
      copyBtn.className = 'qa-card__copy-btn btn-secondary';
      copyBtn.textContent = 'Copy';
      copyBtn.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(bufferedAnswer);
          showToast('Copied to clipboard', 'success');
        } catch {
          showToast('Copy failed', 'error');
        }
      });
      controls.appendChild(copyBtn);

      if (typeof onSaveAnswer === 'function') {
        const saveBtn = document.createElement('button');
        saveBtn.type = 'button';
        saveBtn.className = 'qa-card__save-a btn-secondary';
        saveBtn.textContent = 'Save answer';
        saveBtn.addEventListener('click', async () => {
          saveBtn.disabled = true;
          try {
            await onSaveAnswer(bufferedAnswer);
            showToast('Answer saved to research', 'success');
          } catch (e) {
            showToast(`Save failed: ${e.message}`, 'error');
            saveBtn.disabled = false;
          }
        });
        controls.appendChild(saveBtn);
      }
    }
  }

  function _setControlsForStreaming() {
    controls.innerHTML = '';
    const stopBtn = document.createElement('button');
    stopBtn.type = 'button';
    stopBtn.className = 'qa-card__stop-btn btn-secondary';
    stopBtn.textContent = 'Stop';
    stopBtn.addEventListener('click', () => {
      if (currentController) currentController.abort();
    });
    controls.appendChild(stopBtn);
  }

  async function _startStream() {
    if (!onAskAI) return;
    // Abort any in-flight request first.
    if (currentController) {
      currentController.abort();
    }
    currentController = new AbortController();
    bufferedAnswer = '';
    answerBody.innerHTML = '';
    answerArea.hidden = false;
    cursor.hidden = false;
    tipsBox.classList.add('qa-card__tips--dim');
    _setControlsForStreaming();

    try {
      await onAskAI((chunk) => {
        bufferedAnswer += chunk;
        _renderBuffered();
        answerArea.scrollTop = answerArea.scrollHeight;
      }, currentController.signal);
    } catch (err) {
      if (err?.name === 'AbortError') {
        // User stopped mid-stream — keep what we have.
        bufferedAnswer += '\n\n_[stopped]_';
        _renderBuffered();
      } else {
        showToast(`Stream failed: ${err.message}`, 'error');
        if (!bufferedAnswer) {
          answerArea.hidden = true;
        }
      }
    } finally {
      cursor.hidden = true;
      tipsBox.classList.remove('qa-card__tips--dim');
      currentController = null;
      _setControlsForIdle({ hasAnswer: !!bufferedAnswer });
    }
  }

  _setControlsForIdle({ hasAnswer: !!detailedAnswer });
  card.appendChild(right);

  return card;
}
