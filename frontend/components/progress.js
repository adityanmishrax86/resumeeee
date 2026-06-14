// components/progress.js – Simple progress bar component

export function createProgressBar() {
  const wrapper = document.createElement('div');
  wrapper.className = 'progress';
  const inner = document.createElement('div');
  inner.className = 'inner';
  wrapper.appendChild(inner);

  return {
    element: wrapper,
    setProgress(percent) {
      inner.style.width = `${Math.min(100, Math.max(0, percent))}%`;
    },
    complete() {
      inner.style.width = '100%';
    },
  };
}
