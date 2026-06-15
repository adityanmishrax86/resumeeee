# AI Job Copilot

An intelligent job-hunting automation platform that helps candidates optimize their resumes, identify skill gaps, and prepare for interviews — all through a 6-agent AI pipeline.

---

## Overview

AI Job Copilot takes a job description and a candidate's resume, then runs them through a sequential multi-agent pipeline that:

1. Analyzes the job description for required skills, seniority, domain, and ATS keywords
2. Analyzes the resume for skills, experience, and qualifications
3. Scores how well the resume matches the job (0–100)
4. Identifies skill gaps by severity with bridge strategies
5. Rewrites the resume with tailored wording and ATS-optimized bullets
6. Researches the company and role for interview preparation

Results are delivered asynchronously in the browser as each agent completes its step.

---

## Architecture

The project has three parts that work together:

```
Chrome Extension  →  Frontend SPA  →  FastAPI Backend  →  PostgreSQL
     (job extraction)   (UI/polling)    (6-agent pipeline)    (persistence)
```

### Backend — `backend/`

Built with **FastAPI** and **pydantic-ai**, the backend exposes a REST API and runs a background orchestration pipeline.

**Agents** (`backend/app/agents/`)

| Agent | Purpose |
|---|---|
| `job_analyzer_agent.py` | Parses raw job text into structured skills, seniority, domain, and ATS keywords |
| `resume_analyzer_agent.py` | Extracts candidate resume into a structured schema |
| `resume_matcher_agent.py` | Scores resume vs. job (overall, skills, experience) with matched/missing skills |
| `gap_analysis_agent.py` | Classifies gaps as critical / moderate / minor with actionable bridge strategies |
| `resume_rewrite_agent.py` | Generates ATS-optimized resume variants with reframed bullets |
| `interview_research_agent.py` | Researches company, role, and common interview patterns via web search |

**Orchestration pipeline** (`backend/app/api/orchestrator.py`)

Steps 1 and 2 (JD analysis + resume analysis) run in parallel. Steps 3–5 run sequentially. Step 6 (interview research) fires early and is collected at the end.

```
POST /api/orchestrate  (background=true)
  ├─ [parallel] JD Analyzer + Resume Analyzer
  ├─ [sequential] Resume Matcher
  ├─ [sequential] Gap Analyzer
  ├─ [sequential] Resume Rewriter
  └─ [async] Interview Research
```

Frontend polls `/api/orchestrate/status/{job_id}/{resume_id}` to track progress.

**API routers** (`backend/app/api/`)

| Router | Endpoints |
|---|---|
| `jobs.py` | Ingest, list, and retrieve job descriptions |
| `resumes.py` | Upload and manage candidate resumes |
| `orchestrator.py` | Run and poll the full pipeline |
| `agents.py` | Direct per-agent endpoints for testing |

**Database** — PostgreSQL via SQLAlchemy 2.0

Tables: `job_raw_payloads`, `jobs`, `resumes`, `job_analysis`, `resume_analysis`, `resume_match`, `gap_analysis`, `resume_rewrite`, `interview_research`

**LLM support** (`backend/app/llm/`)

Configurable via the `LLM_PROVIDER` environment variable:

| Provider | Notes |
|---|---|
| `google` | Google Gemini with tool/web-search support (required for interview research) |
| `nvidia` | NVIDIA NIM / Nemotron models |
| `anthropic` | Anthropic Claude |
| `cohere` | Cohere Command |
| `mock` | Deterministic mock for testing |

---

### Frontend — `frontend/`

A vanilla JavaScript SPA built with **Vite**. Uses hash-based routing with 8 screens and shared components.

| Screen | Purpose |
|---|---|
| `screen0_home.js` | Landing page and workflow guide |
| `screen1_job_ingest.js` | Paste or receive extracted job descriptions |
| `screen2_resume_select.js` | Upload and select candidate resumes |
| `screen3_analysis_dashboard.js` | Unified view of all pipeline results |
| `screen4_match_score.js` | Detailed resume-to-job match breakdown |
| `screen5_gap_analysis.js` | Skill gap severity breakdown with recommendations |
| `screen6_resume_variants.js` | View and download tailored resume versions |
| `screen7_interview_prep.js` | Company research and interview tips |
| `screen8_quick_start.js` | One-click pipeline triggered from the extension |

