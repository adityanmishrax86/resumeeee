from fastapi import APIRouter
from fastapi import Depends, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

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
from app.llm.clients import MockLLMClient, NvidiaNIMClient
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
def analyze_job(
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

    if stream and background:
        raise HTTPException(status_code=400, detail="stream cannot be used with background=true")

    if stream:
        # Streaming is only supported for providers that expose SSE (NVIDIA NIM).
        if llm_provider in ("nim", "nvidia", "nvidia-nim"):
            try:
                client = NvidiaNIMClient()
            except Exception:
                logging.exception("Failed to initialize NvidiaNIMClient for streaming")
                raise HTTPException(status_code=500, detail="streaming_init_failed")

            try:
                system_prompt, user_prompt = JobAnalyzerService.prepare_prompts(db, job_id)
            except ValueError as ve:
                raise HTTPException(status_code=404, detail=str(ve))

            gen = client.generate(system_prompt=system_prompt, user_prompt=user_prompt, stream=True)

            def sse_wrapper():
                if isinstance(gen, str):
                    yield f"data: {gen}\n\n"
                    yield "data: [DONE]\n\n"
                    return
                try:
                    for chunk in gen:
                        if chunk is None:
                            continue
                        yield f"data: {chunk}\n\n"
                except GeneratorExit:
                    return

            return StreamingResponse(sse_wrapper(), media_type="text/event-stream")

        raise HTTPException(status_code=400, detail="streaming not supported for selected LLM provider")

    if background:
        # Run in background using a fresh DB session and the async agent
        def _run_analysis(bg_job_id: str):
            db2 = SessionLocal()
            try:
                import asyncio

                asyncio.run(agent.run(db2, bg_job_id))
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
        # Run the async agent synchronously for the request-response path
        import asyncio

        result = asyncio.run(agent.run(db, job_id))
        # Return the Pydantic model instance directly so FastAPI can handle
        # serialization and validation. Agent.run returns a Pydantic model.
        return result
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        logging.exception("Synchronous job analysis failed for %s", job_id)
        raise HTTPException(status_code=500, detail="analysis_failed")