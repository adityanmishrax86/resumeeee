// components/empty_state.js – reusable empty-state messaging

export function createEmptyState(message, actionText, actionHref) {
  const wrap = document.createElement('div');
  wrap.className = 'empty-state';

  const p = document.createElement('p');
  p.textContent = message;
  wrap.appendChild(p);

  if (actionText && actionHref) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = actionText;
    btn.onclick = () => { window.location.hash = actionHref; };
    wrap.appendChild(btn);
  }

  return wrap;
}