`polling.js` polls the status endpoint every few seconds and updates the UI as results arrive. `state.js` manages in-memory app state with event listeners.

---

### Chrome Extension — `extension/`

A Manifest V3 Chrome extension (v1.3.2) that extracts job details from **LinkedIn** and **Naukri** job pages.

| File | Purpose |
|---|---|
| `content.js` | Injected script that scrapes job DOM elements |
| `ats_extractors.js` | Site-specific parsers for LinkedIn / Naukri selectors |
| `popup.js` | Extension popup UI |
| `background.js` | Service worker for message passing |

**Flow:** Click the extension icon on a job page → click Extract → copy JSON or click "Send to Dashboard" (opens `http://localhost:5173/#/quick-start?payload=...`).

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI 0.136 + Uvicorn |
| AI agent framework | pydantic-ai 1.107 |
| LLM providers | Google Genai, Anthropic, Cohere, Mistral, NVIDIA NIM |
| Database | PostgreSQL + SQLAlchemy 2.0 + psycopg3 |
| Frontend | Vanilla JS (ES6+) + Vite 5.4 |
| Extension | Chrome Manifest V3 |
| Web search | DuckDuckGo (`ddgs`) |
| Observability | Logfire + Sentry SDK |
| MCP | `mcp` + `fastmcp` for tool integration |

---

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL running locally (or connection URL)
- At least one LLM API key

### Backend

```bash
cd backend/app
pip install -r requirements.txt
```

Create a `.env` file:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/jobcopilot
LLM_PROVIDER=google          # google | nvidia | anthropic | cohere | mock
GOOGLE_API_KEY=...           # if using google
ANTHROPIC_API_KEY=...        # if using anthropic
NVIDIA_API_KEY=...           # if using nvidia
```

Run the server:

```bash
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev      # starts at http://localhost:5173
```

### Chrome Extension

1. Open Chrome and navigate to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and select the `extension/` folder

---

## Usage

### Full pipeline (via extension)

1. Navigate to a LinkedIn or Naukri job listing
2. Click the **AI Job Copilot** extension icon
3. Click **Extract Job** → **Send to Dashboard**
4. Upload or select your resume in the frontend
5. Click **Analyze** — the pipeline runs in the background
6. Watch results appear screen by screen as each agent finishes

### Manual pipeline (via frontend)

1. Open `http://localhost:5173`
2. Go to **Job Ingest** → paste the job description
3. Go to **Resume Select** → upload your resume
4. Go to **Dashboard** → click **Run Analysis**
5. Results populate across Screens 4–7

### API (direct)

```bash
# Ingest a job
POST http://localhost:8000/api/jobs/ingest
{ "raw_text": "<job description>" }

# Upload a resume
POST http://localhost:8000/api/resumes
{ "content": "<resume text>", "name": "My Resume" }

# Run the full pipeline
POST http://localhost:8000/api/orchestrate
{ "job_id": "...", "resume_id": "...", "background": true }

# Poll status
GET http://localhost:8000/api/orchestrate/status/{job_id}/{resume_id}
```

---

## Project Structure

```
├── backend/app/
│   ├── agents/          # 6 pydantic-ai agent wrappers
│   ├── api/             # FastAPI routers
│   ├── db/              # SQLAlchemy models & database setup
│   ├── llm/             # LLM client abstractions
│   ├── models/          # SQLAlchemy ORM models
│   ├── prompts/         # Per-agent prompt templates
│   ├── schemas/         # Pydantic I/O schemas
│   ├── services/        # Business logic (called by agents)
│   └── main.py          # FastAPI app entry point
├── frontend/
│   ├── screens/         # 9 screen components
│   ├── components/      # Shared UI components
│   ├── api.js           # Fetch wrapper
│   ├── polling.js       # Status polling logic
│   ├── state.js         # In-memory app state
│   └── app.js           # Router & app bootstrap
├── extension/           # Chrome MV3 extension
└── tests/               # Pytest test suite
```

---

## Testing

```bash
cd tests
pytest test_gap_analysis_service.py
pytest test_resume_analyzer_service.py
pytest test_orchestrator_service.py
pytest test_resume_rewrite_service.py
pytest test_interview_research_service.py
```

Set `LLM_PROVIDER=mock` in your environment to run tests without real API calls.
