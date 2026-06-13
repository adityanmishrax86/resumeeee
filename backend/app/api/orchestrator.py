import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db, SessionLocal
from app.agents import (
    get_job_analyzer_agent,
    get_resume_analyzer_agent,
    get_resume_matcher_agent,
    get_gap_analysis_agent,
    get_resume_rewrite_agent,
    get_interview_research_agent,
    _create_llm_client,
)
from app.schemas.orchestrator_schema import OrchestratorRequest, OrchestratorResponse
from app.services.orchestrator_service import OrchestratorService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])


def _make_orchestrator() -> OrchestratorService:
    """Build an OrchestratorService using per-agent LLM clients."""
    return OrchestratorService(
        job_analyzer_client=_create_llm_client(),
        resume_analyzer_client=_create_llm_client(),
        resume_matcher_client=_create_llm_client(),
        gap_analysis_client=_create_llm_client(),
        resume_rewrite_client=_create_llm_client(),
        interview_research_client=_create_llm_client(),
    )


@router.post("", response_model=OrchestratorResponse)
def run_orchestrator(
    request: OrchestratorRequest,
    background: bool = True,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """Run the full 5-agent pipeline for a job + resume pair.

    - `background=true` (default): enqueues the pipeline and returns immediately
      with `status=queued`.
    - `background=false`: runs synchronously and returns the full result inline.
    """

    orchestrator = _make_orchestrator()

    if background:
        def _run(req: OrchestratorRequest):
            db2 = SessionLocal()
            try:
                asyncio.run(
                    orchestrator.run(
                        db=db2,
                        job_id=req.job_id,
                        resume_id=req.resume_id,
                        company_name=req.company_name,
                        role_title=req.role_title,
                        skip_job_analysis=req.skip_job_analysis,
                        skip_resume_analysis=req.skip_resume_analysis,
                        skip_interview_research=req.skip_interview_research,
                    )
                )
            except Exception:
                logger.exception("Background orchestration failed for job_id=%s resume_id=%s", req.job_id, req.resume_id)
            finally:
                db2.close()

        if background_tasks is None:
            background_tasks = BackgroundTasks()

        background_tasks.add_task(_run, request)

        return OrchestratorResponse(
            job_id=request.job_id,
            resume_id=request.resume_id,
            status="queued",
        )

    # Synchronous path
    try:
        result = asyncio.run(
            orchestrator.run(
                db=db,
                job_id=request.job_id,
                resume_id=request.resume_id,
                company_name=request.company_name,
                role_title=request.role_title,
                skip_job_analysis=request.skip_job_analysis,
                skip_resume_analysis=request.skip_resume_analysis,
                skip_interview_research=request.skip_interview_research,
            )
        )
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        logger.exception("Orchestration failed for job_id=%s resume_id=%s", request.job_id, request.resume_id)
        raise HTTPException(status_code=500, detail="orchestration_failed")

    return result
