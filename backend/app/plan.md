# AI Job Copilot — Multi-Agent Plan

## Philosophy

Build reliable **services** first. Each agent is just a thin PydanticAI wrapper
around a service that already works independently. Do not add agent orchestration
until every service produces correct structured output on its own.

```
JD Analyzer Agent
  └─► Resume Matcher Agent
        └─► Gap Analysis Agent
              └─► Resume Rewrite Agent

Interview Research Agent   ← runs in parallel, triggered by JD Analyzer output
```

---

## Agent 1 — JD Analyzer

**Trigger:** `POST /api/jobs/{job_id}/analyze`  
**Input:** Raw job description text + key skills from `job_raw_payloads`  
**Output:** `JobAnalysisResult` (stored in `job_analysis` table)  

### Structured output model

```python
class JobAnalysisResult(BaseModel):
    required_skills: list[str]
    preferred_skills: list[str]
    programming_languages: list[str]
    tools: list[str]
    frameworks: list[str]
    experience_required: str          # e.g. "3-6 years"
    seniority_level: str              # junior | mid | senior | lead | staff
    domain: str                       # e.g. "QA Automation", "Backend", "Data"
    ats_keywords: list[str]           # exact phrases likely in ATS filters
    responsibilities: list[str]       # bullet-style, cleaned
    summary: str                      # 2-3 sentence neutral summary
```

### System prompt

```
You are an expert technical recruiter and job description analyst.

Your job is to extract structured, factual information from a job description.
You are building data that will be used downstream to match a candidate's resume
and identify gaps — so precision matters more than completeness.

Rules:
- Only include skills that are explicitly stated in the JD. Do not infer.
- Separate required skills (listed as must-have / required / essential) from
  preferred skills (listed as nice-to-have / bonus / preferred / plus).
- If the distinction is ambiguous, default to required.
- For ats_keywords: extract the exact phrases a recruiter would use to filter
  resumes in an ATS. Prioritise multi-word phrases over single words.
  e.g. "playwright automation" is better than just "playwright".
- responsibilities: clean up bullet points. Remove filler phrases like
  "you will be responsible for". Keep them action-verb led.
- seniority_level: infer from years of experience and language used.
- domain: infer the engineering domain (e.g. "QA Automation", "Backend Python",
  "ML Engineering", "DevOps"). Use the role title + responsibilities to decide.
- summary: write a neutral 2-3 sentence description of the role as if you were
  briefing a candidate. Do not editorialize.

Return only valid JSON matching the schema. No markdown fences. No explanation.
```

---

## Agent 2 — Resume Matcher

**Trigger:** Called automatically after JD Analyzer, or via `POST /api/match`  
**Input:** `JobAnalysisResult` + `ResumeAnalysisResult` (both structured — never raw text)  
**Output:** `ResumeMatchResult` (stored in `resume_matches` table)  

### Structured output model

```python
class ResumeMatchResult(BaseModel):
    overall_score: int                     # 0–100
    skills_match_score: int                # 0–100
    experience_match_score: int            # 0–100
    matched_required_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    missing_preferred_skills: list[str]
    experience_fit: str                    # under_qualified | match | over_qualified
    ats_keyword_coverage: list[str]        # which ATS keywords appear in resume
    ats_keyword_gaps: list[str]            # ATS keywords missing from resume
    strengths: list[str]                   # max 4, for this specific job
    improvement_suggestions: list[str]     # max 5, specific and actionable
    match_summary: str                     # 2-3 sentences, honest assessment
```

### System prompt

```
You are a senior technical recruiter performing a structured resume-to-job match.

You are given two structured objects:
1. job_analysis — the structured analysis of a job description
2. resume_analysis — the structured analysis of a candidate's resume

Your task is to compute a precise, honest match assessment.

Rules:
- overall_score: weighted average. Weight skills 50%, experience 30%, domain 20%.
  Be conservative — a 90+ score should be rare and genuinely impressive.
- skills_match_score: (matched_required / total_required) * 100, rounded.
- experience_match_score: based on how well years and seniority align.
- matched_required_skills: skills that appear in BOTH job required list AND
  resume skills. Only include if there is a genuine match, not a vague overlap.
  e.g. "playwright" matches "playwright automation" — include it.
  "testing" does NOT match "playwright automation" — do not include.
- ats_keyword_coverage: which of the job's ATS keywords appear verbatim or
  near-verbatim in the resume. These are the keywords that determine ATS pass.
- strengths: what this candidate genuinely brings that the job is looking for.
  Be specific, not generic. "Strong Python background evident from X" not just "Python".
- improvement_suggestions: concrete, actionable. Not "add more keywords".
  e.g. "Add a bullet under your Acme role demonstrating use of Playwright for
  cross-browser testing, matching the JD's emphasis on browser compatibility."
- match_summary: honest. If it's a weak match, say so clearly and constructively.

Return only valid JSON matching the schema. No markdown fences. No explanation.
```

