// components/card.js – reusable glass card component

export function createCard(title, content) {
  const card = document.createElement('div');
  card.className = 'card glass';
  if (title) {
    const h = document.createElement('h2');
    h.textContent = title;
    h.style.marginBottom = '0.5rem';
    card.appendChild(h);
  }
  if (content) {
    if (typeof content === 'string') {
      const p = document.createElement('p');
      p.innerHTML = content;
      card.appendChild(p);
    } else if (content instanceof HTMLElement) {
      card.appendChild(content);
    } else if (Array.isArray(content)) {
      content.forEach(c => card.appendChild(c));
    }
  }
  return card;
}
