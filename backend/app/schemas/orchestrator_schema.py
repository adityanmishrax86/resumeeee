from pydantic import BaseModel, Field
from typing import Optional, Any, Dict


# Canonical agent names used across orchestrator, status, and retry endpoints.
AGENT_JOB_ANALYZER = "job_analyzer"
AGENT_RESUME_ANALYZER = "resume_analyzer"
AGENT_RESUME_MATCHER = "resume_matcher"
AGENT_GAP_ANALYSIS = "gap_analysis"
AGENT_RESUME_REWRITE = "resume_rewrite"
AGENT_INTERVIEW_RESEARCH = "interview_research"
AGENT_COVER_LETTER = "cover_letter"

ALL_AGENTS = (
    AGENT_JOB_ANALYZER,
    AGENT_RESUME_ANALYZER,
    AGENT_RESUME_MATCHER,
    AGENT_GAP_ANALYSIS,
    AGENT_RESUME_REWRITE,
    AGENT_INTERVIEW_RESEARCH,
    AGENT_COVER_LETTER,
)


class OrchestratorRequest(BaseModel):
    job_id: str
    resume_id: str
    company_name: Optional[str] = None
    role_title: Optional[str] = None
    # Skip specific stages if their outputs already exist
    skip_job_analysis: bool = False
    skip_resume_analysis: bool = False
    skip_interview_research: bool = False
    # Force a fresh run even when a completed run already exists for this pair.
    force: bool = False


class RetryAgentRequest(BaseModel):
    job_id: str
    resume_id: str
    agent: str   # one of ALL_AGENTS


class AgentStatus(BaseModel):
    status: str = "pending"            # pending | running | complete | failed | skipped
    error_code: Optional[str] = None
    error_detail: Optional[str] = None
    updated_at: Optional[str] = None


class OrchestratorResponse(BaseModel):
    job_id: str
    resume_id: str
    status: str                                    # queued | running | complete | failed
    error: Optional[str] = None                    # legacy single error message
    error_code: Optional[str] = None               # llm_unavailable | rate_limited | invalid_response | ...
    run_id: Optional[str] = None
    agent_statuses: Dict[str, AgentStatus] = Field(default_factory=dict)

    # IDs of persisted records — populated when status == complete
    job_analysis_id: Optional[str] = None
    resume_analysis_id: Optional[str] = None
    resume_match_id: Optional[str] = None
    gap_analysis_id: Optional[str] = None
    resume_rewrite_id: Optional[str] = None
    interview_research_id: Optional[str] = None
    cover_letter_id: Optional[str] = None

    # Inline results — populated when status == complete (always now that background is mandatory)
    job_analysis: Optional[Any] = None
    resume_analysis: Optional[Any] = None
    resume_match: Optional[Any] = None
    gap_analysis: Optional[Any] = None
    resume_rewrite: Optional[Any] = None
    interview_research: Optional[Any] = None
    cover_letter: Optional[Any] = None