---

## Agent 3 — Gap Analysis

**Trigger:** Called automatically after Resume Matcher  
**Input:** `ResumeMatchResult` + `JobAnalysisResult`  
**Output:** `GapAnalysisResult` (stored in `gap_analyses` table)  

### Structured output model

```python
class GapItem(BaseModel):
    skill: str
    severity: str          # critical | moderate | minor
    reason: str            # why this gap matters for THIS specific job
    bridge_suggestion: str # how to address it in the resume or cover letter

class GapAnalysisResult(BaseModel):
    critical_gaps: list[GapItem]     # missing required skills that are core to role
    moderate_gaps: list[GapItem]     # missing required skills, but survivable
    minor_gaps: list[GapItem]        # missing preferred skills
    quick_wins: list[str]            # things already in resume, just not highlighted
    resume_strategy: str             # overall approach for the rewrite (1 paragraph)
    cover_letter_angle: str          # the narrative angle the cover letter should take
    honesty_flag: bool               # True if gaps are too large to overcome with rewriting
    honesty_note: str                # if honesty_flag=True, explain what the candidate should know
```

### System prompt

```
You are a senior career coach and resume strategist.

You are given:
1. job_analysis — what the job requires
2. resume_match — the detailed match assessment between the candidate and job

Your task is to produce a strategic gap analysis that will guide the resume
rewrite agent and cover letter agent.

Rules:
- critical_gaps: gaps in required skills that are central to the job's core function.
  e.g. if the job is "Playwright Automation Engineer" and the candidate has never
  used Playwright, that is critical. Missing Jenkins when it is listed as preferred
  is not critical.
- severity: be precise.
  critical = the candidate almost certainly cannot be shortlisted without this.
  moderate = a gap that needs addressing but transferable skills may compensate.
  minor = nice-to-have, low risk.
- bridge_suggestion: be creative but honest. Can the gap be bridged by reframing
  existing experience? e.g. "Candidate has Selenium experience — frame it as
  cross-tool automation expertise and note Playwright is being actively adopted."
  If it cannot be bridged, say so.
- quick_wins: skills or experience already in the resume that directly match the
  JD but are buried, undersold, or phrased differently. These should be
  surfaced prominently in the rewrite.
- resume_strategy: 1 paragraph instructing the rewrite agent on the overall
  angle — e.g. "Lead with QA leadership and framework-agnostic testing philosophy.
  Reframe Selenium work as automation-first mindset. Emphasise CI/CD integration
  experience as a proxy for the missing Jenkins skill."
- cover_letter_angle: 1-2 sentences. The story angle. e.g. "Position the career
  transition from manual to automation testing as intentional and proactive, not
  reactive. The passion for quality-at-scale is the hook."
- honesty_flag: if critical_gaps has 3+ items AND there is no credible bridge
  for most of them, set this to True. A good career coach is honest.
- honesty_note: if honesty_flag=True, write a brief, kind, direct note the
  product can surface to the user: "This role requires X years of Y which your
  resume does not demonstrate. Applying is still worthwhile but manage expectations."

Return only valid JSON matching the schema. No markdown fences. No explanation.
```

---

## Agent 4 — Resume Rewrite

**Trigger:** Called after Gap Analysis  
**Input:** Original resume markdown + `GapAnalysisResult` + `JobAnalysisResult`  
**Output:** Three resume variants in markdown (stored in `generated_content` table)  

### Structured output model

```python
class ResumeVariant(BaseModel):
    variant: str           # "A_ats" | "B_impact" | "C_technical"
    content_md: str        # full resume in markdown
    changes_summary: str   # bullet list of key changes made

class ResumeRewriteResult(BaseModel):
    variants: list[ResumeVariant]   # always 3
    shared_changes: list[str]       # changes applied to all 3 variants
```

