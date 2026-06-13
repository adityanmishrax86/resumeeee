from pydantic import BaseModel, Field
from typing import Optional, Any


class OrchestratorRequest(BaseModel):
    job_id: str
    resume_id: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    # Skip specific stages if their outputs already exist
    skip_job_analysis: bool = False
    skip_resume_analysis: bool = False
    skip_interview_research: bool = False


class OrchestratorResponse(BaseModel):
    job_id: str
    resume_id: str
    status: str                                    # queued | running | complete | failed
    error: Optional[str] = None

    # IDs of persisted records — populated when status == complete
    job_analysis_id: Optional[str] = None
    resume_analysis_id: Optional[str] = None
    resume_match_id: Optional[str] = None
    gap_analysis_id: Optional[str] = None
    resume_rewrite_id: Optional[str] = None
    interview_research_id: Optional[str] = None

    # Inline results — populated when background=false
    job_analysis: Optional[Any] = None
    resume_match: Optional[Any] = None
    gap_analysis: Optional[Any] = None
    resume_rewrite: Optional[Any] = None
    interview_research: Optional[Any] = None
