from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from uuid import UUID
from typing import Literal
from typing import Dict


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


class ResumeMatchDraft(BaseModel):
    """LLM-authored narrative only; scores and match lists are computed server-side."""
    strengths: list[str] = Field(default_factory=list, max_length=4)
    improvement_suggestions: list[str] = Field(default_factory=list, max_length=5)
    match_summary: str = ""

class ResumeMatchResult(BaseModel):
    overall_score: int = Field(ge=0, le=100)
    skills_match_score: int = Field(ge=0, le=100)
    experience_match_score: int = Field(ge=0, le=100)
    domain_score: int = Field(default=0, ge=0, le=100)
    matched_required_skills: list[str]
    missing_required_skills: list[str]
    matched_preferred_skills: list[str]
    missing_preferred_skills: list[str]
    experience_fit: Literal["under_qualified", "match", "over_qualified"]
    ats_keyword_coverage: list[str]        # which ATS keywords appear in resume
    ats_keyword_gaps: list[str]            # ATS keywords missing from resume
    skill_evidence: Dict[str, str] = Field(default_factory=dict)
    ats_keyword_evidence: Dict[str, str] = Field(default_factory=dict)
    strengths: list[str] = Field(max_length=4)
    improvement_suggestions: list[str] = Field(max_length=5)
    match_summary: str                     # 2-3 sentences, honest assessment
