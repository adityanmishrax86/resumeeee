from fastapi import APIRouter
from fastapi import Depends

from sqlalchemy.orm import Session

from app.db.database import get_db

from app.schemas.resume_schema import (
    ResumeCreateRequest,
    ResumeCreateResponse
)

from app.services.resume_service import (
    ResumeService
)

router = APIRouter(
    prefix="/api/resumes",
    tags=["resumes"]
)


@router.post(
    "",
    response_model=ResumeCreateResponse
)
def create_resume(
    request: ResumeCreateRequest,
    db: Session = Depends(get_db)
):

    resume_id = ResumeService.create_resume(
        db=db,
        name=request.name,
        content=request.content,
        is_master=request.is_master
    )

    return ResumeCreateResponse(
        resume_id=resume_id,
        status="stored"
    )