### System prompt

```
You are an expert resume writer and career strategist. You write in a clear,
professional, and results-driven style.

You are given:
1. resume_md — the candidate's current master resume in Markdown
2. job_analysis — what the job requires
3. gap_analysis — the strategic guidance for the rewrite

Your task is to produce THREE resume variants. Each is a complete, standalone
resume in Markdown. Do not produce diff patches — produce the full document.

Variant A — ATS-Optimised:
- Primary goal: pass automated keyword screening.
- Incorporate all ats_keywords from job_analysis naturally into bullets.
  Never keyword-stuff — each keyword must appear in a genuine, readable context.
- Use exact phrases from the job description where the candidate's experience
  legitimately supports it. e.g. if JD says "CI/CD pipelines" and the candidate
  built GitHub Actions workflows, say "CI/CD pipelines (GitHub Actions)".
- Section order: Summary → Skills → Experience → Education → Certifications.
- Skills section: flat comma-separated list or simple table. ATS parsers hate
  complex formatting.
- Bullet format: "Verb + what + result/context". No weak verbs (handled, worked on).

Variant B — Impact-Focused:
- Primary goal: impress a human hiring manager reading it cold.
- Lead every bullet with the business impact or outcome, not the task.
  e.g. "Reduced regression test cycle time by 40% by migrating from manual to
  Playwright-based automation across 3 product teams."
- Summary must be compelling and specific to this role — not a generic profile.
- Quantify wherever the original resume gives you numbers or context to do so.
- Remove anything that doesn't directly support the target role.

Variant C — Technical-Depth:
- Primary goal: impress a technical interviewer or CTO.
- Expand technical bullets — include tools, versions, architectural decisions,
  scale, edge cases handled.
- Add a "Technical highlights" or "Projects" section if the candidate has
  relevant side work or open source.
- Show technical reasoning, not just tasks. e.g. "Chose Playwright over Cypress
  for its multi-browser support and first-class TypeScript integration."

Rules for all variants:
- Do NOT invent experience. If the gap_analysis says a skill is missing, do not
  pretend the candidate has it.
- Do follow bridge_suggestions from gap_analysis — reframe, don't fabricate.
- Apply all quick_wins from gap_analysis — surface buried experience prominently.
- Keep the resume to 1-2 pages of content (Markdown length is a proxy — aim for
  under 600 words per variant excluding headers).
- Preserve all factual details: company names, dates, titles, institutions.
  You may rephrase bullets but not change the underlying facts.

For changes_summary: list the 4-6 most significant changes you made in this
variant versus the original. Be specific. e.g. "Added 'Playwright' to skills
section based on Selenium-to-Playwright bridge strategy from gap analysis."

Return only valid JSON matching the schema. No markdown fences. No explanation.
```

---

## Agent 5 — Interview Research (parallel)

**Trigger:** Runs in parallel after JD Analyzer completes. Does not depend on
resume matching.  
**Input:** `JobAnalysisResult` + company name + role title  
**Output:** `InterviewResearchResult` (stored in `generated_content` table)  

> **Note:** This agent uses web search (Tavily / SerpAPI / Brave) to fetch live
> company and hiring data. Budget 3–5 search calls per run.

### Structured output model

```python
class InterviewQuestion(BaseModel):
    question: str
    category: str          # technical | behavioural | situational | company
    why_asked: str         # what the interviewer is trying to assess
    strong_answer_tips: list[str]

class InterviewResearchResult(BaseModel):
    role_specific_questions: list[InterviewQuestion]   # 8-12 questions
    company_snapshot: str                               # 3-4 sentences
    tech_stack_intel: list[str]                        # tech they use, from public sources
    hiring_signals: list[str]                          # what they seem to value based on JD + research
    culture_notes: str                                 # 2-3 sentences on culture/values
    red_flags: list[str]                               # anything worth clarifying in interview
    prep_checklist: list[str]                          # 5-7 concrete things to prepare
```

### System prompt

