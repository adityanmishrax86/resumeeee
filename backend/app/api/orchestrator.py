import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session

import logfire

from app.db.database import get_db, SessionLocal
from app.agents import _create_llm_client
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
from app.schemas.orchestrator_schema import (
    OrchestratorRequest,
    OrchestratorResponse,
    RetryAgentRequest,
    AgentStatus,
    ALL_AGENTS,
)
from app.services.orchestrator_service import (
    OrchestratorService,
    _find_or_create_run,
    _hydrate_response_with_run,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orchestrate", tags=["orchestrate"])


def _make_orchestrator() -> OrchestratorService:
    return OrchestratorService(
        job_analyzer_client=_create_llm_client(),
        resume_analyzer_client=_create_llm_client(),
        resume_matcher_client=_create_llm_client(),
        gap_analysis_client=_create_llm_client(),
        resume_rewrite_client=_create_llm_client(),
        interview_research_client=_create_llm_client(),
    )


# ──────────────────────────────────────────────────────────────────────────────
# Background runner — captures the caller's Logfire context so spans created
# inside the BG task remain attached to the originating HTTP request.
# ──────────────────────────────────────────────────────────────────────────────

def _run_orchestration_bg(req: OrchestratorRequest, run_id: str, parent_ctx) -> None:
    db2 = SessionLocal()
    try:
        run = db2.query(ApplicationRun).filter(ApplicationRun.id == run_id).first()
        if run is None:
            logger.error("Background orchestration: run %s vanished", run_id)
            return
        orchestrator = _make_orchestrator()
        import asyncio

        async def _do():
            await orchestrator.run(
                db=db2,
                job_id=req.job_id,
                resume_id=req.resume_id,
                company_name=req.company_name,
                role_title=req.role_title,
                skip_job_analysis=req.skip_job_analysis,
                skip_resume_analysis=req.skip_resume_analysis,
                skip_interview_research=req.skip_interview_research,
                force=req.force,
                run=run,
            )

        if parent_ctx is not None:
            with logfire.attach_context(parent_ctx):
                asyncio.run(_do())
        else:
            asyncio.run(_do())
    except Exception:
        logger.exception("Background orchestration failed run_id=%s", run_id)
        # Best-effort: mark run failed if it wasn't already.
        try:
            run = db2.query(ApplicationRun).filter(ApplicationRun.id == run_id).first()
            if run is not None and run.status not in ("complete", "failed"):
                run.status = "failed"
                run.error_code = "internal_error"
                run.error_detail = "background task crashed"
                run.updated_at = datetime.utcnow()
                db2.commit()
        except Exception:
            logger.exception("Failed to mark run %s as failed after BG crash", run_id)
    finally:
        db2.close()


@router.post("", response_model=OrchestratorResponse)
async def run_orchestrator(
    request: OrchestratorRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Enqueue the 6-agent pipeline for (job, resume).

    Always runs in the background. Returns `run_id` plus current status:
    - If a completed run for this pair already exists and `force=false`, the
      existing run's snapshot is returned without scheduling new work.
    - If a run is already in progress, that one's status is returned (no
      duplicate background task is queued).
    - Otherwise a fresh `application_runs` row is created and a BG task is
      scheduled.
    """
    existing = (
        db.query(ApplicationRun)
        .filter(
            ApplicationRun.job_id == request.job_id,
            ApplicationRun.resume_id == request.resume_id,
        )
        .order_by(ApplicationRun.created_at.desc())
        .first()
    )

    if existing is not None and not request.force:
        if existing.status == "complete":
            return _build_status_response(db, existing)
        if existing.status in ("running", "queued"):
            return _build_status_response(db, existing)

    run = _find_or_create_run(db, job_id=request.job_id, resume_id=request.resume_id, force=request.force)
    run.status = "queued"
    run.error_code = None
    run.error_detail = None
    run.updated_at = datetime.utcnow()
    db.commit()

    # Capture the request-scoped Logfire context so descendant spans created
    # in the BG task are linked to the HTTP request that scheduled them.
    try:
        parent_ctx = logfire.get_context()
    except Exception:
        parent_ctx = None

    background_tasks.add_task(_run_orchestration_bg, request, str(run.id), parent_ctx)

    return _build_status_response(db, run)


@router.get("/status/{job_id}/{resume_id}", response_model=OrchestratorResponse)
def get_orchestrator_status(job_id: str, resume_id: str, db: Session = Depends(get_db)):
    """Return the latest run for (job, resume) — including a real `failed` state."""
    run = (
        db.query(ApplicationRun)
        .filter(ApplicationRun.job_id == job_id, ApplicationRun.resume_id == resume_id)
        .order_by(ApplicationRun.created_at.desc())
        .first()
    )
    if run is None:
        # No run started yet — surface this as a 404 so the UI can distinguish
        # "never started" from "queued / running".
        raise HTTPException(status_code=404, detail="no_run_for_pair")
    return _build_status_response(db, run)


@router.post("/retry-agent", response_model=OrchestratorResponse)
async def retry_agent(
    request: RetryAgentRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Re-run a single failed agent without rerunning the whole pipeline.

    The orchestrator's `_run_chain` is restarted, but skip-if-exists checks
    consult the previous run's `agent_statuses` so already-successful steps
    are reused. Only the failed agent (and the steps that depend on it) are
    actually re-executed.
    """
    if request.agent not in ALL_AGENTS:
        raise HTTPException(status_code=400, detail=f"unknown_agent: {request.agent}")

    run = (
        db.query(ApplicationRun)
        .filter(ApplicationRun.job_id == request.job_id, ApplicationRun.resume_id == request.resume_id)
        .order_by(ApplicationRun.created_at.desc())
        .first()
    )
    if run is None:
        raise HTTPException(status_code=404, detail="no_run_for_pair")
    if run.status == "running":
        raise HTTPException(status_code=409, detail="run_already_in_progress")

    # Reset the failed agent so skip-if-exists will not short-circuit it.
    statuses = dict(run.agent_statuses or {})
    statuses[request.agent] = {
        "status": "pending",
        "error_code": None,
        "error_detail": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
    run.agent_statuses = statuses
    run.status = "queued"
    run.error_code = None
    run.error_detail = None
    run.updated_at = datetime.utcnow()
    db.commit()

    # Reuse the same BG runner — it will pick up the existing run row and the
    # chain will skip already-complete steps and re-execute the reset agent.
    req = OrchestratorRequest(
        job_id=request.job_id,
        resume_id=request.resume_id,
        skip_job_analysis=False,
        skip_resume_analysis=False,
        skip_interview_research=False,
        force=False,
    )
    try:
        parent_ctx = logfire.get_context()
    except Exception:
        parent_ctx = None
    background_tasks.add_task(_run_orchestration_bg, req, str(run.id), parent_ctx)

    return _build_status_response(db, run)


# ──────────────────────────────────────────────────────────────────────────────
# Status helpers
# ──────────────────────────────────────────────────────────────────────────────

def _build_status_response(db: Session, run: ApplicationRun) -> OrchestratorResponse:
    response = OrchestratorResponse(
        job_id=str(run.job_id),
        resume_id=str(run.resume_id),
        status=run.status,
        run_id=str(run.id),
    )
    _hydrate_response_with_run(response, run)

    # Hydrate inline results from the per-agent tables so the frontend has
    # everything it needs in one round-trip when the run is complete.
    ja = (
        db.query(JobAnalysis)
        .filter(JobAnalysis.job_id == run.job_id)
        .order_by(JobAnalysis.created_at.desc())
        .first()
    )
    if ja:
        response.job_analysis_id = str(ja.id)
        response.job_analysis = ja.result

    ra = (
        db.query(ResumeAnalysis)
        .filter(ResumeAnalysis.resume_id == run.resume_id)
        .order_by(ResumeAnalysis.created_at.desc())
        .first()
    )
    if ra:
        response.resume_analysis_id = str(ra.id)
        response.resume_analysis = ra.result

    if ja:
        rm = (
            db.query(ResumeMatch)
            .filter(
                ResumeMatch.resume_id == run.resume_id,
                ResumeMatch.job_analysis_id == ja.id,
            )
            .order_by(ResumeMatch.created_at.desc())
            .first()
        )
        if rm:
            response.resume_match_id = str(rm.id)
            response.resume_match = rm.result

            ga = (
                db.query(GapAnalysis)
                .filter(
                    GapAnalysis.job_analysis_id == ja.id,
                    GapAnalysis.resume_match_id == rm.id,
                )
                .order_by(GapAnalysis.created_at.desc())
                .first()
            )
            if ga:
                response.gap_analysis_id = str(ga.id)
                response.gap_analysis = ga.result

                rr = (
                    db.query(ResumeRewrite)
                    .filter(
                        ResumeRewrite.resume_id == run.resume_id,
                        ResumeRewrite.gap_analysis_id == ga.id,
                    )
                    .order_by(ResumeRewrite.created_at.desc())
                    .first()
                )
                if rr:
                    response.resume_rewrite_id = str(rr.id)
                    response.resume_rewrite = rr.result

        ir = (
            db.query(InterviewResearch)
            .filter(InterviewResearch.job_analysis_id == ja.id)
            .order_by(InterviewResearch.created_at.desc())
            .first()
        )
        if ir:
            response.interview_research_id = str(ir.id)
            response.interview_research = ir.result

        cl = (
            db.query(CoverLetter)
            .filter(
                CoverLetter.resume_id == run.resume_id,
                CoverLetter.job_analysis_id == ja.id,
            )
            .order_by(CoverLetter.created_at.desc())
            .first()
        )
        if cl:
            response.cover_letter_id = str(cl.id)
            response.cover_letter = cl.result

    return response
