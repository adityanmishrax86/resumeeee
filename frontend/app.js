// app.js - Main entry point and simple SPA router

import { initHeader } from './components/header.js';
import { initFooter } from './components/footer.js';
import { loadScreen0 } from './screens/screen0_home.js';
import { loadScreen1 } from './screens/screen1_job_ingest.js';
import { loadScreen2 } from './screens/screen2_resume_select.js';
import { loadScreen8 } from './screens/screen8_quick_start.js';
import { loadScreenSetup } from './screens/screen_setup.js';
import {
  loadResultsHub,
  loadScreen4,
  loadScreen5,
  loadScreen6,
  loadScreen7,
  loadScreenCover,
} from './screens/screen_results_hub.js';
import { getRoutePath } from './utils/hash.js';
import { loadSettings, isConfigured } from './services/settings.js';

const routes = {
  '#/home': loadScreen0,
  '#/jobs': loadScreen1,
  '#/resumes': loadScreen2,
  // Legacy `#/analysis` deep links land on Quick Start now.
  '#/analysis': loadScreen8,
  '#/quick-start': loadScreen8,
  '#/results': (main) => loadResultsHub(main, 'match'),
  '#/results/match': (main) => loadResultsHub(main, 'match'),
  '#/results/gaps': (main) => loadResultsHub(main, 'gaps'),
  '#/results/variants': (main) => loadResultsHub(main, 'variants'),
  '#/results/interview': (main) => loadResultsHub(main, 'interview'),
  '#/results/cover': (main) => loadResultsHub(main, 'cover'),
  '#/match': loadScreen4,
  '#/gaps': loadScreen5,
  '#/variants': loadScreen6,
  '#/interview': loadScreen7,
  '#/cover': loadScreenCover,
  '#/setup': loadScreenSetup,
};

const SETUP_ROUTE = '#/setup';

async function router() {
  // Ensure we know whether the backend is configured before deciding which
  // screen to render. The settings service caches the result so this is cheap
  // after the first call.
  await loadSettings();

  let routePath = getRoutePath();

  // Gate: every route except setup itself requires configuration.
  if (!isConfigured() && routePath !== SETUP_ROUTE) {
    if (window.location.hash !== SETUP_ROUTE) {
      window.location.hash = SETUP_ROUTE;
      return; // hashchange will trigger router() again
    }
    routePath = SETUP_ROUTE;
  }

  const loader = routes[routePath] || loadScreen0;
  const appDiv = document.getElementById('app');
  appDiv.innerHTML = '';

  const header = initHeader();
  const main = document.createElement('main');
  main.className = 'glass';
  const footer = initFooter();

  appDiv.appendChild(header);
  appDiv.appendChild(main);
  appDiv.appendChild(footer);
  loader(main);
}

window.addEventListener('hashchange', router);
window.addEventListener('load', router);

export { router, getRoutePath };
