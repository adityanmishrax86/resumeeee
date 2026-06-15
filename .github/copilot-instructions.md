# Copilot Instructions — Resume Backend (`app/`)

> This file is auto-derived from the **graphify knowledge graph** (`graphify-out/graph.json`).
> Always consult it for the ground-truth structure before suggesting changes, imports, or new files.

---

## 1. Project Overview

This is a **FastAPI backend** for an AI-powered resume analysis and job-matching system.
It uses a layered architecture: **API routes → Services → Agents → LLM Clients → DB Models**.

The project is also guided by `plan.md`, which defines five planned agents and several future DB tables not yet implemented.

---

## 2. Folder & File Structure

```
app/
├── main.py                         # FastAPI app entry point
│
├── api/
│   ├── jobs.py                     # POST /jobs/ingest, POST /jobs/analyze
│   └── resumes.py                  # POST /resumes/, POST /resumes/match
│
├── agents/
│   ├── agent_adapter.py            # Abstract base: AgentAdapter(ABC) — wraps LLM client into async agent
│   ├── job_analyzer_agent.py       # JobAnalyzerAgent — delegates to JobAnalyzerService
│   └── resume_matcher_agent.py     # ResumeMatcherAgent — delegates to ResumeMatcherService
│
├── services/
│   ├── job_analyzer_service.py     # JobAnalyzerService — prompt prep, LLM call, JSON extraction
│   ├── job_service.py              # JobService — ingestion logic
│   └── resume_service.py          # ResumeService — create/match resume, prompt prep
│
├── llm/
│   ├── clients.py                  # BaseLLMClient (ABC), MockLLMClient, NvidiaNIMClient
│   ├── google_client.py            # GoogleClient (extends BaseLLMClient via pydantic_ai.Agent)
│   └── nim_schema.py              # Pydantic schemas: NimMessage, NimChatRequest
│
├── models/
│   ├── models.py                   # SQLAlchemy ORM: Job, JobSkill, JobRawPayload, Resume
│   └── analysis_models.py         # SQLAlchemy ORM: JobAnalysis, ResumeMatch
│
├── schemas/
│   ├── job_schema.py               # Pydantic: JobIngestRequest, JobIngestResponse
│   ├── job_analysis_schema.py      # Pydantic: JobAnalysisResult
│   └── resume_schema.py           # Pydantic: ResumeCreateRequest/Response, ResumeMatchRequest/Result
│
├── db/
│   └── database.py                # SQLAlchemy engine, Base (DeclarativeBase), get_db() dependency
│
└── graphify-out/
    └── graph.json                  # Graphify knowledge graph (source of truth for this file)
```

---

## 3. Architecture & Data Flow

```
HTTP Request
    │
    ▼
api/jobs.py  ──────────────────────────────────► api/resumes.py
    │                                                   │
    ▼                                                   ▼
services/job_service.py          services/resume_service.py
services/job_analyzer_service.py
    │                                                   │
    ▼                                                   ▼
agents/job_analyzer_agent.py       agents/resume_matcher_agent.py
    │                                                   │
    └──────────────┬────────────────────────────────────┘
                   ▼
         llm/clients.py  (BaseLLMClient)
              │        │         │
       MockLLMClient  NvidiaNIMClient  llm/google_client.py (GoogleClient)
                   │
                   ▼
         models/ + db/database.py
```

### Key relationships (from graph)
- `AgentAdapter` is abstract (`inherits ABC`); all agents extend it.
- `BaseLLMClient` is abstract; `MockLLMClient`, `NvidiaNIMClient`, `GoogleClient` implement `.generate()`.
- `GoogleClient` uses `pydantic_ai.Agent` and requires `GOOGLE_API_KEY` env var.
- `NvidiaNIMClient` requires `NVIDIA_API_KEY` env var.
- `JobAnalyzerService` calls `_extract_json()` helper to parse raw LLM output.
- `ResumeService` parses LLM responses into `ResumeMatchResult`.
- `get_db()` in `db/database.py` is the FastAPI dependency for SQLAlchemy sessions.

---

## 4. API Routes

| Method | Path             | File             | Handler          | Description                                 |
|--------|------------------|------------------|------------------|---------------------------------------------|
| POST   | /jobs/ingest     | api/jobs.py      | `ingest_job()`   | Ingest raw job description, store payload   |
| POST   | /jobs/analyze    | api/jobs.py      | `analyze_job()`  | Analyze job via LLM, store structured result|
| POST   | /resumes/        | api/resumes.py   | `create_resume()`| Accept JSON / multipart / raw markdown      |
| POST   | /resumes/match   | api/resumes.py   | `match_resume()` | Match resume against a job via LLM          |

