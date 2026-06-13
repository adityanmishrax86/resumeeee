from fastapi import APIRouter
from fastapi import Depends, HTTPException, Request, Form, UploadFile

from sqlalchemy.orm import Session
import logging
from app.db.database import get_db
from datetime import datetime
import re

from app.schemas.resume_schema import (
    ResumeCreateRequest,
    ResumeCreateResponse,
    ResumeMatchRequest,
    ResumeMatchResult,
    ResumeListItem,
)

from app.services.resume_service import (
    ResumeService
)
from app.agents import resume_matcher_agent
from app.models.analysis_models import ResumeMatch
from app.models.models import Resume
import uuid
import json
import ast


router = APIRouter(
    prefix="/api/resumes",
    tags=["resumes"]
)


@router.get("", response_model=list[ResumeListItem])
def list_resumes(db: Session = Depends(get_db)):
    return db.query(Resume).order_by(Resume.created_at.desc()).all()


@router.post("", response_model=ResumeCreateResponse)
async def create_resume(request: Request, db: Session = Depends(get_db)) -> ResumeCreateResponse:
    """Accept JSON, multipart/form-data, or raw markdown text for resume creation.

    This endpoint is more permissive than the original Pydantic-bound handler
    so clients that send raw markdown or multipart uploads will not receive
    a 422 Unprocessable Entity error.
    """

    content_type = (request.headers.get("content-type") or "").lower()
    name = None
    is_master = False
    resume_content = None

    try:
        if "application/json" in content_type:
            # Try strict JSON parse first. If it fails (common when clients
            # include unescaped newlines in string values), fall back to a
            # tolerant extraction from the raw body.
            try:
                payload = await request.json()
                name = payload.get("name")
                resume_content = payload.get("content") or payload.get("content_md")
                is_master = payload.get("is_master", False)
            except Exception:
                raw = await request.body()
                text = raw.decode("utf-8", errors="replace")

                # Try to extract fields with a tolerant regex (DOTALL so content
                # may contain newlines). This handles the common case where the
                # JSON body was posted with unescaped newlines inside strings.
                m_name = re.search(r'"name"\s*:\s*"(.*?)"', text, flags=re.DOTALL)
                if m_name:
                    name = m_name.group(1)

                m_is = re.search(r'"is_master"\s*:\s*(true|false)', text, flags=re.IGNORECASE)
                if m_is:
                    is_master = m_is.group(1).lower() == "true"

                m_content = re.search(r'"content"\s*:\s*"(.*?)"\s*(?:,\s*"is_master"|\})', text, flags=re.DOTALL)
                if m_content:
                    resume_content = m_content.group(1)
                else:
                    # If nothing matched, as a final fallback treat the whole
                    # body as the resume markdown (strip surrounding braces).
                    stripped = text.strip()
                    if stripped.startswith("{") and stripped.endswith("}"):
                        stripped = stripped[1:-1].strip()
                    resume_content = stripped

        elif "multipart/form-data" in content_type:
            form = await request.form()
            # Form fields: name, is_master, content or file
            name = form.get("name")
            is_master = form.get("is_master", False)
            if "file" in form:
                upload = form["file"]
                if isinstance(upload, UploadFile):
                    body = await upload.read()
                    resume_content = body.decode("utf-8")
            resume_content = resume_content or form.get("content") or form.get("content_md")

        else:
            # Treat as raw text body (text/plain or others)
            body = await request.body()
            resume_content = body.decode("utf-8").strip()
            name = request.query_params.get("name") or f"resume-{datetime.utcnow().isoformat()}"

    except Exception:
        logging.exception("Failed parsing create_resume request body")
        raise HTTPException(status_code=400, detail="invalid_request_body")

    if not name or not resume_content:
        raise HTTPException(status_code=422, detail="missing name or content")

    resume_id = ResumeService.create_resume(
        db=db,
        name=name,
        content=resume_content,
        is_master=bool(is_master),
    )

    return ResumeCreateResponse(resume_id=resume_id, status="stored")

@router.post("/match", response_model=ResumeMatchResult)
def match_resume(request: ResumeMatchRequest, db: Session = Depends(get_db)) -> ResumeMatchResult:
    agent = resume_matcher_agent()
    try:
    # Run the async agent synchronously for the request-response path
        import asyncio

        result = asyncio.run(agent.run(db, request.resume_id, request.job_analysis_id))
        # Expect the agent to return a ResumeMatchResult or a raw/str dict
        try:
            if isinstance(result, ResumeMatchResult):
                match_model = result
            else:
                # Use the service to parse/validate the raw agent response
                match_model = ResumeService.match_resume(db, result)
        except Exception as e:
            logging.exception("Failed to normalize agent result: %s", e)
            raise HTTPException(status_code=500, detail="invalid_agent_result")

        # Persist the match result (best-effort; don't fail the request on DB errors)
        try:
            payload = match_model.model_dump()
            match = ResumeMatch(
                id=uuid.uuid4(),
                resume_id=request.resume_id,
                job_analysis_id=request.job_analysis_id,
                result=payload,
                overall_score=match_model.overall_score,
                match_summary=match_model.match_summary,
            )
            db.add(match)
            db.commit()
        except Exception:
            logging.exception("Failed to persist resume match result")

        return match_model
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception:
        logging.exception("Synchronous resume match failed for %s", request.job_analysis_id)
        raise HTTPException(status_code=500, detail="analysis_failed")