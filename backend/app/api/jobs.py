from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.database import get_db

from app.schemas.job_schema import (
    JobIngestRequest,
    JobIngestResponse
)

from app.services.job_service import JobService

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