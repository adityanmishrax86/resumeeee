// components/header.js – header with grouped nav, health banner, mobile menu

import { checkBackendHealth } from '../api.js';
import { hasStoredRuns } from '../state.js';
import { getRoutePath } from '../utils/hash.js';
import { isConfigured, getCachedSettings } from '../services/settings.js';

const NAV_GROUPS = [
  {
    label: 'Get Started',
    links: [
      { text: 'Home', href: '#/home' },
      { text: 'Quick Start', href: '#/quick-start' },
    ],
  },
  {
    label: 'Setup',
    links: [
      { text: 'Settings', href: '#/setup' },
      { text: 'Jobs', href: '#/jobs' },
      { text: 'Resumes', href: '#/resumes' },
    ],
  },
  {
    label: 'Results',
    links: [
      { text: 'All Results', href: '#/results' },
      { text: 'Match', href: '#/results/match' },
      { text: 'Gaps', href: '#/results/gaps' },
      { text: 'Variants', href: '#/results/variants' },
      { text: 'Interview', href: '#/results/interview' },
      { text: 'Cover Letter', href: '#/results/cover' },
    ],
    requiresRun: true,
  },
];

function createHealthBanner() {
  const banner = document.createElement('div');
  banner.id = 'health-banner';
  banner.className = 'health-banner health-banner-checking';
  banner.textContent = 'Checking backend connection…';

  checkBackendHealth().then((ok) => {
    if (ok) {
      banner.className = 'health-banner health-banner-ok';
      banner.textContent = 'Backend connected';
      setTimeout(() => banner.classList.add('health-banner-hidden'), 2500);
    } else {
      banner.className = 'health-banner health-banner-error';
      banner.innerHTML =
        'Backend offline — start the API with <code>uvicorn app.main:app --reload --port 8000</code> in <code>backend/app</code>.';
    }
  });

  return banner;
}

function createSetupBanner() {
  if (isConfigured()) return null;
  const settings = getCachedSettings();
  const banner = document.createElement('div');
  banner.className = 'health-banner health-banner-error';
  const reason = settings?._error
    ? `Backend unreachable: ${settings._error}.`
    : 'LLM provider and API key are not configured.';
  banner.innerHTML = `Setup required — ${reason} <a href="#/setup" style="color:#fafafa;text-decoration:underline;">Open Settings</a>`;
  return banner;
}

function isResultsRoute(path) {
  return path.startsWith('#/results') || ['#/match', '#/gaps', '#/variants', '#/interview', '#/cover'].includes(path);
}

const LEGACY_RESULT_ROUTES = {
  '#/match': '#/results/match',
  '#/gaps': '#/results/gaps',
  '#/variants': '#/results/variants',
  '#/interview': '#/results/interview',
  '#/cover': '#/results/cover',
};

function effectivePath(path) {
  return LEGACY_RESULT_ROUTES[path] || path;
}

export function initHeader() {
  const wrapper = document.createElement('div');
  wrapper.className = 'header-wrapper';

  wrapper.appendChild(createHealthBanner());
  const setupBanner = createSetupBanner();
  if (setupBanner) wrapper.appendChild(setupBanner);

  const header = document.createElement('header');
  header.className = 'app-header';

  const logoTitleDiv = document.createElement('a');
  logoTitleDiv.href = '#/home';
  logoTitleDiv.className = 'brand-link';

  const logo = document.createElement('img');
  logo.src = '/assets/logo.png';
  logo.alt = 'Job Copilot Logo';

  const title = document.createElement('h1');
  title.textContent = 'AI Job Copilot';
  logoTitleDiv.appendChild(logo);
  logoTitleDiv.appendChild(title);

  const menuBtn = document.createElement('button');
  menuBtn.type = 'button';
  menuBtn.className = 'nav-toggle';
  menuBtn.setAttribute('aria-label', 'Toggle navigation');
  menuBtn.textContent = 'Menu';

  const nav = document.createElement('nav');
  nav.className = 'main-nav';
  nav.id = 'main-nav';

  const currentPath = getRoutePath();
  const resolvedPath = effectivePath(currentPath);
  const runsAvailable = hasStoredRuns();
  const configured = isConfigured();

  NAV_GROUPS.forEach((group) => {
    const groupEl = document.createElement('div');
    groupEl.className = 'nav-group';

    const label = document.createElement('span');
    label.className = 'nav-group-label';
    label.textContent = group.label;
    groupEl.appendChild(label);

    const linkRow = document.createElement('div');
    linkRow.className = 'nav-group-links';

    group.links.forEach((l) => {
      const a = document.createElement('a');
      a.href = l.href;
      a.textContent = l.text;

      const linkPath = l.href.split('?')[0];
      const active =
        resolvedPath === linkPath ||
        (linkPath === '#/results' && isResultsRoute(currentPath) && resolvedPath === '#/results') ||
        (linkPath.startsWith('#/results/') && resolvedPath === linkPath);

      if (active) {
        a.classList.add('nav-active');
        a.setAttribute('aria-current', 'page');
      }

      // Disable everything except the Settings link until the backend is configured.
      const isSettingsLink = linkPath === '#/setup';
      if (!configured && !isSettingsLink) {
        a.classList.add('nav-disabled');
        a.title = 'Configure LLM provider first';
        a.addEventListener('click', (e) => {
          e.preventDefault();
          window.location.hash = '#/setup';
        });
      } else if (group.requiresRun && !runsAvailable) {
        a.classList.add('nav-disabled');
        a.title = 'Run analysis first';
        a.addEventListener('click', (e) => {
          if (!hasStoredRuns()) {
            e.preventDefault();
          }
        });
      }

      linkRow.appendChild(a);
    });

    groupEl.appendChild(linkRow);
    nav.appendChild(groupEl);
  });

  menuBtn.addEventListener('click', () => {
    nav.classList.toggle('nav-open');
    menuBtn.classList.toggle('nav-toggle-open');
  });

  header.appendChild(logoTitleDiv);
  header.appendChild(menuBtn);
  header.appendChild(nav);
  wrapper.appendChild(header);

  return wrapper;
}
