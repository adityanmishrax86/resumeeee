from fastapi import APIRouter
from fastapi import Depends, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from sqlalchemy.orm import Session

import os
import logging

from app.db.database import get_db, SessionLocal

from app.schemas.job_schema import (
    JobIngestRequest,
    JobIngestResponse
)

from app.services.job_service import JobService
from app.services.job_analyzer_service import JobAnalyzerService
from app.llm.clients import MockLLMClient, NvidiaNIMClient

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"]
)


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

    # Select LLM client based on env; default to MockLLMClient for now.
    llm_provider = os.getenv("LLM_PROVIDER", "mock").lower()
    logging.info("LLM provider selected: %s", llm_provider)
    if llm_provider in ("nim", "nvidia", "nvidia-nim"):
        try:
            client = NvidiaNIMClient()
            logging.info("Initialized NvidiaNIMClient with invoke_url=%s model=%s", getattr(client, 'invoke_url', None), getattr(client, 'model', None))
        except Exception:
            logging.exception("Failed to initialize NvidiaNIMClient, falling back to MockLLMClient")
            client = MockLLMClient()
    else:
        client = MockLLMClient()
        logging.info("Using MockLLMClient for LLM operations")

    if stream and background:
        raise HTTPException(status_code=400, detail="stream cannot be used with background=true")

    if stream:
        # Prepare prompts and stream the LLM output as SSE
        try:
            system_prompt, user_prompt = JobAnalyzerService.prepare_prompts(db, job_id)
        except ValueError as ve:
            raise HTTPException(status_code=404, detail=str(ve))

        # Generate streaming iterator from client
        gen = client.generate(system_prompt=system_prompt, user_prompt=user_prompt, stream=True)

        # Wrap generator or string into SSE formatted StreamingResponse
        def sse_wrapper():
            # If client returned a single string, send it as one data event
            if isinstance(gen, str):
                yield f"data: {gen}\n\n"
                yield "data: [DONE]\n\n"
                return

            try:
                for chunk in gen:
                    # Each chunk is expected to be a JSON string or text
                    if chunk is None:
                        continue
                    yield f"data: {chunk}\n\n"
            except GeneratorExit:
                return

        return StreamingResponse(sse_wrapper(), media_type="text/event-stream")

    if background:
        # Run in background using a fresh DB session
        def _run_analysis(bg_job_id: str, llm_client):
            db2 = SessionLocal()
            try:
                JobAnalyzerService.analyze_job(db2, bg_job_id, llm_client)
            except Exception:
                logging.exception("Background job analysis failed for %s", bg_job_id)
            finally:
                db2.close()

        if background_tasks is None:
            # BackgroundTasks should be provided by FastAPI; if it's not, run sync
            background_tasks = BackgroundTasks()

        background_tasks.add_task(_run_analysis, job_id, client)

        return {"job_id": job_id, "status": "analysis_queued"}

    # synchronous path
    try:
        result = JobAnalyzerService.analyze_job(db, job_id, client)
        # pydantic v2 uses model_dump(); model_dump returns a dict suitable for JSON response
        try:
            return result.model_dump()
        except Exception:
            # Fallback for pydantic v1 compatibility
            return result.dict()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        logging.exception("Synchronous job analysis failed for %s", job_id)
        raise HTTPException(status_code=500, detail="analysis_failed")