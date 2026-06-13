"""
OrchestratorService — full 5-agent pipeline.

Execution order (from plan.md):
  1. JD Analyzer      (required)
  2. Resume Analyzer  (required, runs in parallel with 1)
  3. Resume Matcher   (depends on 1 + 2)
  4. Gap Analyzer     (depends on 3)
  5. Resume Rewriter  (depends on 4)
  6. Interview Research (fires at step 1, collected at step 5)

Steps 1 and 6 run concurrently (asyncio.gather).
Steps 3, 4, 5 are strictly sequential.
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.clients import BaseLLMClient
from app.schemas.orchestrator_schema import OrchestratorResponse

logger = logging.getLogger(__name__)


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
    ) -> OrchestratorResponse:
        response = OrchestratorResponse(job_id=job_id, resume_id=resume_id, status="running")

        # ── Lazy imports (avoid circular imports at module load) ───────────────
        from app.agents.job_analyzer_agent import JobAnalyzerAgent
        from app.agents.resume_analyzer_agent import ResumeAnalyzerAgent
        from app.agents.resume_matcher_agent import ResumeMatcherAgent
        from app.agents.gap_analysis_agent import GapAnalysisAgent
        from app.agents.resume_rewrite_agent import ResumeRewriteAgent
        from app.agents.interview_research_agent import InterviewResearchAgent
        from app.models.analysis_models import JobAnalysis, ResumeAnalysis

        # ── Step 1 & 2: JD Analyzer + Resume Analyzer run concurrently ────────
        job_analysis_result = None
        resume_analysis_result = None

        async def _run_job_analysis():
            nonlocal job_analysis_result
            if skip_job_analysis:
                # Use the most recent existing analysis
                existing = (
                    db.query(JobAnalysis)
                    .filter(JobAnalysis.job_id == job_id)
                    .order_by(JobAnalysis.created_at.desc())
                    .first()
                )
                if existing:
                    logger.info("Orchestrator: reusing existing job analysis %s", existing.id)
                    response.job_analysis_id = str(existing.id)
                    from app.schemas.job_analysis_schema import JobAnalysisResult
                    job_analysis_result = JobAnalysisResult.parse_obj(existing.result)
                    return
            agent = JobAnalyzerAgent(self.job_analyzer_client)
            result = await agent.run(db=db, job_id=job_id)
            existing = (
                db.query(JobAnalysis)
                .filter(JobAnalysis.job_id == job_id)
                .order_by(JobAnalysis.created_at.desc())
                .first()
            )
            response.job_analysis_id = str(existing.id) if existing else None
            response.job_analysis = result.model_dump()
            job_analysis_result = result

        async def _run_resume_analysis():
            nonlocal resume_analysis_result
            if skip_resume_analysis:
                existing = (
                    db.query(ResumeAnalysis)
                    .filter(ResumeAnalysis.resume_id == resume_id)
                    .order_by(ResumeAnalysis.created_at.desc())
                    .first()
                )
                if existing:
                    logger.info("Orchestrator: reusing existing resume analysis %s", existing.id)
                    response.resume_analysis_id = str(existing.id)
                    from app.schemas.resume_analysis_schema import ResumeAnalysisResult
                    resume_analysis_result = ResumeAnalysisResult.parse_obj(existing.result)
                    return
            agent = ResumeAnalyzerAgent(self.resume_analyzer_client)
            result = await agent.run(db=db, resume_id=resume_id)
            existing = (
                db.query(ResumeAnalysis)
                .filter(ResumeAnalysis.resume_id == resume_id)
                .order_by(ResumeAnalysis.created_at.desc())
                .first()
            )
            response.resume_analysis_id = str(existing.id) if existing else None
            resume_analysis_result = result

        try:
            await asyncio.gather(_run_job_analysis(), _run_resume_analysis())
        except Exception:
            logger.exception("Orchestrator: step 1/2 failed for job_id=%s", job_id)
            response.status = "failed"
            response.error = "job_or_resume_analysis_failed"
            return response

        # ── Step 3: Resume Matcher (sequential) ───────────────────────────────
        resume_match_result = None
        resume_match_id = None
        try:
            matcher_agent = ResumeMatcherAgent(self.resume_matcher_client)
            resume_match_result = await matcher_agent.run(
                db=db,
                resume_id=resume_id,
                job_analysis_id=response.job_analysis_id,
            )
            from app.models.analysis_models import ResumeMatch
            rm_row = (
                db.query(ResumeMatch)
                .filter(ResumeMatch.resume_id == resume_id, ResumeMatch.job_analysis_id == response.job_analysis_id)
                .order_by(ResumeMatch.created_at.desc())
                .first()
            )
            resume_match_id = str(rm_row.id) if rm_row else None
            response.resume_match_id = resume_match_id
            response.resume_match = resume_match_result.model_dump()
        except Exception:
            logger.exception("Orchestrator: step 3 (resume match) failed for job_id=%s resume_id=%s", job_id, resume_id)
            response.status = "failed"
            response.error = "resume_match_failed"
            return response

        # ── Steps 4 & 6: Gap Analysis + Interview Research concurrently ───────
        gap_analysis_result = None
        gap_analysis_id = None
        interview_research_result = None

        async def _run_gap_analysis():
            nonlocal gap_analysis_result, gap_analysis_id
            agent = GapAnalysisAgent(self.gap_analysis_client)
            result = await agent.run(
                db=db,
                job_analysis_id=response.job_analysis_id,
                resume_match_id=resume_match_id,
            )
            from app.models.analysis_models import GapAnalysis
            ga_row = (
                db.query(GapAnalysis)
                .filter(
                    GapAnalysis.job_analysis_id == response.job_analysis_id,
                    GapAnalysis.resume_match_id == resume_match_id,
                )
                .order_by(GapAnalysis.created_at.desc())
                .first()
            )
            gap_analysis_id = str(ga_row.id) if ga_row else None
            response.gap_analysis_id = gap_analysis_id
            response.gap_analysis = result.model_dump()
            gap_analysis_result = result

        async def _run_interview_research():
            nonlocal interview_research_result
            if skip_interview_research:
                return
            try:
                agent = InterviewResearchAgent(self.interview_research_client)
                result = await agent.run(
                    db=db,
                    job_analysis_id=response.job_analysis_id,
                    company_name=company_name,
                    role_title=role_title,
                )
                from app.models.analysis_models import InterviewResearch
                ir_row = (
                    db.query(InterviewResearch)
                    .filter(InterviewResearch.job_analysis_id == response.job_analysis_id)
                    .order_by(InterviewResearch.created_at.desc())
                    .first()
                )
                response.interview_research_id = str(ir_row.id) if ir_row else None
                response.interview_research = result.model_dump()
                interview_research_result = result
            except Exception:
                # Interview research failure is non-blocking — log and continue
                logger.exception("Orchestrator: interview research failed (non-fatal) for job_id=%s", job_id)

        try:
            await asyncio.gather(_run_gap_analysis(), _run_interview_research())
        except Exception:
            logger.exception("Orchestrator: step 4/6 failed for job_id=%s", job_id)
            response.status = "failed"
            response.error = "gap_analysis_failed"
            return response

        # ── Step 5: Resume Rewrite (depends on Gap Analysis) ──────────────────
        try:
            rewrite_agent = ResumeRewriteAgent(self.resume_rewrite_client)
            rewrite_result = await rewrite_agent.run(
                db=db,
                resume_id=resume_id,
                gap_analysis_id=gap_analysis_id,
                job_analysis_id=response.job_analysis_id,
            )
            from app.models.analysis_models import ResumeRewrite
            rr_row = (
                db.query(ResumeRewrite)
                .filter(ResumeRewrite.resume_id == resume_id)
                .order_by(ResumeRewrite.created_at.desc())
                .first()
            )
            response.resume_rewrite_id = str(rr_row.id) if rr_row else None
            response.resume_rewrite = rewrite_result.model_dump()
        except Exception:
            # Rewrite failure is non-blocking — log and continue
            logger.exception("Orchestrator: resume rewrite failed (non-fatal) for resume_id=%s", resume_id)

        response.status = "complete"
        return response
