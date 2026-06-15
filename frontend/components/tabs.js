// components/tabs.js – Simple tab navigation component

export function createTabs(tabs, initialIndex = 0) {
  const container = document.createElement('div');
  container.className = 'tabs-root';

  const tabHeader = document.createElement('div');
  tabHeader.className = 'tabs-header';
  tabHeader.setAttribute('role', 'tablist');

  const contentArea = document.createElement('div');
  contentArea.className = 'tabs-content';

  const panels = [];

  function activateTab(idx) {
    panels.forEach((p, i) => {
      p.btn.classList.toggle('active', i === idx);
      p.btn.setAttribute('aria-selected', i === idx ? 'true' : 'false');
      p.panel.hidden = i !== idx;
      if (i === idx) {
        p.panel.innerHTML = '';
        if (typeof p.render === 'function') {
          p.render(p.panel);
        }
      }
    });
  }

  tabs.forEach((tab, idx) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'tab-btn';
    btn.textContent = tab.title;
    btn.setAttribute('role', 'tab');
    btn.addEventListener('click', () => activateTab(idx));

    const panel = document.createElement('div');
    panel.className = 'tab-panel';
    panel.setAttribute('role', 'tabpanel');
    panel.hidden = idx !== initialIndex;

    tabHeader.appendChild(btn);
    contentArea.appendChild(panel);
    panels.push({ btn, panel, render: tab.content });

    if (idx === initialIndex) {
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      if (typeof tab.content === 'function') {
        tab.content(panel);
      }
    }
  });

  container.appendChild(tabHeader);
  container.appendChild(contentArea);

  return {
    element: container,
    activateTab,
  };
}
