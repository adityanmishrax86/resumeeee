// screens/screen2_resume_select.js – Resume Selection / Upload screen

import { createCard } from '../components/card.js';
import { createEmptyState } from '../components/empty_state.js';
import { showToast } from '../components/toast.js';
import { getJson, postJson, deleteJson } from '../api.js';

export function loadScreen2(container) {
  const title = document.createElement('h2');
  title.textContent = 'Resume Selection / Upload';
  container.appendChild(title);

  const uploadCard = createCard('Upload Resume (Markdown)', null);

  const form = document.createElement('form');
  form.style.display = 'flex';
  form.style.flexDirection = 'column';
  form.style.gap = '0.8rem';

  const nameLabel = document.createElement('label');
  nameLabel.textContent = 'Resume Name';
  const nameInput = document.createElement('input');
  nameInput.type = 'text';
  nameInput.required = true;

  const fileLabel = document.createElement('label');
  fileLabel.textContent = 'Markdown File (.md or .txt)';
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = '.md,.txt';

  const masterLabel = document.createElement('label');
  const masterCheckbox = document.createElement('input');
  masterCheckbox.type = 'checkbox';
  masterLabel.appendChild(masterCheckbox);
  masterLabel.appendChild(document.createTextNode(' Set as master resume'));

  const uploadBtn = document.createElement('button');
  uploadBtn.type = 'submit';
  uploadBtn.textContent = 'Upload Resume';

  form.appendChild(nameLabel);
  form.appendChild(nameInput);
  form.appendChild(fileLabel);
  form.appendChild(fileInput);
  form.appendChild(masterLabel);
  form.appendChild(uploadBtn);

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    uploadBtn.disabled = true;
    try {
      const file = fileInput.files[0];
      if (!file) throw new Error('Please select a file');
      const text = await file.text();
      const payload = {
        name: nameInput.value.trim(),
        content: text,
        is_master: masterCheckbox.checked,
      };
      const res = await postJson('/api/resumes', payload);
      showToast('Resume uploaded successfully', 'success');
      nameInput.value = '';
      fileInput.value = '';
      const event = new CustomEvent('resumeAdded', { detail: { resumeId: res.resume_id } });
      window.dispatchEvent(event);
      refreshResumes();
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      uploadBtn.disabled = false;
    }
  });

  uploadCard.appendChild(form);
  container.appendChild(uploadCard);

  // List existing resumes
  const listCard = createCard('Saved Resumes', null);
  const tableWrap = document.createElement('div');
  tableWrap.style.overflowX = 'auto';
  listCard.appendChild(tableWrap);
  container.appendChild(listCard);

  async function refreshResumes() {
    try {
      const resumes = await getJson('/api/resumes');
      tableWrap.innerHTML = '';
      if (resumes.length === 0) {
        tableWrap.appendChild(createEmptyState('No resumes yet.', 'Upload above', null));
        return;
      }
      const table = document.createElement('table');
      table.className = 'data-table';
      table.style.width = '100%';
      table.innerHTML = '<thead><tr><th>Name</th><th>Master</th><th>Created</th><th></th></tr></thead>';
      const tbody = document.createElement('tbody');
      resumes.forEach((r) => {
        const tr = document.createElement('tr');
        const cells = [
          r.name,
          r.is_master ? '★' : '',
          r.created_at ? new Date(r.created_at).toLocaleString() : '—',
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
          if (!confirm(`Delete resume "${r.name}"? This removes all derived analyses for this resume.`)) return;
          delBtn.disabled = true;
          try {
            await deleteJson(`/api/resumes/${r.id}`);
            showToast('Resume deleted', 'success');
            refreshResumes();
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
      showToast('Failed to load resumes: ' + err.message, 'error');
    }
  }

  refreshResumes();
  window.addEventListener('resumeAdded', refreshResumes);
}
