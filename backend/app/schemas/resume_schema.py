from pydantic import BaseModel, ConfigDict
from datetime import datetime
from uuid import UUID


class ResumeCreateRequest(BaseModel):
    name: str
    content: str
    is_master: bool = False


class ResumeCreateResponse(BaseModel):
    resume_id: str
    status: str


class ResumeListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    is_master: bool
    created_at: datetime


class ResumeMatchRequest(BaseModel):
    resume_id: str
    job_analysis_id: str

class ResumeMatchResult(BaseModel):
    overall_score: int                     # 0–100
    skills_match_score: int                # 0–100
    experience_match_score: int            # 0–100
    matched_required_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    missing_preferred_skills: list[str]
    experience_fit: str                    # under_qualified | match | over_qualified
    ats_keyword_coverage: list[str]        # which ATS keywords appear in resume
    ats_keyword_gaps: list[str]            # ATS keywords missing from resume
    strengths: list[str]                   # max 4, for this specific job
    improvement_suggestions: list[str]     # max 5, specific and actionable
    match_summary: str                     # 2-3 sentences, honest assessment