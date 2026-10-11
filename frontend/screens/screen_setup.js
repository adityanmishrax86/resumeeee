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
  openai: {
    label: 'OpenAI (via pydantic-ai)',
    modelPlaceholder: 'gpt-4o-mini',
    keyLabel: 'OpenAI API key',
    keyHelp: 'Stored encrypted; exported to OPENAI_API_KEY at runtime.',
    requiresKey: true,
  },
  groq: {
    label: 'Groq (via pydantic-ai)',
    modelPlaceholder: 'llama-3.3-70b-versatile',
    keyLabel: 'Groq API key',
    keyHelp: 'Stored encrypted; exported to GROQ_API_KEY at runtime.',
    requiresKey: true,
  },
  mock: {
    label: 'Mock (no external calls)',
    modelPlaceholder: 'mock',
    keyLabel: 'API key (not required)',
    keyHelp: 'Mock provider produces deterministic responses for development.',
    requiresKey: false,
  },
  ollama: {
    label: 'Ollama (Local / Self-hosted)',
    modelPlaceholder: 'llama3',
    keyLabel: 'Ollama API key (optional)',
    keyHelp: 'API key is optional for local self-hosted Ollama. Required only if using a custom proxy or authenticated gateway.',
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

  // Ollama specific fields
  const ollamaContainer = document.createElement('div');
  ollamaContainer.style.display = 'none';
  ollamaContainer.style.flexDirection = 'column';
  ollamaContainer.style.gap = '0.9rem';
  ollamaContainer.style.marginTop = '0.5rem';
  ollamaContainer.style.marginBottom = '0.5rem';

  const baseUrlLabel = document.createElement('label');
  baseUrlLabel.textContent = 'Base URL';
  const baseUrlInput = document.createElement('input');
  baseUrlInput.type = 'url';
  baseUrlInput.id = 'ollama-base-url';
  baseUrlInput.placeholder = 'http://localhost:11434/v1';

  const timeoutLabel = document.createElement('label');
  timeoutLabel.textContent = 'Timeout (seconds)';
  const timeoutInput = document.createElement('input');
  timeoutInput.type = 'number';
  timeoutInput.id = 'ollama-timeout';
  timeoutInput.placeholder = '300';
  timeoutInput.min = '1';

  ollamaContainer.appendChild(baseUrlLabel);
  ollamaContainer.appendChild(baseUrlInput);
  ollamaContainer.appendChild(timeoutLabel);
  ollamaContainer.appendChild(timeoutInput);

  function applyProviderPreset() {
    const provider = providerSelect.value;
    const cfg = PROVIDER_PRESETS[provider];
    if (!cfg) return;

    if (provider === 'ollama') {
      ollamaContainer.style.display = 'flex';
      baseUrlInput.value = settings?.extra?.base_url || 'http://localhost:11434/v1';
      timeoutInput.value = settings?.extra?.timeout || '300';
    } else {
      ollamaContainer.style.display = 'none';
    }

    if (!modelInput.value) modelInput.placeholder = cfg.modelPlaceholder;
    else modelInput.placeholder = cfg.modelPlaceholder;
    keyLabel.textContent = cfg.keyLabel;
    keyInput.placeholder = settings?.has_api_key && settings.provider === provider
      ? '•••••••• (leave blank to keep existing)'
      : 'Paste your API key';
    keyInput.required = cfg.requiresKey && !(settings?.has_api_key && settings.provider === provider);
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
      baseUrlInput.value = 'http://localhost:11434/v1';
      timeoutInput.value = '300';
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
  form.appendChild(ollamaContainer);
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
      const payload = {
        provider: providerSelect.value,
        model: modelInput.value.trim(),
        api_key: keyInput.value || null,
      };
      if (providerSelect.value === 'ollama') {
        payload.base_url = baseUrlInput.value.trim() || 'http://localhost:11434/v1';
        payload.timeout = parseInt(timeoutInput.value, 10) || 300;
      }
      const next = await saveSettings(payload);
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
