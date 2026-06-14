// screens/screen_setup.js – initial setup wizard for LLM provider + API key.

import { createCard } from '../components/card.js';
import { showToast } from '../components/toast.js';
import { loadSettings, saveSettings, clearSettings, getCachedSettings } from '../services/settings.js';

const PROVIDER_PRESETS = {
  google: {
    label: 'Google (Gemini via pydantic-ai)',
    modelPlaceholder: 'gemini-2.5-flash-preview',
    keyLabel: 'Google API key',
    keyHelp: 'Stored encrypted; exported to GOOGLE_API_KEY at runtime.',
    requiresKey: true,
  },
  nvidia: {
    label: 'NVIDIA NIM',
    modelPlaceholder: 'google/gemma-4-31b-it',
    keyLabel: 'NVIDIA API key',
    keyHelp: 'Stored encrypted; exported to NVIDIA_API_KEY at runtime.',
    requiresKey: true,
  },
  mock: {
    label: 'Mock (no external calls)',
    modelPlaceholder: 'mock',
    keyLabel: 'API key (not required)',
    keyHelp: 'Mock provider produces deterministic responses for development.',
    requiresKey: false,
  },
};

export async function loadScreenSetup(container) {
  container.innerHTML = '';

  const heading = document.createElement('h2');
  heading.textContent = 'LLM Setup';
  container.appendChild(heading);

  const subtitle = document.createElement('p');
  subtitle.className = 'hero-subtitle';
  subtitle.style.marginBottom = '1.5rem';
  subtitle.textContent =
    'Configure the model and API key the backend will use. The key is encrypted at rest and never exposed back to the browser. The app stays disabled until this is set.';
  container.appendChild(subtitle);

  const settings = (await loadSettings()) || getCachedSettings();

  const card = createCard('Provider & credentials', null);

  const statusLine = document.createElement('p');
  statusLine.className = 'field-helper';
  statusLine.style.marginBottom = '1rem';
  renderStatus(statusLine, settings);
  card.appendChild(statusLine);

  const form = document.createElement('form');
  form.style.display = 'flex';
  form.style.flexDirection = 'column';
  form.style.gap = '0.9rem';

  // Provider select
  const providerLabel = document.createElement('label');
  providerLabel.textContent = 'Provider';
  const providerSelect = document.createElement('select');
  Object.entries(PROVIDER_PRESETS).forEach(([value, cfg]) => {
    const opt = document.createElement('option');
    opt.value = value;
    opt.textContent = cfg.label;
    providerSelect.appendChild(opt);
  });
  providerSelect.value = settings?.provider || 'google';

  // Model input
  const modelLabel = document.createElement('label');
  modelLabel.textContent = 'Model';
  const modelInput = document.createElement('input');
  modelInput.type = 'text';
  modelInput.required = true;
  modelInput.value = settings?.model || '';

  // API key input
  const keyLabel = document.createElement('label');
  const keyInput = document.createElement('input');
  keyInput.type = 'password';
  keyInput.autocomplete = 'new-password';
  const keyHelp = document.createElement('p');
  keyHelp.className = 'field-helper';

  function applyProviderPreset() {
    const cfg = PROVIDER_PRESETS[providerSelect.value];
    if (!cfg) return;
    if (!modelInput.value) modelInput.placeholder = cfg.modelPlaceholder;
    else modelInput.placeholder = cfg.modelPlaceholder;
    keyLabel.textContent = cfg.keyLabel;
    keyInput.placeholder = settings?.has_api_key && settings.provider === providerSelect.value
      ? '•••••••• (leave blank to keep existing)'
      : 'Paste your API key';
    keyInput.required = cfg.requiresKey && !(settings?.has_api_key && settings.provider === providerSelect.value);
    keyHelp.textContent = cfg.keyHelp;
  }
  providerSelect.addEventListener('change', applyProviderPreset);
  applyProviderPreset();

  const saveBtn = document.createElement('button');
  saveBtn.type = 'submit';
  saveBtn.textContent = 'Save settings';

  const clearBtn = document.createElement('button');
  clearBtn.type = 'button';
  clearBtn.className = 'btn-secondary';
  clearBtn.textContent = 'Clear stored settings';
  clearBtn.style.background = 'rgba(255,255,255,0.08)';
  clearBtn.onclick = async () => {
    if (!confirm('Clear stored provider/model/API key from the backend?')) return;
    clearBtn.disabled = true;
    try {
      const next = await clearSettings();
      renderStatus(statusLine, next);
      showToast('Settings cleared', 'success');
      modelInput.value = '';
      keyInput.value = '';
      applyProviderPreset();
    } catch (err) {
      showToast('Clear failed: ' + err.message, 'error');
    } finally {
      clearBtn.disabled = false;
    }
  };

  form.appendChild(providerLabel);
  form.appendChild(providerSelect);
  form.appendChild(modelLabel);
  form.appendChild(modelInput);
  form.appendChild(keyLabel);
  form.appendChild(keyInput);
  form.appendChild(keyHelp);

  const btnRow = document.createElement('div');
  btnRow.style.display = 'flex';
  btnRow.style.gap = '0.75rem';
  btnRow.style.flexWrap = 'wrap';
  btnRow.appendChild(saveBtn);
  btnRow.appendChild(clearBtn);
  form.appendChild(btnRow);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    saveBtn.disabled = true;
    try {
      const next = await saveSettings({
        provider: providerSelect.value,
        model: modelInput.value.trim(),
        api_key: keyInput.value || null,
      });
      renderStatus(statusLine, next);
      keyInput.value = '';
      showToast('Settings saved', 'success');
      if (next?.configured) {
        // Send the user back to home so the rest of the UI re-enables.
        setTimeout(() => { window.location.hash = '#/home'; }, 600);
      }
    } catch (err) {
      showToast('Save failed: ' + err.message, 'error');
    } finally {
      saveBtn.disabled = false;
    }
  });

  card.appendChild(form);
  container.appendChild(card);
}

function renderStatus(el, settings) {
  if (!settings) {
    el.textContent = 'Loading current settings…';
    return;
  }
  const tag = settings.configured
    ? `Configured via ${settings.source} (provider=${settings.provider}, model=${settings.model || '—'}, api_key=${settings.has_api_key ? 'stored' : 'none'})`
    : 'Not configured. Set a provider, model, and API key below to enable the rest of the app.';
  el.textContent = tag;
  el.style.color = settings.configured ? '#4ade80' : '#fca5a5';
}
