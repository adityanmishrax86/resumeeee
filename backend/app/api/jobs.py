from fastapi import APIRouter
from fastapi import Depends, BackgroundTasks, HTTPException

from sqlalchemy.orm import Session

import os
import logging

from app.db.database import get_db, SessionLocal

from app.schemas.job_schema import (
    JobIngestRequest,
    JobIngestResponse,
    JobListItem,
    JobDetail,
)

from app.models.models import Job
from app.models.analysis_models import JobAnalysis
from app.services.job_service import JobService
from app.services.job_analyzer_service import JobAnalyzerService
from app.agents import get_job_analyzer_agent

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"]
)


@router.get("", response_model=list[JobListItem])
def list_jobs(db: Session = Depends(get_db)):
    return db.query(Job).order_by(Job.created_at.desc()).all()


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job


@router.delete("/{job_id}", status_code=204)
def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Cascade-delete a job and every derived analysis row.

    Returns 204 No Content on success, 404 if the job did not exist.
    """
    deleted = JobService.delete_job(db=db, job_id=job_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="job_not_found")
    return None


@router.get("/{job_id}/analysis")
def get_job_analysis(job_id: str, db: Session = Depends(get_db)):
    ja = (
        db.query(JobAnalysis)
        .filter(JobAnalysis.job_id == job_id)
        .order_by(JobAnalysis.created_at.desc())
        .first()
    )
    if not ja:
        raise HTTPException(status_code=404, detail="analysis_not_found")
    return ja.result


@router.post(
    "/ingest",
    response_model=JobIngestResponse
)
def ingest_job(
    request: JobIngestRequest,
    db: Session = Depends(get_db)
):

    job_id = JobService.ingest_job(
        db=db,
        source=request.source,
        payload=request.payload
    )

    return JobIngestResponse(
        job_id=job_id,
        status="stored"
    )


@router.post("/{job_id}/analyze")
async def analyze_job(
    job_id: str,
    background: bool = True,
    stream: bool = False,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db)
):
    """Analyze a job description and store structured analysis.

    By default the analysis runs in the background (returns 202-like response).
    Pass `?background=false` to run synchronously and return the analysis JSON.
    """

    # Use the singleton agent to run analyses (agent created based on LLM_PROVIDER)
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    logging.info("LLM provider selected: %s", llm_provider)
    agent = get_job_analyzer_agent()

    if stream:
        raise HTTPException(status_code=400, detail="streaming_not_supported")

    if background:
        # Run in background using a fresh DB session and the async agent
        async def _run_analysis(bg_job_id: str):
            db2 = SessionLocal()
            try:
                await agent.run(db2, bg_job_id)
            except Exception:
                logging.exception("Background job analysis failed for %s", bg_job_id)
            finally:
                db2.close()

        if background_tasks is None:
            background_tasks = BackgroundTasks()

        background_tasks.add_task(_run_analysis, job_id)

        return {"job_id": job_id, "status": "analysis_queued"}

    # synchronous path
    try:
        result = await agent.run(db, job_id)
        # Return the Pydantic model instance directly so FastAPI can handle
        # serialization and validation. Agent.run returns a Pydantic model.
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        logging.exception("Synchronous job analysis failed for %s", job_id)
        raise HTTPException(status_code=500, detail="analysis_failed")