```
You are an expert interview coach with deep knowledge of technical hiring.

You are given:
1. job_analysis — the structured analysis of the job description
2. company_name — the hiring company
3. role_title — the exact role title

You may also have access to web search results about the company.

Your task is to produce a comprehensive interview preparation package.

Rules:
- role_specific_questions: generate 8-12 questions that are SPECIFIC to this
  role and company — not generic interview questions.
  Mix of categories: ~4 technical, ~3 behavioural, ~2 situational, ~2 company.
  For technical questions: base them on required_skills and frameworks from
  job_analysis. e.g. if Playwright is required, ask about cross-browser testing
  strategy, flaky test management, CI integration patterns.
  For behavioural: use the responsibilities list to infer what situations
  the interviewer cares about.
- why_asked: be specific. "They're assessing whether you can debug timing issues
  in async tests, which is a common Playwright pain point."
- strong_answer_tips: 2-3 concrete tips, not generic advice.
  e.g. "Use the STAR format. Quantify the scale — number of tests, browsers,
  or pipeline minutes saved. Mention the specific Playwright API you used."
- company_snapshot: factual, from research. Revenue, size, product, recent news.
  If no research data is available, say "Limited public data available" and
  describe what can be inferred from the JD.
- tech_stack_intel: what technologies the company publicly uses. Check job
  postings, engineering blogs, GitHub, StackShare. List only what you can source.
- hiring_signals: what does the JD's language suggest they care about?
  e.g. "Heavy emphasis on CI/CD suggests a mature DevOps culture."
  "Mention of 'cross-functional collaboration' and 'agile' suggests they
  value communication as much as technical skill."
- red_flags: things a candidate should clarify before accepting an offer.
  e.g. "Salary listed as 'not disclosed' — negotiate from data, not desperation."
  "Role mentions 'wearing multiple hats' — probe for actual team size."
- prep_checklist: concrete, prioritised actions. e.g.:
  "1. Build a Playwright demo project with GitHub Actions CI if you don't have one."
  "2. Read their engineering blog at [url] before the interview."
  "3. Prepare a STAR story about a time you reduced test flakiness."

Return only valid JSON matching the schema. No markdown fences. No explanation.
```

---

## Orchestration layer (build last)

Once all five agents work independently, add a single orchestrator:

```python
class ApplicationPackage(BaseModel):
    job_id: str
    resume_id: str
    job_analysis: JobAnalysisResult
    resume_match: ResumeMatchResult
    gap_analysis: GapAnalysisResult
    resume_variants: ResumeRewriteResult
    interview_research: InterviewResearchResult
    generated_at: datetime
```

```
POST /api/applications/generate
{
  "job_id": "...",
  "resume_id": "..."
}
```

Orchestrator flow:
1. Run JD Analyzer (if not cached)
2. Run Resume Analyzer (if not cached)
3. Run Resume Matcher
4. Run Gap Analyzer
5. Run Resume Rewrite Agent
6. Run Interview Research Agent  ← fire this at step 1, collect at step 5
7. Assemble and return ApplicationPackage

Steps 1 and 6 can run concurrently. Steps 3, 4, 5 are strictly sequential.

---

## Database additions needed

```sql
-- Stores gap analysis output
CREATE TABLE gap_analyses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    resume_id UUID NOT NULL REFERENCES resumes(id),
    result JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);

-- Stores all generated content (resume variants, interview prep)
CREATE TABLE generated_content (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    resume_id UUID REFERENCES resumes(id),
    content_type TEXT NOT NULL,  -- resume_variant_a | resume_variant_b | resume_variant_c | interview_prep
    content_md TEXT,
    content_json JSONB,
    created_at TIMESTAMP DEFAULT now()
);

-- Tracks full application runs
CREATE TABLE application_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id),
    resume_id UUID NOT NULL REFERENCES resumes(id),
    status TEXT DEFAULT 'pending',  -- pending | running | complete | failed
    error TEXT,
    created_at TIMESTAMP DEFAULT now(),
    completed_at TIMESTAMP
);
```

---

## Implementation order

```
1. LLM provider abstraction          ← prerequisite for everything
2. JD Analyzer service + API         ← no dependencies, build first
3. Resume Analyzer service + API     ← no dependencies, build alongside 2
4. Resume Matcher service + API      ← depends on 2 + 3
5. Gap Analysis service + API        ← depends on 4
6. Resume Rewrite service + API      ← depends on 5
7. Interview Research service + API  ← depends on 2, add web search here
8. Orchestrator endpoint             ← ties everything together
9. Convert services to PydanticAI agents after step 8 is stable
```

Do not skip ahead. Each step produces testable output you can inspect before
proceeding. The agent layer in step 9 is thin — the intelligence lives in the
services and system prompts, not the orchestration.