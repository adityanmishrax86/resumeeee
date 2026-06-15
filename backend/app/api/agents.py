import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.agents import _create_llm_client
from app.agents.job_analyzer_agent import JobAnalyzerAgent
from app.agents.resume_analyzer_agent import ResumeAnalyzerAgent
from app.agents.resume_matcher_agent import ResumeMatcherAgent
from app.agents.gap_analysis_agent import GapAnalysisAgent
from app.agents.interview_research_agent import InterviewResearchAgent
from app.agents.resume_rewrite_agent import ResumeRewriteAgent
from app.agents.cover_letter_agent import CoverLetterAgent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agents", tags=["Agents"])

class JobAnalyzerRequest(BaseModel):
    job_id: str

@router.post("/job-analyzer")
async def run_job_analyzer(req: JobAnalyzerRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = JobAnalyzerAgent(client)
    try:
        result = await agent.run(db=db, job_id=req.job_id)
        return result
    except Exception as e:
        logger.exception("Job Analyzer failed")
        raise HTTPException(status_code=500, detail=str(e))

class ResumeAnalyzerRequest(BaseModel):
    resume_id: str

@router.post("/resume-analyzer")
async def run_resume_analyzer(req: ResumeAnalyzerRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = ResumeAnalyzerAgent(client)
    try:
        result = await agent.run(db=db, resume_id=req.resume_id)
        return result
    except Exception as e:
        logger.exception("Resume Analyzer failed")
        raise HTTPException(status_code=500, detail=str(e))

class ResumeMatcherRequest(BaseModel):
    resume_id: str
    job_analysis_id: str

@router.post("/resume-matcher")
async def run_resume_matcher(req: ResumeMatcherRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = ResumeMatcherAgent(client)
    try:
        result = await agent.run(db=db, resume_id=req.resume_id, job_analysis_id=req.job_analysis_id)
        return result
    except Exception as e:
        logger.exception("Resume Matcher failed")
        raise HTTPException(status_code=500, detail=str(e))

class GapAnalyzerRequest(BaseModel):
    job_analysis_id: str
    resume_match_id: str

@router.post("/gap-analyzer")
async def run_gap_analyzer(req: GapAnalyzerRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = GapAnalysisAgent(client)
    try:
        result = await agent.run(db=db, job_analysis_id=req.job_analysis_id, resume_match_id=req.resume_match_id)
        return result
    except Exception as e:
        logger.exception("Gap Analyzer failed")
        raise HTTPException(status_code=500, detail=str(e))

class InterviewResearchRequest(BaseModel):
    job_analysis_id: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None

@router.post("/interview-research")
async def run_interview_research(req: InterviewResearchRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = InterviewResearchAgent(client)
    try:
        result = await agent.run(db=db, job_analysis_id=req.job_analysis_id, company_name=req.company_name, role_title=req.role_title)
        return result
    except Exception as e:
        logger.exception("Interview Research failed")
        raise HTTPException(status_code=500, detail=str(e))

class ResumeRewriteRequest(BaseModel):
    resume_id: str
    gap_analysis_id: str
    job_analysis_id: str
    custom_instructions: Optional[str] = None

@router.post("/resume-rewrite")
async def run_resume_rewrite(req: ResumeRewriteRequest, db: Session = Depends(get_db)):
    client = _create_llm_client()
    agent = ResumeRewriteAgent(client)
    try:
        result = await agent.run(
            db=db,
            resume_id=req.resume_id,
            gap_analysis_id=req.gap_analysis_id,
            job_analysis_id=req.job_analysis_id,
            custom_instructions=req.custom_instructions,
        )
        return result
    except Exception as e:
        logger.exception("Resume Rewrite failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Custom-prompt regen endpoints (variants + interview only) ─────────────────


class ResumeRewriteRegenRequest(BaseModel):
    resume_id: str
    gap_analysis_id: str
    job_analysis_id: str
    custom_instructions: str


@router.post("/resume-rewrite/regen")
async def regen_resume_rewrite(req: ResumeRewriteRegenRequest, db: Session = Depends(get_db)):
    """Regenerate resume variants with user-provided custom instructions."""
    client = _create_llm_client()
    agent = ResumeRewriteAgent(client)
    try:
        return await agent.run(
            db=db,
            resume_id=req.resume_id,
            gap_analysis_id=req.gap_analysis_id,
            job_analysis_id=req.job_analysis_id,
            custom_instructions=req.custom_instructions,
        )
    except Exception as e:
        logger.exception("Resume Rewrite regen failed")
        raise HTTPException(status_code=500, detail=str(e))


class InterviewRegenRequest(BaseModel):
    job_analysis_id: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    custom_instructions: str


@router.post("/interview-research/regen")
async def regen_interview_research(req: InterviewRegenRequest, db: Session = Depends(get_db)):
    """Regenerate interview prep with user-provided custom instructions."""
    client = _create_llm_client()
    agent = InterviewResearchAgent(client)
    try:
        return await agent.run(
            db=db,
            job_analysis_id=req.job_analysis_id,
            company_name=req.company_name,
            role_title=req.role_title,
            custom_instructions=req.custom_instructions,
        )
    except Exception as e:
        logger.exception("Interview research regen failed")
        raise HTTPException(status_code=500, detail=str(e))


class InterviewMoreRequest(BaseModel):
    job_analysis_id: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    count: int = 10
    custom_instructions: Optional[str] = None


@router.post("/interview-research/more")
async def more_interview_questions(req: InterviewMoreRequest, db: Session = Depends(get_db)):
    """Append more interview questions to the existing research row."""
    from app.services.interview_research_service import InterviewResearchService

    if req.count <= 0 or req.count > 50:
        raise HTTPException(status_code=400, detail="count must be between 1 and 50")

    client = _create_llm_client()

    # Backfill empty company/role from the Job row when caller didn't supply them.
    effective_company = req.company_name
    effective_role = req.role_title
    if not effective_company or not effective_role:
        from app.models.analysis_models import JobAnalysis
        from app.models.models import Job
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == req.job_analysis_id).first()
        if ja is not None:
            job_row = db.query(Job).filter(Job.id == ja.job_id).first()
            if job_row is not None:
                effective_company = effective_company or job_row.company_name
                effective_role = effective_role or job_row.role_title

    try:
        return await InterviewResearchService.generate_more_questions(
            db=db,
            job_analysis_id=req.job_analysis_id,
            company_name=effective_company,
            role_title=effective_role,
            count=req.count,
            llm_client=client,
            custom_instructions=req.custom_instructions,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Interview research generate-more failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Interview: streaming detailed answer ──────────────────────────────────────


class InterviewAnswerStreamRequest(BaseModel):
    job_analysis_id: Optional[str] = None
    question: str
    category: Optional[str] = None
    why_asked: Optional[str] = None
    existing_tips: Optional[list[str]] = None
    custom_instructions: Optional[str] = None


@router.post("/interview-research/answer/stream")
async def stream_interview_answer(
    req: InterviewAnswerStreamRequest, db: Session = Depends(get_db)
):
    """Stream a detailed answer for a single interview question as SSE.

    Emits ``data: <token>\\n\\n`` events followed by a terminal
    ``data: [DONE]\\n\\n``. No database write — caller chooses to save via the
    ``/interview-research/save`` endpoint.
    """
    from fastapi.responses import StreamingResponse
    from app.services.interview_research_service import InterviewResearchService as _Svc

    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="question is required")

    async def event_source():
        try:
            async for chunk in _Svc.stream_detailed_answer(
                db=db,
                job_analysis_id=req.job_analysis_id,
                question=req.question,
                category=req.category,
                why_asked=req.why_asked,
                existing_tips=req.existing_tips,
                custom_instructions=req.custom_instructions,
            ):
                if not chunk:
                    continue
                # SSE line discipline: escape any embedded newlines so the
                # whole chunk arrives in a single `data:` event.
                safe = chunk.replace("\r\n", "\n").replace("\n", "\\n")
                yield f"data: {safe}\n\n"
        except Exception as exc:
            logger.exception("Streaming interview answer failed")
            err = str(exc).replace("\n", " ")
            yield f"event: error\ndata: {err}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


# ── Interview: resume-grounded profile questions ─────────────────────────────


class ProfileQuestionsRequest(BaseModel):
    resume_id: str
    job_analysis_id: Optional[str] = None
    count: int = 8
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    custom_instructions: Optional[str] = None


@router.post("/interview-research/profile-questions")
async def generate_profile_questions(
    req: ProfileQuestionsRequest, db: Session = Depends(get_db)
):
    """Generate resume-grounded interview questions on demand. Not persisted."""
    from app.services.interview_research_service import InterviewResearchService as _Svc

    if req.count <= 0 or req.count > 30:
        raise HTTPException(status_code=400, detail="count must be between 1 and 30")

    client = _create_llm_client()
    try:
        questions = await _Svc.generate_profile_questions(
            db=db,
            resume_id=req.resume_id,
            job_analysis_id=req.job_analysis_id,
            count=req.count,
            llm_client=client,
            company_name=req.company_name,
            role_title=req.role_title,
            custom_instructions=req.custom_instructions,
        )
        return {"questions": [q.model_dump() for q in questions]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Profile question generation failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Interview: opt-in save (user questions + detailed answers) ───────────────


class _SaveUserQuestion(BaseModel):
    question: str
    category: str = "user"
    why_asked: str = ""
    strong_answer_tips: list[str] = []
    detailed_answer: Optional[str] = None
    source: Optional[str] = "user"


class _SaveAnswerUpdate(BaseModel):
    question: str
    detailed_answer: str


class SaveInterviewItemsRequest(BaseModel):
    job_analysis_id: str
    user_questions: Optional[list[_SaveUserQuestion]] = None
    updated_answers: Optional[list[_SaveAnswerUpdate]] = None


@router.post("/interview-research/save")
async def save_interview_items(
    req: SaveInterviewItemsRequest, db: Session = Depends(get_db)
):
    """Persist user-added questions and/or streamed detailed answers."""
    from app.services.interview_research_service import InterviewResearchService as _Svc

    if not req.user_questions and not req.updated_answers:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of user_questions or updated_answers",
        )

    try:
        result = _Svc.save_user_items(
            db=db,
            job_analysis_id=req.job_analysis_id,
            user_questions=[q.model_dump() for q in (req.user_questions or [])],
            updated_answers=[u.model_dump() for u in (req.updated_answers or [])],
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Save interview items failed")
        raise HTTPException(status_code=500, detail=str(e))


# ── Cover Letter ──────────────────────────────────────────────────────────────


class CoverLetterRequest(BaseModel):
    resume_id: str
    job_analysis_id: Optional[str] = None
    gap_analysis_id: Optional[str] = None
    custom_instructions: Optional[str] = None


@router.post("/cover-letter")
async def run_cover_letter(req: CoverLetterRequest, db: Session = Depends(get_db)):
    """Generate three cover-letter variants (professional / story / startup)."""
    client = _create_llm_client()
    agent = CoverLetterAgent(client)
    try:
        return await agent.run(
            db=db,
            resume_id=req.resume_id,
            job_analysis_id=req.job_analysis_id,
            gap_analysis_id=req.gap_analysis_id,
            custom_instructions=req.custom_instructions,
        )
    except Exception as e:
        logger.exception("Cover letter generation failed")
        raise HTTPException(status_code=500, detail=str(e))
