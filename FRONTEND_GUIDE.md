# AI Job Copilot — Frontend Integration Guide

This document describes every API endpoint, all data models, the full agent pipeline, and
the recommended UI flow. Use it as the single source of truth when building the frontend.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Base URL & Auth](#2-base-url--auth)
3. [API Endpoints](#3-api-endpoints)
   - 3.1 [Jobs](#31-jobs)
   - 3.2 [Resumes](#32-resumes)
   - 3.3 [Orchestrator (Full Pipeline)](#33-orchestrator-full-pipeline)
4. [Data Models (complete schemas)](#4-data-models)
5. [Agent Pipeline Deep Dive](#5-agent-pipeline-deep-dive)
6. [Recommended UI Flow](#6-recommended-ui-flow)
7. [Status Polling Pattern](#7-status-polling-pattern)
8. [Error Handling Reference](#8-error-handling-reference)
9. [Browser Extension Integration](#9-browser-extension-integration)

---

## 1. Architecture Overview

```
Browser Extension
    │  (scrapes job page → posts raw payload)
    ▼
POST /api/jobs/ingest  ──►  job_raw_payloads table  (job_id returned)
POST /api/resumes      ──►  resumes table           (resume_id returned)
    │
    ▼
POST /api/orchestrate   ──►  5-agent pipeline (async or sync)
    │
    ├── Agent 1: JD Analyzer ─────────────────────────────────────────┐
    │                                                                   │
    ├── Agent 2: Resume Analyzer ───────────────────────────────────── ├─► (concurrent)
    │                                                                   │
    ├── Agent 3: Resume Matcher  (sequential, needs 1 + 2) ◄───────────┘
    │
    ├── Agent 4: Gap Analyzer    (sequential, needs 3)
    │       │
    │       └── Agent 6: Interview Research  (concurrent with 4)
    │
    └── Agent 5: Resume Rewriter (sequential, needs 4)
```

All results are stored in the database and returned inline when `background=false`.
When `background=true` (the default) the pipeline runs in the background and the
frontend must poll or rely on a webhook/websocket (not yet implemented).

---

## 2. Base URL & Auth

| Key | Value |
|-----|-------|
| Base URL | `http://localhost:8000` (dev) |
| Auth | None implemented — add your own token middleware before going public |
| Content-Type | `application/json` for most endpoints |

---

## 3. API Endpoints

### 3.1 Jobs

#### `POST /api/jobs/ingest`

Ingest a raw job description payload (typically sent by the browser extension).

**Request body**

```jsonc
{
  "source": "linkedin",          // string — ATS name / job board
  "payload": {                   // free-form object, whatever the extension scraped
    "title": "Senior QA Engineer",
    "company": "Acme Corp",
    "location": "Remote",
    "description": "We are looking for...",
    "requirements": "5+ years ...",
    "url": "https://linkedin.com/jobs/view/..."
  }
}
```

**Response `200`**

```jsonc
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "stored"
}
```

> **Store `job_id`** — it is used in every subsequent call.

---

#### `POST /api/jobs/{job_id}/analyze`

Run the JD Analyzer agent on an ingested job.

**Query params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `background` | bool | `true` | `true` → returns immediately; `false` → waits and returns `JobAnalysisResult` |
| `stream` | bool | `false` | SSE streaming (only when `background=false` and NVIDIA NIM provider) |

**Background response (`background=true`)**

```jsonc
{
  "job_id": "550e8400...",
  "status": "analysis_queued"
}
```

**Sync response (`background=false`)**

Returns a `JobAnalysisResult` object directly — see [§4.1](#41-jobanalysisresult).

**Streaming (`stream=true`, `background=false`)**

Returns `Content-Type: text/event-stream`. Each SSE event is a JSON chunk.
Final event is `data: [DONE]`.

---

### 3.2 Resumes

#### `POST /api/resumes`

Store a resume. Accepts three content types:

**Option A — JSON**

```jsonc
{
  "name": "My Master Resume",
  "content": "# John Doe\n\n## Experience\n...",   // Markdown string
  "is_master": true
}
```

**Option B — multipart/form-data**

| Field | Type | Notes |
|-------|------|-------|
| `name` | string | |
| `is_master` | bool | |
| `file` | File | `.md` or `.txt` resume |
| `content` | string | alternative to `file` |

**Option C — raw text/plain body**

Post the Markdown body directly. Pass `?name=<resume-name>` as a query param.

**Response `200`**

```jsonc
{
  "resume_id": "123e4567-e89b-12d3-a456-426614174000",
  "status": "stored"
}
```

> **Store `resume_id`** — it is used in every subsequent call.

---

#### `POST /api/resumes/match`

Run only the Resume Matcher agent (skips JD Analyzer + Resume Analyzer — requires
those results to already exist in the DB).

**Request body**

```jsonc
{
  "resume_id": "123e4567...",
  "job_analysis_id": "abcd1234..."
}
```

**Response `200`** — `ResumeMatchResult` object — see [§4.3](#43-resumematchresult).

---

### 3.3 Orchestrator (Full Pipeline)

#### `POST /api/orchestrate`

Runs the full 5-agent pipeline for a job + resume pair.

**Request body**

```jsonc
{
  "job_id": "550e8400...",
  "resume_id": "123e4567...",
  "company_name": "Acme Corp",     // optional — used by Interview Research agent
  "role_title": "Senior QA Engineer", // optional — used by Interview Research agent
  "skip_job_analysis": false,      // true if job_analysis already exists in DB
  "skip_resume_analysis": false,   // true if resume_analysis already exists in DB
  "skip_interview_research": false // true to skip the interview research agent
}
```

**Query params**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `background` | bool | `true` | `true` → returns `status=queued` immediately |

**Response — background mode (`background=true`)**

```jsonc
{
  "job_id": "550e8400...",
  "resume_id": "123e4567...",
  "status": "queued"
}
```

**Response — sync mode (`background=false`)**

```jsonc
{
  "job_id": "550e8400...",
  "resume_id": "123e4567...",
  "status": "complete",             // or "failed"
  "error": null,                    // error key if failed

  // Record IDs for later retrieval
  "job_analysis_id": "aaa...",
  "resume_analysis_id": "bbb...",
  "resume_match_id": "ccc...",
  "gap_analysis_id": "ddd...",
  "resume_rewrite_id": "eee...",
  "interview_research_id": "fff...",

  // Inline results (objects)
  "job_analysis": { /* JobAnalysisResult */ },
  "resume_match": { /* ResumeMatchResult */ },
  "gap_analysis": { /* GapAnalysisResult */ },
  "resume_rewrite": { /* ResumeRewriteResult */ },
  "interview_research": { /* InterviewResearchResult */ }
}
```

---

## 4. Data Models

### 4.1 `JobAnalysisResult`

Output of the JD Analyzer agent.

```typescript
interface JobAnalysisResult {
  required_skills: string[];       // must-have skills explicitly listed in JD
  preferred_skills: string[];      // nice-to-have skills
  programming_languages: string[];
  tools: string[];
  frameworks: string[];
  experience_required: string;     // e.g. "3-6 years"
  seniority_level: string;         // "junior" | "mid" | "senior" | "lead" | "staff"
  domain: string;                  // e.g. "QA Automation", "Backend Python"
  ats_keywords: string[];          // exact phrases that ATS filters look for
  responsibilities: string[];      // action-verb-led bullets
  summary: string;                 // 2-3 sentence neutral role summary
}
```

---

### 4.2 `ResumeAnalysisResult`

Output of the Resume Analyzer agent.

```typescript
interface ResumeAnalysisResult {
  skills: string[];
  experience_years: string;        // e.g. "5 years"
  domains: string[];               // engineering domains the candidate has worked in
  certifications: string[];
  summary: string;
}
```

---

### 4.3 `ResumeMatchResult`

Output of the Resume Matcher agent.

```typescript
interface ResumeMatchResult {
  overall_score: number;               // 0–100
  skills_match_score: number;          // 0–100
  experience_match_score: number;      // 0–100

  matched_required_skills: string[];
  missing_required_skills: string[];
  matched_preferred_skills: string[];
  missing_preferred_skills: string[];

  experience_fit: "under_qualified" | "match" | "over_qualified";

  ats_keyword_coverage: string[];   // ATS keywords present in resume
  ats_keyword_gaps: string[];       // ATS keywords missing from resume

  strengths: string[];              // max 4, specific to this job
  improvement_suggestions: string[]; // max 5, specific and actionable

  match_summary: string;           // 2-3 sentences, honest assessment
}
```

**Score weighting** (from agent instructions):

| Dimension | Weight |
|-----------|--------|
| Skills    | 50 %   |
| Experience| 30 %   |
| Domain    | 20 %   |

> A score ≥ 90 should be genuinely rare. Present scores conservatively in the UI.

---

### 4.4 `GapAnalysisResult`

Output of the Gap Analysis agent.

```typescript
interface GapItem {
  skill: string;
  severity: "critical" | "moderate" | "minor";
  reason: string;           // why this gap matters for THIS job
  bridge_suggestion: string; // how to address it in resume / cover letter
}

interface GapAnalysisResult {
  critical_gaps: GapItem[];   // missing required skills core to the role
  moderate_gaps: GapItem[];   // missing required skills, but survivable
  minor_gaps: GapItem[];      // missing preferred skills

  quick_wins: string[];       // buried resume strengths to surface

  resume_strategy: string;    // 1-paragraph instruction for the rewrite
  cover_letter_angle: string; // 1-2 sentence narrative angle for cover letter

  honesty_flag: boolean;      // true when gaps are likely insurmountable
  honesty_note: string;       // kind, direct note to show the user if honesty_flag=true
}
```

> **UI tip:** If `honesty_flag` is `true`, display `honesty_note` as a prominent
> warning banner before showing the resume variants.

---

### 4.5 `ResumeRewriteResult`

Output of the Resume Rewrite agent.

```typescript
interface ResumeVariant {
  variant: "A_ats" | "B_impact" | "C_technical";
  content_md: string;         // complete resume in Markdown
  changes_summary: string[];  // 4-6 key changes vs. original
}

interface ResumeRewriteResult {
  variants: ResumeVariant[];   // always 3 variants
  shared_changes: string[];    // changes applied across all variants
}
```

**Variant descriptions**

| Variant | Code | Goal |
|---------|------|------|
| ATS-Optimised | `A_ats` | Pass automated keyword screening. Keywords woven naturally into bullets. Flat skills section. |
| Impact-Focused | `B_impact` | Impress a human hiring manager. Business impact leads every bullet. Compelling summary. |
| Technical-Depth | `C_technical` | Impress a technical interviewer. Expands tool/architecture details. Shows technical reasoning. |

---

### 4.6 `InterviewResearchResult`

Output of the Interview Research agent (runs in parallel with Gap Analysis).

```typescript
interface InterviewQuestion {
  question: string;
  category: string;            // e.g. "behavioural", "technical", "system design"
  why_asked: string;
  strong_answer_tips: string[];
}

interface InterviewResearchResult {
  role_specific_questions: InterviewQuestion[];
  company_snapshot: string;    // paragraph about the company
  tech_stack_intel: string[];  // known tools/technologies used internally
  hiring_signals: string[];    // publicly visible signals about this hiring round
  culture_notes: string;
  red_flags: string[];         // potential concerns worth probing in interview
  prep_checklist: string[];    // actionable prep steps for the candidate
}
```

---

### 4.7 `OrchestratorRequest` / `OrchestratorResponse`

See §3.3 above for the full JSON shapes.

---

## 5. Agent Pipeline Deep Dive

### Execution order

```
Step 1 ──► JD Analyzer            (async, concurrent with step 2)
Step 2 ──► Resume Analyzer        (async, concurrent with step 1)

         ─── await both ───

Step 3 ──► Resume Matcher         (sequential: needs steps 1 + 2)

         ─── await ───

Step 4 ──► Gap Analyzer           (sequential, concurrent with step 6)
Step 6 ──► Interview Research     (async, concurrent with step 4)

         ─── await both ───

Step 5 ──► Resume Rewriter        (sequential: needs step 4)
```

### Stage skip flags

Use these in `OrchestratorRequest` to avoid re-running expensive LLM calls when
results already exist:

| Flag | Skip condition |
|------|---------------|
| `skip_job_analysis` | `job_analysis` row already exists for `job_id` |
| `skip_resume_analysis` | `resume_analysis` row already exists for `resume_id` |
| `skip_interview_research` | Don't need interview prep (saves ~3-5 LLM calls) |

### Possible `status` values in `OrchestratorResponse`

| Status | Meaning |
|--------|---------|
| `queued` | Background run accepted, pipeline not yet started |
| `running` | Pipeline in progress (only visible in sync mode internal state) |
| `complete` | All agents finished successfully |
| `failed` | One or more agents failed — see `error` field |

### Possible `error` values

| Error key | Failed stage |
|-----------|-------------|
| `job_or_resume_analysis_failed` | Step 1 or 2 |
| `resume_match_failed` | Step 3 |
| `gap_or_interview_failed` | Step 4 or 6 |
| `resume_rewrite_failed` | Step 5 |

---

## 6. Recommended UI Flow

### Screen 1 — Job Ingestion

**Purpose:** Get a job description into the system.

**Two paths:**
1. **Browser Extension** — User clicks the extension on a job board page. It
   auto-scrapes and sends `POST /api/jobs/ingest`. The `job_id` is returned and
   stored in `chrome.storage`.
2. **Manual paste** — Form with a large textarea. On submit, wrap the paste as:
   ```json
   { "source": "manual", "payload": { "description": "<pasted text>" } }
   ```

**UI elements:**
- Job title, company name inputs (used later for Interview Research)
- "Ingest" button → show `job_id` confirmation toast
- Job history list (if you maintain local state)

---

### Screen 2 — Resume Selection / Upload

**Purpose:** Select or upload the master resume.

**UI elements:**
- Upload `.md` or `.txt` file (use `multipart/form-data`)
- Paste raw Markdown in a text area
- "Set as master" toggle
- Saved resumes list with `resume_id`

---

### Screen 3 — Run Analysis (Dashboard Trigger)

**Purpose:** Fire the orchestrator pipeline.

**UI elements:**
- Job selector (shows ingested jobs with title + company)
- Resume selector (shows stored resumes)
- Optional: Company Name + Role Title inputs (improve Interview Research quality)
- "Analyse" button → `POST /api/orchestrate` with `background=true`
- Progress indicator (see §7 for polling)

**Recommended:** Pass `background=false` if you want results immediately without
polling complexity (suitable for fast LLM providers). Expect 15–60 s response time.

---

### Screen 4 — Match Score Overview

**Purpose:** Show the high-level match between resume and job.

Display `ResumeMatchResult`:

```
┌─────────────────────────────────────────────────────┐
│  Overall Match: [████████░░] 78 / 100               │
│  Skills:        [█████████░] 85 / 100               │
│  Experience:    [███████░░░] 70 / 100               │
│                                                     │
│  Experience Fit: ✓ Match                            │
│                                                     │
│  Strengths                   Improvement Areas      │
│  • Python automation         • Add Playwright        │
│  • CI/CD integration         • Jenkins mention       │
│                                                     │
│  [match_summary paragraph]                          │
└─────────────────────────────────────────────────────┘
```

**ATS panel** (collapsible):

| Covered | Gaps |
|---------|------|
| `pytest automation` | `playwright cross-browser` |
| `CI/CD pipelines` | `performance testing` |

---

### Screen 5 — Gap Analysis

**Purpose:** Show strategic gaps and how to address them.

**⚠ Honesty Banner** — If `honesty_flag === true`, show:
```
⚠ Heads up: This role requires skills that are not yet in your resume.
[honesty_note text]
Applying is still an option, but set realistic expectations.
```

**Gap cards** — Group by severity with colour coding:

| Severity | Colour |
|----------|--------|
| `critical` | Red |
| `moderate` | Amber |
| `minor` | Blue |

Each card: skill name, reason, bridge suggestion.

**Quick Wins** — highlight these with a ✓ icon — already in the resume, just
need surfacing.

**Strategy** — show `resume_strategy` and `cover_letter_angle` as advisory text.

---

### Screen 6 — Resume Variants

**Purpose:** Let the user choose, preview, and download a rewritten resume.

**Tab layout:**

```
[A: ATS-Optimised]  [B: Impact-Focused]  [C: Technical-Depth]
```

Each tab:
- Markdown preview (render with a Markdown renderer)
- "Changes made" collapsible list (from `changes_summary`)
- "Shared changes" section at bottom
- Download as `.md` button
- Copy to clipboard button

---

### Screen 7 — Interview Prep

**Purpose:** Help the candidate prepare for the interview.

**Sections:**

1. **Company Snapshot** — `company_snapshot` paragraph
2. **Tech Stack Intel** — tag cloud or bullet list from `tech_stack_intel`
3. **Culture Notes** — `culture_notes` paragraph
4. **Hiring Signals** — bullet list from `hiring_signals`
5. **Red Flags** — `red_flags` (collapsible, shown with ⚠)
6. **Prep Checklist** — `prep_checklist` as checkboxes
7. **Interview Questions** — accordion, grouped by `category`:
   - Question text
   - Why asked
   - Answer tips (bullet list)

---

## 7. Status Polling Pattern

When `background=true`, the pipeline runs asynchronously. The backend does **not**
yet expose a GET endpoint for polling — **implement one of the following strategies**:

### Option A — Short Polling (simple, recommended for v1)

```typescript
async function pollUntilDone(jobId: string, resumeId: string): Promise<OrchestratorResponse> {
  // POST with background=false immediately (simplest approach for small payloads)
  // OR implement a GET /api/orchestrate/status/{job_id}/{resume_id} endpoint
}
```

**Recommended immediate workaround:** Call `POST /api/orchestrate` with
`background=false`. The request blocks until complete (15–60 s). Show a
progress spinner with stage labels that animate through the pipeline steps.

### Option B — Background + Polling (needs a new status endpoint)

Request a new endpoint from the backend: `GET /api/orchestrate/status/{job_id}/{resume_id}`
that reads the DB and returns the current `OrchestratorResponse`.

### Option C — WebSocket / SSE (future)

Not yet implemented in the backend.

---

## 8. Error Handling Reference

| HTTP Status | Scenario | UI action |
|-------------|----------|-----------|
| `400` | `stream=true` with `background=true` | Disable streaming option in UI |
| `404` | `job_id` or `resume_id` not found | Show "Job/Resume not found" error |
| `422` | Missing `name` or `content` in resume upload | Inline form validation |
| `500` | LLM call failed | Show retry button with error message |

**Orchestrator error keys** (in `error` field):

| Error key | User-facing message |
|-----------|---------------------|
| `job_or_resume_analysis_failed` | "Could not analyse the job or resume. Please try again." |
| `resume_match_failed` | "Matching failed. Check that both job and resume are valid." |
| `gap_or_interview_failed` | "Gap analysis failed. Match results are still available." |
| `resume_rewrite_failed` | "Resume rewrite failed. Gap analysis results are still available." |

---

## 9. Browser Extension Integration

The Chrome extension (`/extension`) scrapes job pages and sends them to the backend.

### Supported ATS platforms

| ATS | Detection |
|-----|-----------|
| Greenhouse | `greenhouse.io` domain |
| Lever | `lever.co` domain |
| Workday | `myworkdayjobs.com` domain |
| Taleo | `taleo.net` domain |
| Oracle HCM | `oraclecloud.com` domain |
| iCIMS | `icims.com` domain |
| Ashby | `ashbyhq.com` domain |
| SmartRecruiters | `smartrecruiters.com` domain |
| SAP SuccessFactors | `successfactors.com` domain |
| LinkedIn, Indeed, and generic fallback also supported |

### Extracted payload shape

```typescript
interface ExtractedJob {
  ats: string;              // detected ATS name
  title: string;
  company: string;
  location: string;
  description: string;      // full JD text
  requirements: string;
  responsibilities: string;
  url: string;
  extracted_at: string;     // ISO timestamp
}
```

### How to send from extension to frontend

The extension popup writes the extracted JSON to the output textarea. If you build
a **companion web app**, you can:

1. Have the extension post directly to `POST /api/jobs/ingest` with the scraped payload.
2. Return the `job_id` and open the web app URL with `?job_id=<id>` so the user
   lands on Screen 3 with the job pre-selected.

### Extension message flow

```
User clicks "Extract" in popup
  → popup.js injects ats_extractors.js + content.js into the tab
  → sends EXTRACT_JOB message to content script
  → content script uses ats_extractors to scrape
  → returns { ok: true, data: ExtractedJob }
  → popup.js displays JSON in output textarea
  → User copies JSON or (future) extension auto-posts to backend
```

---

## Appendix: Full TypeScript type reference

```typescript
// ── Job ──────────────────────────────────────────────────────────────────────
interface JobIngestRequest { source: string; payload: Record<string, unknown> }
interface JobIngestResponse { job_id: string; status: string }

interface JobAnalysisResult {
  required_skills: string[]; preferred_skills: string[];
  programming_languages: string[]; tools: string[]; frameworks: string[];
  experience_required: string; seniority_level: string; domain: string;
  ats_keywords: string[]; responsibilities: string[]; summary: string;
}

// ── Resume ───────────────────────────────────────────────────────────────────
interface ResumeCreateRequest { name: string; content: string; is_master?: boolean }
interface ResumeCreateResponse { resume_id: string; status: string }

interface ResumeAnalysisResult {
  skills: string[]; experience_years: string; domains: string[];
  certifications: string[]; summary: string;
}

// ── Match ────────────────────────────────────────────────────────────────────
interface ResumeMatchRequest { resume_id: string; job_analysis_id: string }
interface ResumeMatchResult {
  overall_score: number; skills_match_score: number; experience_match_score: number;
  matched_required_skills: string[]; missing_required_skills: string[];
  matched_preferred_skills: string[]; missing_preferred_skills: string[];
  experience_fit: "under_qualified" | "match" | "over_qualified";
  ats_keyword_coverage: string[]; ats_keyword_gaps: string[];
  strengths: string[]; improvement_suggestions: string[]; match_summary: string;
}

// ── Gap Analysis ─────────────────────────────────────────────────────────────
interface GapItem {
  skill: string; severity: "critical" | "moderate" | "minor";
  reason: string; bridge_suggestion: string;
}
interface GapAnalysisResult {
  critical_gaps: GapItem[]; moderate_gaps: GapItem[]; minor_gaps: GapItem[];
  quick_wins: string[]; resume_strategy: string; cover_letter_angle: string;
  honesty_flag: boolean; honesty_note: string;
}

// ── Resume Rewrite ────────────────────────────────────────────────────────────
interface ResumeVariant {
  variant: "A_ats" | "B_impact" | "C_technical";
  content_md: string; changes_summary: string[];
}
interface ResumeRewriteResult { variants: ResumeVariant[]; shared_changes: string[] }

// ── Interview Research ────────────────────────────────────────────────────────
interface InterviewQuestion {
  question: string; category: string; why_asked: string;
  strong_answer_tips: string[];
}
interface InterviewResearchResult {
  role_specific_questions: InterviewQuestion[]; company_snapshot: string;
  tech_stack_intel: string[]; hiring_signals: string[]; culture_notes: string;
  red_flags: string[]; prep_checklist: string[];
}

// ── Orchestrator ─────────────────────────────────────────────────────────────
interface OrchestratorRequest {
  job_id: string; resume_id: string;
  company_name?: string; role_title?: string;
  skip_job_analysis?: boolean; skip_resume_analysis?: boolean;
  skip_interview_research?: boolean;
}
interface OrchestratorResponse {
  job_id: string; resume_id: string;
  status: "queued" | "running" | "complete" | "failed";
  error?: string;
  job_analysis_id?: string; resume_analysis_id?: string; resume_match_id?: string;
  gap_analysis_id?: string; resume_rewrite_id?: string; interview_research_id?: string;
  job_analysis?: JobAnalysisResult;
  resume_match?: ResumeMatchResult;
  gap_analysis?: GapAnalysisResult;
  resume_rewrite?: ResumeRewriteResult;
  interview_research?: InterviewResearchResult;
}
```
