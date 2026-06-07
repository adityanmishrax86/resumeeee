const extractBtn = document.getElementById("extractBtn");
const copyBtn = document.getElementById("copyBtn");
const output = document.getElementById("output");
const statusEl = document.getElementById("status");

function setStatus(message, type = "") {
  statusEl.textContent = message;
  statusEl.className = type;
}

async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

async function injectContentScript(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["ats_extractors.js", "content.js"]
  });
}

function sendExtractMessage(tabId) {
  return new Promise((resolve, reject) => {
    chrome.tabs.sendMessage(tabId, { type: "EXTRACT_JOB" }, (response) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      resolve(response);
    });
  });
}

async function extractJob() {
  setStatus("Extracting...", "");

  try {
    const tab = await getActiveTab();
    if (!tab || !tab.id) {
      throw new Error("No active tab found.");
    }

    await injectContentScript(tab.id);
    const response = await sendExtractMessage(tab.id);

    if (!response || !response.ok) {
      throw new Error(response?.error || "Failed to extract job details.");
    }

    output.value = JSON.stringify(response.data, null, 2);
    setStatus("Extraction completed.", "ok");
  } catch (error) {
    setStatus(error.message || "Extraction failed.", "err");
  }
}

async function copyJson() {
  const value = output.value.trim();
  if (!value) {
    setStatus("Nothing to copy yet.", "err");
    return;
  }

  try {
    await navigator.clipboard.writeText(value);
    setStatus("JSON copied to clipboard.", "ok");
  } catch {
    setStatus("Copy failed. Select and copy manually.", "err");
  }
}

extractBtn.addEventListener("click", extractJob);
copyBtn.addEventListener("click", copyJson);