- `analyze_job()` uses `BackgroundTasks` — analysis is async by default.
- `create_resume()` supports JSON, multipart/form-data, and raw markdown (`Request` body).

---

## 5. DB Models (SQLAlchemy ORM)

### `models/models.py`
| Class         | Description                                  |
|---------------|----------------------------------------------|
| `Job`         | Core job entity                              |
| `JobSkill`    | Skills extracted from a job (FK → Job)       |
| `JobRawPayload` | Raw ingested JD text/JSON (FK → Job)       |
| `Resume`      | Uploaded resume entity                       |

### `models/analysis_models.py`
| Class         | Description                                  |
|---------------|----------------------------------------------|
| `JobAnalysis` | LLM-structured analysis of a job            |
| `ResumeMatch` | LLM match result between resume and job     |

- All models use `Base` from `db/database.py` (`DeclarativeBase`).
- Always import `Base` from `db.database`, not redefined locally.

---

## 6. Pydantic Schemas

| Schema                 | File                         | Used In                      |
|------------------------|------------------------------|------------------------------|
| `JobIngestRequest`     | schemas/job_schema.py        | api/jobs.py                  |
| `JobIngestResponse`    | schemas/job_schema.py        | api/jobs.py                  |
| `JobAnalysisResult`    | schemas/job_analysis_schema.py | services/job_analyzer_service.py |
| `ResumeCreateRequest`  | schemas/resume_schema.py     | api/resumes.py               |
| `ResumeCreateResponse` | schemas/resume_schema.py     | api/resumes.py               |
| `ResumeMatchRequest`   | schemas/resume_schema.py     | api/resumes.py               |
| `ResumeMatchResult`    | schemas/resume_schema.py     | agents/resume_matcher_agent.py, services/resume_service.py |

---

## 7. LLM Client Interface

Every LLM client must implement `BaseLLMClient` from `llm/clients.py`:

```python
# llm/clients.py
class BaseLLMClient(ABC):
    async def generate(self, system_prompt: str, user_prompt: str) -> str: ...
```

- `MockLLMClient` — deterministic JSON for tests; no API key needed.
- `NvidiaNIMClient` — calls NVIDIA NIM Chat Completions API; uses `NimMessage` / `NimChatRequest` from `llm/nim_schema.py`.
- `GoogleClient` — uses `pydantic_ai.Agent`; requires `GOOGLE_API_KEY`; calls `._init_agent()` in `__init__`.

**When adding a new LLM provider**, subclass `BaseLLMClient`, implement `.generate()`, and add it to the client factory (if one exists) or wire it directly in the service.

---

## 8. Planned Agents & Tables (from `plan.md`)

These are **not yet implemented** but are part of the roadmap. Do not confuse with existing files.

### Planned Agents
| Agent                    | Result Type              |
|--------------------------|--------------------------|
| `JD Analyzer Agent`      | `JobAnalysisResult`      |
| `Resume Matcher Agent`   | `ResumeMatchResult`      |
| `Gap Analysis Agent`     | `GapAnalysisResult`      |
| `Resume Rewrite Agent`   | `ResumeRewriteResult`    |
| `Interview Research Agent` | `InterviewResearchResult` |

### Planned DB Tables
- `gap_analyses` — stores gap analysis between resume and job
- `generated_content` — stores rewritten resumes or interview content
- `application_runs` — tracks full pipeline runs per application (`ApplicationPackage`)

When implementing these, follow the existing `agents/` + `services/` pattern and add Pydantic schemas in `schemas/`.

---

## 9. Coding Conventions

- **Agents** live in `agents/`, are async, and wrap a `Service`. Constructor signature: `__init__(self, llm_client: BaseLLMClient, db: Session)`.
- **Services** live in `services/`, contain business logic, prompt preparation, and DB writes.
- **Schemas** (Pydantic) live in `schemas/`. ORM models live in `models/`. Never mix them.
- **DB session** is always injected via `Depends(get_db)` from `db.database`.
- **LLM clients** are injected, not instantiated inside services/agents.
- Use `BackgroundTasks` for long-running LLM calls (see `api/jobs.py`).
- JSON extraction from LLM output goes through `_extract_json()` in `job_analyzer_service.py` — reuse this pattern.
- Environment variables: `GOOGLE_API_KEY` (GoogleClient), `NVIDIA_API_KEY` (NvidiaNIMClient).

---

## 10. What NOT to Do

- Do not instantiate `BaseLLMClient` directly — it is abstract.
- Do not define `Base` in model files — always import from `db.database`.
- Do not add business logic to API route handlers (`api/`) — delegate to services.
- Do not create new schemas in `models/` — keep Pydantic schemas in `schemas/`.
- Do not implement planned agents from `plan.md` as if they already exist — check `agents/` first.