"""
OrchestratorService — full 7-agent pipeline.

Execution order:
  1. JD Analyzer      (required)  ─┐  parallel
  2. Resume Analyzer  (required)  ─┘
  3. Resume Matcher   (depends on 1 + 2)
  4. Gap Analyzer     (depends on 3)
  5. Resume Rewriter  ─┐
     Cover Letter     ─┤  parallel (all depend on 4)
     Interview Prep   ─┘

Steps 1 and 2 run concurrently (asyncio.gather).
Step 3 is sequential, step 4 is sequential.
Steps 5 (rewrite + cover letter + interview) run concurrently.

Run state is persisted in `application_runs` so the status endpoint can report
`failed`/`complete` reliably and a single agent can be retried without rerunning
the whole chain.
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Callable, Awaitable

from sqlalchemy.orm import Session

import logfire

from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMError, LLMServiceUnavailable, LLMRateLimited
from app.schemas.orchestrator_schema import (
    OrchestratorResponse,
    AgentStatus,
    AGENT_JOB_ANALYZER,
    AGENT_RESUME_ANALYZER,
    AGENT_RESUME_MATCHER,
    AGENT_GAP_ANALYSIS,
    AGENT_RESUME_REWRITE,
    AGENT_INTERVIEW_RESEARCH,
    AGENT_COVER_LETTER,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Run-state helpers (kept here so the orchestrator owns its persistence model)
# ──────────────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _set_agent_status(run, agent: str, status: str, *, error_code: Optional[str] = None, error_detail: Optional[str] = None) -> None:
    statuses = dict(run.agent_statuses or {})
    statuses[agent] = {
        "status": status,
        "error_code": error_code,
        "error_detail": error_detail,
        "updated_at": _now_iso(),
    }
    run.agent_statuses = statuses
    run.updated_at = datetime.utcnow()


def _classify_error_code(exc: Exception) -> str:
    if isinstance(exc, LLMServiceUnavailable):
        return "llm_unavailable"
    if isinstance(exc, LLMRateLimited):
        return "rate_limited"
    if isinstance(exc, LLMError):
        return "llm_error"
    return "internal_error"


class OrchestratorService:
    def __init__(
        self,
        job_analyzer_client: BaseLLMClient,
        resume_analyzer_client: BaseLLMClient,
        resume_matcher_client: BaseLLMClient,
        gap_analysis_client: BaseLLMClient,
        resume_rewrite_client: BaseLLMClient,
        interview_research_client: BaseLLMClient,
    ):
        self.job_analyzer_client = job_analyzer_client
        self.resume_analyzer_client = resume_analyzer_client
        self.resume_matcher_client = resume_matcher_client
        self.gap_analysis_client = gap_analysis_client
        self.resume_rewrite_client = resume_rewrite_client
        self.interview_research_client = interview_research_client

    # ── public entrypoint ────────────────────────────────────────────────────
    async def run(
        self,
        db: Session,
        job_id: str,
        resume_id: str,
        company_name: Optional[str] = None,
        role_title: Optional[str] = None,
        skip_job_analysis: bool = False,
        skip_resume_analysis: bool = False,
        skip_interview_research: bool = False,
        force: bool = False,
        run=None,
    ) -> OrchestratorResponse:
        # Lazy imports avoid circular imports at module load
        from app.agents.job_analyzer_agent import JobAnalyzerAgent
        from app.agents.resume_analyzer_agent import ResumeAnalyzerAgent
        from app.agents.resume_matcher_agent import ResumeMatcherAgent
        from app.agents.gap_analysis_agent import GapAnalysisAgent
        from app.agents.resume_rewrite_agent import ResumeRewriteAgent
        from app.agents.interview_research_agent import InterviewResearchAgent
        from app.agents.cover_letter_agent import CoverLetterAgent
        from app.models.analysis_models import (
            ApplicationRun,
            JobAnalysis,
            ResumeAnalysis,
            ResumeMatch,
            GapAnalysis,
            ResumeRewrite,
            InterviewResearch,
            CoverLetter,
        )

        # Find-or-create the ApplicationRun row. The caller may pass an
        # already-created one (the API does, to return run_id immediately).
        if run is None:
            run = _find_or_create_run(db, job_id=job_id, resume_id=resume_id, force=force)
        run.status = "running"
        run.error_code = None
        run.error_detail = None
        run.updated_at = datetime.utcnow()
        db.commit()

        response = OrchestratorResponse(
            job_id=job_id,
            resume_id=resume_id,
            status="running",
            run_id=str(run.id),
        )

        # Open a top-level span and bind run/job/resume ids as baggage so every
        # descendant span (HTTP, DB, pydantic-ai) carries them automatically.
        with logfire.set_baggage(run_id=str(run.id), job_id=job_id, resume_id=resume_id):
            with logfire.span(
                "orchestrator.run",
                run_id=str(run.id),
                job_id=job_id,
                resume_id=resume_id,
            ) as root_span:
                try:
                    await self._run_chain(
                        db=db,
                        run=run,
                        response=response,
                        job_id=job_id,
                        resume_id=resume_id,
                        company_name=company_name,
                        role_title=role_title,
                        skip_job_analysis=skip_job_analysis,
                        skip_resume_analysis=skip_resume_analysis,
                        skip_interview_research=skip_interview_research,
                        JobAnalyzerAgent=JobAnalyzerAgent,
                        ResumeAnalyzerAgent=ResumeAnalyzerAgent,
                        ResumeMatcherAgent=ResumeMatcherAgent,
                        GapAnalysisAgent=GapAnalysisAgent,
                        ResumeRewriteAgent=ResumeRewriteAgent,
                        InterviewResearchAgent=InterviewResearchAgent,
                        CoverLetterAgent=CoverLetterAgent,
                        JobAnalysis=JobAnalysis,
                        ResumeAnalysis=ResumeAnalysis,
                        ResumeMatch=ResumeMatch,
                        GapAnalysis=GapAnalysis,
                        ResumeRewrite=ResumeRewrite,
                        InterviewResearch=InterviewResearch,
                        CoverLetter=CoverLetter,
                    )
                except _StopChain:
                    # _run_chain raises this after marking the run failed.
                    return _hydrate_response_with_run(response, run)
                except Exception as exc:
                    logger.exception("Orchestrator: unexpected error run_id=%s", run.id)
                    root_span.record_exception(exc)
                    run.status = "failed"
                    run.error_code = "internal_error"
                    run.error_detail = str(exc)[:1000]
                    db.commit()
                    return _hydrate_response_with_run(response, run)

        run.status = "complete"
        run.updated_at = datetime.utcnow()
        db.commit()
        return _hydrate_response_with_run(response, run)

    # ── internal chain ───────────────────────────────────────────────────────
    async def _run_chain(
        self,
        *,
        db,
        run,
        response: OrchestratorResponse,
        job_id: str,
        resume_id: str,
        company_name: Optional[str],
        role_title: Optional[str],
        skip_job_analysis: bool,
        skip_resume_analysis: bool,
        skip_interview_research: bool,
        JobAnalyzerAgent,
        ResumeAnalyzerAgent,
        ResumeMatcherAgent,
        GapAnalysisAgent,
        ResumeRewriteAgent,
        InterviewResearchAgent,
        CoverLetterAgent,
        JobAnalysis,
        ResumeAnalysis,
        ResumeMatch,
        GapAnalysis,
        ResumeRewrite,
        InterviewResearch,
        CoverLetter,
    ) -> None:
        job_analysis_result = None
        resume_analysis_result = None

        # ── Steps 1 & 2 (parallel) ───────────────────────────────────────────
        async def _job_analysis():
            nonlocal job_analysis_result
            if skip_job_analysis:
                existing = (
                    db.query(JobAnalysis)
                    .filter(JobAnalysis.job_id == job_id)
                    .order_by(JobAnalysis.created_at.desc())
                    .first()
                )
                if existing:
                    response.job_analysis_id = str(existing.id)
                    from app.schemas.job_analysis_schema import JobAnalysisResult
                    job_analysis_result = JobAnalysisResult.parse_obj(existing.result)
                    _set_agent_status(run, AGENT_JOB_ANALYZER, "skipped")
                    return
            agent = JobAnalyzerAgent(self.job_analyzer_client)
            result = await agent.run(db=db, job_id=job_id)
            row = (
                db.query(JobAnalysis)
                .filter(JobAnalysis.job_id == job_id)
                .order_by(JobAnalysis.created_at.desc())
                .first()
            )
            response.job_analysis_id = str(row.id) if row else None
            job_analysis_result = result

        async def _resume_analysis():
            nonlocal resume_analysis_result
            if skip_resume_analysis:
                existing = (
                    db.query(ResumeAnalysis)
                    .filter(ResumeAnalysis.resume_id == resume_id)
                    .order_by(ResumeAnalysis.created_at.desc())
                    .first()
                )
                if existing:
                    response.resume_analysis_id = str(existing.id)
                    from app.schemas.resume_analysis_schema import ResumeAnalysisResult
                    resume_analysis_result = ResumeAnalysisResult.parse_obj(existing.result)
                    _set_agent_status(run, AGENT_RESUME_ANALYZER, "skipped")
                    return
            agent = ResumeAnalyzerAgent(self.resume_analyzer_client)
            result = await agent.run(db=db, resume_id=resume_id)
            row = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.resume_id == resume_id)
                .order_by(ResumeAnalysis.created_at.desc())
                .first()
            )
            response.resume_analysis_id = str(row.id) if row else None
            resume_analysis_result = result

        await asyncio.gather(
            self._wrap_agent(db, run, AGENT_JOB_ANALYZER, _job_analysis),
            self._wrap_agent(db, run, AGENT_RESUME_ANALYZER, _resume_analysis),
        )

        # ── Step 3: Resume Matcher (skip-if-exists) ──────────────────────────
        resume_match_id: Optional[str] = None

        async def _resume_match():
            nonlocal resume_match_id
            existing = (
                db.query(ResumeMatch)
                .filter(
                    ResumeMatch.resume_id == resume_id,
                    ResumeMatch.job_analysis_id == response.job_analysis_id,
                )
                .order_by(ResumeMatch.created_at.desc())
                .first()
            )
            if existing and not _agent_failed_previously(run, AGENT_RESUME_MATCHER):
                resume_match_id = str(existing.id)
                response.resume_match_id = resume_match_id
                _set_agent_status(run, AGENT_RESUME_MATCHER, "skipped")
                return
            agent = ResumeMatcherAgent(self.resume_matcher_client)
            await agent.run(
                db=db,
                resume_id=resume_id,
                job_analysis_id=response.job_analysis_id,
            )
            row = (
                db.query(ResumeMatch)
                .filter(
                    ResumeMatch.resume_id == resume_id,
                    ResumeMatch.job_analysis_id == response.job_analysis_id,
                )
                .order_by(ResumeMatch.created_at.desc())
                .first()
            )
            resume_match_id = str(row.id) if row else None
            response.resume_match_id = resume_match_id

        await self._wrap_agent(db, run, AGENT_RESUME_MATCHER, _resume_match)

        # ── Step 4: Gap Analysis (sequential) ────────────────────────────────
        gap_analysis_id: Optional[str] = None

        async def _gap_analysis():
            nonlocal gap_analysis_id
            existing = (
                db.query(GapAnalysis)
                .filter(
                    GapAnalysis.job_analysis_id == response.job_analysis_id,
                    GapAnalysis.resume_match_id == resume_match_id,
                )
                .order_by(GapAnalysis.created_at.desc())
                .first()
            )
            if existing and not _agent_failed_previously(run, AGENT_GAP_ANALYSIS):
                gap_analysis_id = str(existing.id)
                response.gap_analysis_id = gap_analysis_id
                _set_agent_status(run, AGENT_GAP_ANALYSIS, "skipped")
                return
            agent = GapAnalysisAgent(self.gap_analysis_client)
            await agent.run(
                db=db,
                job_analysis_id=response.job_analysis_id,
                resume_match_id=resume_match_id,
            )
            row = (
                db.query(GapAnalysis)
                .filter(
                    GapAnalysis.job_analysis_id == response.job_analysis_id,
                    GapAnalysis.resume_match_id == resume_match_id,
                )
                .order_by(GapAnalysis.created_at.desc())
                .first()
            )
            gap_analysis_id = str(row.id) if row else None
            response.gap_analysis_id = gap_analysis_id

        await self._wrap_agent(db, run, AGENT_GAP_ANALYSIS, _gap_analysis)

        # ── Step 5: Resume Rewrite ‖ Cover Letter ‖ Interview Research ───────
        # All three depend on gap_analysis being complete. They fire in
        # parallel to minimise wall-clock time.

        async def _resume_rewrite():
            existing = (
                db.query(ResumeRewrite)
                .filter(
                    ResumeRewrite.resume_id == resume_id,
                    ResumeRewrite.gap_analysis_id == gap_analysis_id,
                )
                .order_by(ResumeRewrite.created_at.desc())
                .first()
            )
            if existing and not _agent_failed_previously(run, AGENT_RESUME_REWRITE):
                response.resume_rewrite_id = str(existing.id)
                _set_agent_status(run, AGENT_RESUME_REWRITE, "skipped")
                return
            agent = ResumeRewriteAgent(self.resume_rewrite_client)
            await agent.run(
                db=db,
                resume_id=resume_id,
                gap_analysis_id=gap_analysis_id,
                job_analysis_id=response.job_analysis_id,
            )
            row = (
                db.query(ResumeRewrite)
                .filter(ResumeRewrite.resume_id == resume_id)
                .order_by(ResumeRewrite.created_at.desc())
                .first()
            )
            response.resume_rewrite_id = str(row.id) if row else None

        async def _cover_letter():
            existing = (
                db.query(CoverLetter)
                .filter(
                    CoverLetter.resume_id == resume_id,
                    CoverLetter.job_analysis_id == response.job_analysis_id,
                )
                .order_by(CoverLetter.created_at.desc())
                .first()
            )
            if existing and not _agent_failed_previously(run, AGENT_COVER_LETTER):
                response.cover_letter_id = str(existing.id)
                response.cover_letter = existing.result if isinstance(existing.result, dict) else None
                _set_agent_status(run, AGENT_COVER_LETTER, "skipped")
                return
            agent = CoverLetterAgent(self.resume_rewrite_client)
            result = await agent.run(
                db=db,
                resume_id=resume_id,
                job_analysis_id=response.job_analysis_id,
                gap_analysis_id=gap_analysis_id,
            )
            row = (
                db.query(CoverLetter)
                .filter(
                    CoverLetter.resume_id == resume_id,
                    CoverLetter.job_analysis_id == response.job_analysis_id,
                )
                .order_by(CoverLetter.created_at.desc())
                .first()
            )
            response.cover_letter_id = str(row.id) if row else None
            response.cover_letter = result.model_dump() if result is not None else None

        async def _interview_research():
            if skip_interview_research:
                _set_agent_status(run, AGENT_INTERVIEW_RESEARCH, "skipped")
                return
            existing = (
                db.query(InterviewResearch)
                .filter(InterviewResearch.job_analysis_id == response.job_analysis_id)
                .order_by(InterviewResearch.created_at.desc())
                .first()
            )
            if existing and not _agent_failed_previously(run, AGENT_INTERVIEW_RESEARCH):
                response.interview_research_id = str(existing.id)
                _set_agent_status(run, AGENT_INTERVIEW_RESEARCH, "skipped")
                return
            # Fall back to the Job row when the caller didn't supply
            # company/role context — the frontend rarely sends them and the
            # interview prompt is much weaker without them.
            effective_company = company_name
            effective_role = role_title
            if not effective_company or not effective_role:
                from app.models.models import Job
                job_row = db.query(Job).filter(Job.id == job_id).first()
                if job_row is not None:
                    effective_company = effective_company or job_row.company_name
                    effective_role = effective_role or job_row.role_title
            agent = InterviewResearchAgent(self.interview_research_client)
            await agent.run(
                db=db,
                job_analysis_id=response.job_analysis_id,
                company_name=effective_company,
                role_title=effective_role,
            )
            row = (
                db.query(InterviewResearch)
                .filter(InterviewResearch.job_analysis_id == response.job_analysis_id)
                .order_by(InterviewResearch.created_at.desc())
                .first()
            )
            response.interview_research_id = str(row.id) if row else None

        await asyncio.gather(
            self._wrap_agent(db, run, AGENT_RESUME_REWRITE, _resume_rewrite),
            self._wrap_agent(db, run, AGENT_COVER_LETTER, _cover_letter, non_blocking=True),
            self._wrap_agent(db, run, AGENT_INTERVIEW_RESEARCH, _interview_research, non_blocking=True),
        )

    # ── per-agent wrapper: span, status update, failure classification ──────
    async def _wrap_agent(
        self,
        db,
        run,
        agent: str,
        body: Callable[[], Awaitable[None]],
        *,
        non_blocking: bool = False,
    ) -> None:
        start = time.time()
        _set_agent_status(run, agent, "running")
        db.commit()
        logger.info("[%s] starting run_id=%s", agent, run.id)
        with logfire.span("agent.{agent}", agent=agent, run_id=str(run.id)) as span:
            try:
                await body()
            except LLMServiceUnavailable as exc:
                # 503 = stop the entire chain. Mark the run failed.
                logger.error("[%s] LLM unavailable (503) run_id=%s: %s", agent, run.id, exc)
                span.record_exception(exc)
                _set_agent_status(run, agent, "failed", error_code="llm_unavailable", error_detail=str(exc)[:500])
                run.status = "failed"
                run.error_code = "llm_unavailable"
                run.error_detail = f"[{agent}] {exc}"[:1000]
                db.commit()
                raise _StopChain()
            except LLMRateLimited as exc:
                # 429 = stop the chain but flag this agent as retryable so the
                # user can re-run just this one step.
                logger.error("[%s] LLM rate limited (429) run_id=%s: %s", agent, run.id, exc)
                span.record_exception(exc)
                _set_agent_status(run, agent, "failed", error_code="rate_limited", error_detail=str(exc)[:500])
                run.status = "failed"
                run.error_code = "rate_limited"
                run.error_detail = f"[{agent}] {exc}"[:1000]
                db.commit()
                raise _StopChain()
            except Exception as exc:
                code = _classify_error_code(exc)
                logger.exception("[%s] failed run_id=%s code=%s", agent, run.id, code)
                span.record_exception(exc)
                _set_agent_status(run, agent, "failed", error_code=code, error_detail=str(exc)[:500])
                if non_blocking:
                    db.commit()
                    return
                run.status = "failed"
                run.error_code = code
                run.error_detail = f"[{agent}] {exc}"[:1000]
                db.commit()
                raise _StopChain()
            else:
                _set_agent_status(run, agent, "complete")
                db.commit()
                logger.info("[%s] completed in %.2fs run_id=%s", agent, time.time() - start, run.id)


class _StopChain(Exception):
    """Internal signal: stop the orchestration chain. The run row already
    reflects the failure when this is raised."""


# ──────────────────────────────────────────────────────────────────────────────
# Helpers exported for the API layer (find-or-create + response hydration).
# ──────────────────────────────────────────────────────────────────────────────

def _find_or_create_run(db: Session, *, job_id: str, resume_id: str, force: bool):
    from app.models.analysis_models import ApplicationRun

    if not force:
        existing = (
            db.query(ApplicationRun)
            .filter(ApplicationRun.job_id == job_id, ApplicationRun.resume_id == resume_id)
            .order_by(ApplicationRun.created_at.desc())
            .first()
        )
        if existing is not None:
            return existing
    run = ApplicationRun(job_id=job_id, resume_id=resume_id, status="queued", agent_statuses={})
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def _agent_failed_previously(run, agent: str) -> bool:
    """True if a prior attempt of this agent failed — used by skip-if-exists
    to avoid reusing stale rows when the previous run was a partial failure."""
    statuses = run.agent_statuses or {}
    state = statuses.get(agent) or {}
    return state.get("status") == "failed"


def _hydrate_response_with_run(response: OrchestratorResponse, run) -> OrchestratorResponse:
    response.run_id = str(run.id)
    response.status = run.status
    response.error_code = run.error_code
    response.error = run.error_detail
    statuses = {}
    for agent, payload in (run.agent_statuses or {}).items():
        if not isinstance(payload, dict):
            continue
        statuses[agent] = AgentStatus(
            status=payload.get("status", "pending"),
            error_code=payload.get("error_code"),
            error_detail=payload.get("error_detail"),
            updated_at=payload.get("updated_at"),
        )
    response.agent_statuses = statuses
    return response
