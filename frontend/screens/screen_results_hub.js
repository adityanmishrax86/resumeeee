// screens/screen_results_hub.js – unified results hub with tabs

import { createCard } from '../components/card.js';
import { createTabs } from '../components/tabs.js';
import { createEmptyState } from '../components/empty_state.js';
import { showToast } from '../components/toast.js';
import { setActiveRun, resolveRunContext, hasStoredRuns, getOrchestratorResult, patchOrchestratorResult } from '../state.js';
import { getHashParams, getRoutePath, buildHash } from '../utils/hash.js';
import { postJson, streamPost } from '../api.js';
import {
  fetchJobResumeOptions,
  fillJobSelect,
  fillResumeSelect,
  loadMatchData,
  loadGapData,
  loadVariantsData,
  loadInterviewData,
  loadCoverLetterData,
} from '../services/results_loaders.js';
import { renderMatch } from './screen4_match_score.js';
import { renderGapAnalysis } from './screen5_gap_analysis.js';
import { renderResumeVariants } from './screen6_resume_variants.js';
import { renderInterviewPrep } from './screen7_interview_prep.js';
import { renderCoverLetter } from './screen_cover_letter.js';

const TAB_INDEX = { match: 0, gaps: 1, variants: 2, interview: 3, cover: 4 };

function tabFromRoute(routePath, hashParams) {
  const fromQuery = hashParams.get('tab');
  if (fromQuery && TAB_INDEX[fromQuery] != null) return fromQuery;

  if (routePath === '#/results/match' || routePath === '#/match') return 'match';
  if (routePath === '#/results/gaps' || routePath === '#/gaps') return 'gaps';
  if (routePath === '#/results/variants' || routePath === '#/variants') return 'variants';
  if (routePath === '#/results/interview' || routePath === '#/interview') return 'interview';
  if (routePath === '#/results/cover' || routePath === '#/cover') return 'cover';
  return 'match';
}

