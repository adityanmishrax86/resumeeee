// components/toast.js – lightweight in-app notifications

let container = null;

function ensureContainer() {
  if (container && document.body.contains(container)) return container;
  container = document.createElement('div');
  container.id = 'toast-container';
  container.className = 'toast-container';
  container.setAttribute('aria-live', 'polite');
  document.body.appendChild(container);
  return container;
}

/**
 * @param {string} message
 * @param {'info'|'success'|'error'} type
 * @param {number} durationMs
 */
export function showToast(message, type = 'info', durationMs = 4000) {
  const root = ensureContainer();
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  root.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));

  const remove = () => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 300);
  };

  setTimeout(remove, durationMs);
  toast.addEventListener('click', remove);
}
