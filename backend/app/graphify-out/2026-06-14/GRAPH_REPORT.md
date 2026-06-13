# Graph Report - .  (2026-06-14)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 250 nodes · 555 edges · 21 communities (13 shown, 8 thin omitted)
- Extraction: 47% EXTRACTED · 53% INFERRED · 0% AMBIGUOUS · INFERRED: 294 edges (avg confidence: 0.52)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `45184cde`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Community 0|Community 0]]
- [[_COMMUNITY_Community 1|Community 1]]
- [[_COMMUNITY_Community 2|Community 2]]
- [[_COMMUNITY_Community 3|Community 3]]
- [[_COMMUNITY_Community 4|Community 4]]
- [[_COMMUNITY_Community 5|Community 5]]
- [[_COMMUNITY_Community 6|Community 6]]
- [[_COMMUNITY_Community 7|Community 7]]
- [[_COMMUNITY_Community 8|Community 8]]
- [[_COMMUNITY_Community 9|Community 9]]
- [[_COMMUNITY_Community 10|Community 10]]
- [[_COMMUNITY_Community 11|Community 11]]
- [[_COMMUNITY_Community 12|Community 12]]
- [[_COMMUNITY_Community 14|Community 14]]
- [[_COMMUNITY_Community 15|Community 15]]
- [[_COMMUNITY_Community 16|Community 16]]
- [[_COMMUNITY_Community 17|Community 17]]
- [[_COMMUNITY_Community 18|Community 18]]
- [[_COMMUNITY_Community 19|Community 19]]
- [[_COMMUNITY_Community 20|Community 20]]

## God Nodes (most connected - your core abstractions)
1. `JobAnalysis` - 27 edges
2. `BaseLLMClient` - 24 edges
3. `OrchestratorService` - 19 edges
4. `ResumeMatch` - 17 edges
5. `ResumeService` - 16 edges
6. `AgentAdapter` - 15 edges
7. `GapAnalysis` - 15 edges
8. `ResumeMatchResult` - 14 edges
9. `JobAnalyzerService` - 14 edges
10. `InterviewResearchAgent` - 14 edges

## Surprising Connections (you probably didn't know these)
- `BaseLLMClient` --uses--> `BaseLLMClient`  [INFERRED]
  agents/agent_adapter.py → llm/clients.py
- `BaseModel` --uses--> `BaseLLMClient`  [INFERRED]
  agents/agent_adapter.py → llm/clients.py
- `ResumeMatcherAgent` --uses--> `ResumeMatchResult`  [INFERRED]
  agents/resume_matcher_agent.py → schemas/resume_schema.py
- `ResumeMatcherAgent` --uses--> `ResumeService`  [INFERRED]
  agents/resume_matcher_agent.py → services/resume_service.py
- `BaseLLMClient` --uses--> `ResumeMatchResult`  [INFERRED]
  agents/resume_matcher_agent.py → schemas/resume_schema.py

## Import Cycles
- None detected.

## Communities (21 total, 8 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.10
Nodes (30): AgentAdapter, GapAnalysisAgent, Agent wrapper for the GapAnalysisService., BaseLLMClient, ResumeAnalysisResult, Session, ResumeAnalyzerAgent, Agent wrapper for the ResumeRewriteService. (+22 more)

### Community 1 - "Community 1"
Cohesion: 0.10
Nodes (22): ABC, AgentAdapter, BaseLLMClient, Base adapter for wrapping an LLM client into an async agent.      Subclasses s, Call the underlying LLM client and return a string response.          This hel, JobAnalyzerAgent, BaseLLMClient, JobAnalysisResult (+14 more)

### Community 2 - "Community 2"
Cohesion: 0.14
Nodes (18): InterviewResearchAgent, BaseLLMClient, InterviewResearchResult, Session, Agent wrapper for the InterviewResearchService.      Routing logic (checked at, Create a tool-enabled GoogleClient and reuse the standard service path., BaseLLMClient, GoogleClient (+10 more)

### Community 3 - "Community 3"
Cohesion: 0.16
Nodes (16): BaseLLMClient, ResumeRewriteResult, Session, Base, JobAnalysis, ResumeRewrite, ResumeRewriteResult, BaseLLMClient (+8 more)

### Community 4 - "Community 4"
Cohesion: 0.23
Nodes (18): BaseModel, create_resume(), match_resume(), ResumeMatchResult, Session, Accept JSON, multipart/form-data, or raw markdown text for resume creation., ResumeMatch, Request (+10 more)

### Community 5 - "Community 5"
Cohesion: 0.15
Nodes (14): BaseLLMClient, GapAnalysisResult, Session, BaseModel, GapAnalysis, GapAnalysisResult, GapItem, InterviewQuestion (+6 more)

### Community 6 - "Community 6"
Cohesion: 0.17
Nodes (14): analyze_job(), ingest_job(), Session, Analyze a job description and store structured analysis.      By default the a, BackgroundTasks, JobIngestRequest, MockLLMClient, NvidiaNIMClient (+6 more)

### Community 7 - "Community 7"
Cohesion: 0.17
Nodes (15): ApplicationPackage, Gap Analysis Agent, GapAnalysisResult, Interview Research Agent, InterviewResearchResult, JD Analyzer Agent, JobAnalysisResult, ResumeMatchResult (+7 more)

### Community 8 - "Community 8"
Cohesion: 0.26
Nodes (7): Base, DeclarativeBase, Job, JobRawPayload, JobSkill, Resume, JobService

### Community 9 - "Community 9"
Cohesion: 0.33
Nodes (6): Gap Analyzer System Prompt, Gap Analyzer User Prompt Template, Resume Rewriter System Prompt, Resume Rewriter User Prompt Template, GapAnalysisResult Schema, ResumeRewriteResult Schema

### Community 10 - "Community 10"
Cohesion: 0.67
Nodes (3): Interview Researcher System Prompt, Interview Researcher User Prompt Template, InterviewResearchResult Schema

### Community 11 - "Community 11"
Cohesion: 0.67
Nodes (3): Resume Analyzer System Prompt, Resume Analyzer User Prompt Template, ResumeAnalysisResult Schema

## Knowledge Gaps
- **16 isolated node(s):** `gap_analyses table`, `generated_content table`, `application_runs table`, `JD Analyzer System Prompt`, `JD Analyzer User Prompt Template` (+11 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **8 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `JobAnalysis` connect `Community 3` to `Community 0`, `Community 1`, `Community 2`, `Community 4`, `Community 5`, `Community 8`?**
  _High betweenness centrality (0.231) - this node is a cross-community bridge._
- **Why does `OrchestratorService` connect `Community 0` to `Community 2`, `Community 3`, `Community 4`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.136) - this node is a cross-community bridge._
- **Why does `BaseLLMClient` connect `Community 1` to `Community 2`, `Community 3`, `Community 4`, `Community 6`?**
  _High betweenness centrality (0.125) - this node is a cross-community bridge._
- **Are the 25 inferred relationships involving `JobAnalysis` (e.g. with `Base` and `OrchestratorResponse`) actually correct?**
  _`JobAnalysis` has 25 INFERRED edges - model-reasoned connections that need verification._
- **Are the 19 inferred relationships involving `BaseLLMClient` (e.g. with `AgentAdapter` and `BaseLLMClient`) actually correct?**
  _`BaseLLMClient` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `OrchestratorService` (e.g. with `Session` and `BackgroundTasks`) actually correct?**
  _`OrchestratorService` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `ResumeMatch` (e.g. with `match_resume()` and `ResumeMatchResult`) actually correct?**
  _`ResumeMatch` has 15 INFERRED edges - model-reasoned connections that need verification._