export function loadResultsHub(container, forcedTab) {
  const hashParams = getHashParams();
  const routePath = getRoutePath();
  const initialTab = forcedTab || tabFromRoute(routePath, hashParams);
  const { jobId: ctxJob, resumeId: ctxResume } = resolveRunContext(hashParams);

  const title = document.createElement('h2');
  title.textContent = 'Analysis Results';
  container.appendChild(title);

  if (!hasStoredRuns()) {
    container.appendChild(
      createEmptyState(
        'No analysis results yet. Run the pipeline from Quick Start or Run Analysis.',
        'Go to Quick Start',
        '#/quick-start'
      )
    );
    return;
  }

  const selCard = createCard('Select Job & Resume', null);
  selCard.className = 'card results-selector';

  const jobSelect = document.createElement('select');
  jobSelect.id = 'results-job-select';
  const resumeSelect = document.createElement('select');
  resumeSelect.id = 'results-resume-select';
  const loadBtn = document.createElement('button');
  loadBtn.type = 'button';
  loadBtn.textContent = 'Load Results';

  const selectorRow = document.createElement('div');
  selectorRow.className = 'results-selector-row';

  const jobLabel = document.createElement('label');
  jobLabel.textContent = 'Job';
  jobLabel.htmlFor = 'results-job-select';
  const resumeLabel = document.createElement('label');
  resumeLabel.textContent = 'Resume';
  resumeLabel.htmlFor = 'results-resume-select';

  selectorRow.appendChild(jobLabel);
  selectorRow.appendChild(jobSelect);
  selectorRow.appendChild(resumeLabel);
  selectorRow.appendChild(resumeSelect);
  selectorRow.appendChild(loadBtn);
  selCard.appendChild(selectorRow);
  container.appendChild(selCard);

  const tabsCard = createCard('', null);
  tabsCard.className = 'card results-tabs-card';
  container.appendChild(tabsCard);

  let tabsApi = null;
  let currentJobId = ctxJob;
  let currentResumeId = ctxResume;

  async function renderTabContent(panel, tabKey) {
    const jobId = jobSelect.value || currentJobId;
    const resumeId = resumeSelect.value || currentResumeId;

    if (!jobId || !resumeId) {
      panel.appendChild(createEmptyState('Select a job and resume above.', 'Run Analysis', '#/analysis'));
      return;
    }

    panel.innerHTML = '<p class="loading-text">Loading…</p>';

    try {
      let data;
      if (tabKey === 'match') data = await loadMatchData(jobId, resumeId);
      else if (tabKey === 'gaps') data = loadGapData(jobId, resumeId);
      else if (tabKey === 'variants') data = loadVariantsData(jobId, resumeId);
      else if (tabKey === 'interview') data = loadInterviewData(jobId, resumeId);
      else data = loadCoverLetterData(jobId, resumeId);

      panel.innerHTML = '';
      const saved = getOrchestratorResult(jobId, resumeId) || {};

      if (tabKey === 'match') {
        renderMatch(panel, data);
      } else if (tabKey === 'gaps') {
        renderGapAnalysis(panel, data);
      } else if (tabKey === 'variants') {
        renderResumeVariants(panel, data, {
          resumeId,
          gapAnalysisId: saved.gap_analysis_id,
          jobAnalysisId: saved.job_analysis_id,
          onRegen: async (custom_instructions) => {
            const result = await postJson('/api/agents/resume-rewrite/regen', {
              resume_id: resumeId,
              gap_analysis_id: saved.gap_analysis_id,
              job_analysis_id: saved.job_analysis_id,
              custom_instructions,
            });
            patchOrchestratorResult(jobId, resumeId, { resume_rewrite: result });
            return result;
          },
        });
      } else if (tabKey === 'interview') {
        renderInterviewPrep(panel, data, {
          jobAnalysisId: saved.job_analysis_id,
          resumeId,
          onRegen: async (custom_instructions) => {
            const result = await postJson('/api/agents/interview-research/regen', {
              job_analysis_id: saved.job_analysis_id,
              custom_instructions,
            });
            patchOrchestratorResult(jobId, resumeId, { interview_research: result });
            return result;
          },
          onMore: async (count, custom_instructions) => {
            const result = await postJson('/api/agents/interview-research/more', {
              job_analysis_id: saved.job_analysis_id,
              count,
              custom_instructions: custom_instructions || null,
            });
            patchOrchestratorResult(jobId, resumeId, { interview_research: result });
            return result;
          },
          onAskAIStream: async (payload, onChunk, { signal } = {}) => {
            await streamPost(
              '/api/agents/interview-research/answer/stream',
              {
                job_analysis_id: saved.job_analysis_id,
                question: payload.question,
                category: payload.category || null,
                why_asked: payload.why_asked || null,
                existing_tips: payload.existing_tips || null,
              },
              onChunk,
              { signal },
            );
          },
          onSaveAnswer: async ({ question, detailed_answer }) => {
            if (!saved.job_analysis_id) return null;
            const result = await postJson('/api/agents/interview-research/save', {
              job_analysis_id: saved.job_analysis_id,
              updated_answers: [{ question, detailed_answer }],
            });
            patchOrchestratorResult(jobId, resumeId, { interview_research: result });
            return result;
          },
          onSaveUserQuestion: async (question) => {
            if (!saved.job_analysis_id) return null;
            const result = await postJson('/api/agents/interview-research/save', {
              job_analysis_id: saved.job_analysis_id,
              user_questions: [question],
            });
            patchOrchestratorResult(jobId, resumeId, { interview_research: result });
            // Re-render so the freshly saved user question moves out of the
            // local composer list and into the persisted numbered list.
            renderTabContent(panel, 'interview');
            return result;
          },
          onGenerateProfileQuestions: async (count) => {
            const result = await postJson('/api/agents/interview-research/profile-questions', {
              resume_id: resumeId,
              job_analysis_id: saved.job_analysis_id || null,
              count,
            });
            return result?.questions || [];
          },
        });
      } else {
        // cover
        renderCoverLetter(panel, data, {
          resumeId,
          jobAnalysisId: saved.job_analysis_id,
          gapAnalysisId: saved.gap_analysis_id,
          onRegen: async (custom_instructions) => {
            const result = await postJson('/api/agents/cover-letter', {
              resume_id: resumeId,
              job_analysis_id: saved.job_analysis_id || null,
              gap_analysis_id: saved.gap_analysis_id || null,
              custom_instructions: custom_instructions || null,
            });
            patchOrchestratorResult(jobId, resumeId, { cover_letter: result });
            return result;
          },
        });
      }

      currentJobId = jobId;
      currentResumeId = resumeId;
      setActiveRun(jobId, resumeId);
    } catch (e) {
      panel.innerHTML = '';
      panel.appendChild(createEmptyState(e.message, 'Run Analysis', '#/analysis'));
    }
  }

  function initTabs() {
    tabsCard.innerHTML = '';
    tabsApi = createTabs(
      [
        { title: 'Match Score', content: (panel) => renderTabContent(panel, 'match') },
        { title: 'Gap Analysis', content: (panel) => renderTabContent(panel, 'gaps') },
        { title: 'Resume Variants', content: (panel) => renderTabContent(panel, 'variants') },
        { title: 'Interview Prep', content: (panel) => renderTabContent(panel, 'interview') },
        { title: 'Cover Letter', content: (panel) => renderTabContent(panel, 'cover') },
      ],
      TAB_INDEX[initialTab] ?? 0
    );
    tabsCard.appendChild(tabsApi.element);
  }

  async function populateAndLoad(autoLoad = true) {
    try {
      const { jobs, resumes } = await fetchJobResumeOptions();
      fillJobSelect(jobSelect, jobs, currentJobId);
      fillResumeSelect(resumeSelect, resumes, currentResumeId);

      if (!jobSelect.value && jobs[0]) jobSelect.value = jobs[0].id;
      if (!resumeSelect.value && resumes[0]) resumeSelect.value = resumes[0].id;

      initTabs();

      if (autoLoad && jobSelect.value && resumeSelect.value) {
        tabsApi.activateTab(TAB_INDEX[initialTab] ?? 0);
      }
    } catch (e) {
      showToast('Failed to load jobs/resumes: ' + e.message, 'error');
      selCard.appendChild(
        createEmptyState('Could not reach the backend.', 'Check Setup', '#/home')
      );
    }
  }

  loadBtn.addEventListener('click', () => {
    if (!tabsApi) {
      populateAndLoad(true);
      return;
    }
    const buttons = [...tabsCard.querySelectorAll('.tab-btn')];
    const activeBtn = tabsCard.querySelector('.tab-btn.active');
    const idx = Math.max(0, buttons.indexOf(activeBtn));
    tabsApi.activateTab(idx);
  });

  jobSelect.addEventListener('change', () => {
    if (jobSelect.value && resumeSelect.value) {
      setActiveRun(jobSelect.value, resumeSelect.value);
    }
  });
  resumeSelect.addEventListener('change', () => {
    if (jobSelect.value && resumeSelect.value) {
      setActiveRun(jobSelect.value, resumeSelect.value);
    }
  });

  populateAndLoad(true);

  window.addEventListener('orchestratorDone', (e) => {
    currentJobId = e.detail?.jobId || currentJobId;
    currentResumeId = e.detail?.resumeId || currentResumeId;
    populateAndLoad(true);
  });
}

/** Legacy screen loaders redirect to the results hub. */
export function loadScreen4(c) { loadResultsHub(c, 'match'); }
export function loadScreen5(c) { loadResultsHub(c, 'gaps'); }
export function loadScreen6(c) { loadResultsHub(c, 'variants'); }
export function loadScreen7(c) { loadResultsHub(c, 'interview'); }
export function loadScreenCover(c) { loadResultsHub(c, 'cover'); }
