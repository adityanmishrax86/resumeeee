// screens/screen1_job_ingest.js – Job Ingestion screen

import { createCard } from '../components/card.js';
import { createEmptyState } from '../components/empty_state.js';
import { showToast } from '../components/toast.js';
import { getJson, postJson, deleteJson } from '../api.js';

export function loadScreen1(container) {
  const title = document.createElement('h2');
  title.textContent = 'Job Ingestion';
  container.appendChild(title);

  const card = createCard('Ingest a Job Description', null);

  const form = document.createElement('form');
  form.style.display = 'flex';
  form.style.flexDirection = 'column';
  form.style.gap = '0.8rem';

  const sourceLabel = document.createElement('label');
  sourceLabel.textContent = 'Source (e.g., LinkedIn, Manual)';
  const sourceInput = document.createElement('input');
  sourceInput.type = 'text';
  sourceInput.required = true;

  const descriptionLabel = document.createElement('label');
  descriptionLabel.textContent = 'Job Description (JSON or Markdown)';
  const helper = document.createElement('p');
  helper.className = 'field-helper';
  helper.textContent = 'Paste extension JSON or plain markdown. JSON is auto-detected.';
  const descriptionArea = document.createElement('textarea');
  descriptionArea.rows = 8;
  descriptionArea.required = true;

  const ingestBtn = document.createElement('button');
  ingestBtn.type = 'submit';
  ingestBtn.textContent = 'Ingest Job';

  form.appendChild(sourceLabel);
  form.appendChild(sourceInput);
  form.appendChild(descriptionLabel);
  form.appendChild(helper);
  form.appendChild(descriptionArea);
  form.appendChild(ingestBtn);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    ingestBtn.disabled = true;
    try {
      let payloadObj;
      try {
        payloadObj = JSON.parse(descriptionArea.value);
      } catch (err) {
        payloadObj = { description: descriptionArea.value };
      }

      const payload = {
        source: sourceInput.value.trim(),
        payload: payloadObj,
      };
      const res = await postJson('/api/jobs/ingest', payload);
      showToast(`Job stored successfully`, 'success');
      descriptionArea.value = '';
      const event = new CustomEvent('jobAdded', { detail: { jobId: res.job_id } });
      window.dispatchEvent(event);
      refreshJobs();
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      ingestBtn.disabled = false;
    }
  });

  card.appendChild(form);
  container.appendChild(card);

  // Load existing jobs list below the form
  const listCard = createCard('Job History', null);
  const tableWrap = document.createElement('div');
  tableWrap.style.overflowX = 'auto';
  listCard.appendChild(tableWrap);
  container.appendChild(listCard);

  async function refreshJobs() {
    try {
      const jobs = await getJson('/api/jobs');
      tableWrap.innerHTML = '';
      if (jobs.length === 0) {
        tableWrap.appendChild(createEmptyState('No jobs yet.', 'Ingest above', null));
        return;
      }
      const table = document.createElement('table');
      table.className = 'data-table';
      table.style.width = '100%';
      table.innerHTML = '<thead><tr><th>Role</th><th>Company</th><th>Source</th><th>Created</th><th></th></tr></thead>';
      const tbody = document.createElement('tbody');
      jobs.forEach((j) => {
        const tr = document.createElement('tr');
        const cells = [
          j.role_title || 'Untitled',
          j.company_name || 'Unknown',
          j.source || '—',
          j.created_at ? new Date(j.created_at).toLocaleString() : '—',
        ];
        cells.forEach((text) => {
          const td = document.createElement('td');
          td.textContent = text;
          tr.appendChild(td);
        });
        const actionTd = document.createElement('td');
        const delBtn = document.createElement('button');
        delBtn.textContent = 'Delete';
        delBtn.className = 'btn-danger';
        delBtn.onclick = async () => {
          if (!confirm(`Delete "${j.role_title || 'Untitled'}" at ${j.company_name || 'Unknown'}? This removes all derived analyses for this job.`)) return;
          delBtn.disabled = true;
          try {
            await deleteJson(`/api/jobs/${j.id}`);
            showToast('Job deleted', 'success');
            refreshJobs();
          } catch (err) {
            showToast('Delete failed: ' + err.message, 'error');
            delBtn.disabled = false;
          }
        };
        actionTd.appendChild(delBtn);
        tr.appendChild(actionTd);
        tbody.appendChild(tr);
      });
      table.appendChild(tbody);
      tableWrap.appendChild(table);
    } catch (err) {
      showToast('Failed to load jobs: ' + err.message, 'error');
    }
  }

  refreshJobs();
  window.addEventListener('jobAdded', refreshJobs);
}
