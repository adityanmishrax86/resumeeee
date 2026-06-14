import os
from typing import Optional

from app.llm.clients import MockLLMClient, NvidiaNIMClient

# Lazy singletons — one per agent type
_job_analyzer_agent = None
_resume_analyzer_agent = None
_resume_matcher_agent = None
_gap_analysis_agent = None
_resume_rewrite_agent = None
_interview_research_agent = None
_cover_letter_agent = None


def _get_provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "mock").lower()


def _create_llm_client(provider: Optional[str] = None):
    p = provider or _get_provider_name()
    if p in ("mock", "none"):
        return MockLLMClient()
    if p in ("nvidia", "nim", "nvidia-nim"):
        return NvidiaNIMClient()
    if p == "google":
        from app.llm.google_client import GoogleClient
        return GoogleClient()
    return MockLLMClient()


def get_job_analyzer_agent():
    """Return a singleton JobAnalyzerAgent instance (created lazily)."""
    global _job_analyzer_agent
    if _job_analyzer_agent is None:
        from app.agents.job_analyzer_agent import JobAnalyzerAgent
        _job_analyzer_agent = JobAnalyzerAgent(_create_llm_client())
    return _job_analyzer_agent


def get_resume_analyzer_agent():
    """Return a singleton ResumeAnalyzerAgent instance (created lazily)."""
    global _resume_analyzer_agent
    if _resume_analyzer_agent is None:
        from app.agents.resume_analyzer_agent import ResumeAnalyzerAgent
        _resume_analyzer_agent = ResumeAnalyzerAgent(_create_llm_client())
    return _resume_analyzer_agent


def get_resume_matcher_agent():
    """Return a singleton ResumeMatcherAgent instance (created lazily)."""
    global _resume_matcher_agent
    if _resume_matcher_agent is None:
        from app.agents.resume_matcher_agent import ResumeMatcherAgent
        _resume_matcher_agent = ResumeMatcherAgent(_create_llm_client())
    return _resume_matcher_agent


# Legacy alias kept for backward compatibility with existing api/resumes.py usage
def resume_matcher_agent():
    return get_resume_matcher_agent()


def get_gap_analysis_agent():
    """Return a singleton GapAnalysisAgent instance (created lazily)."""
    global _gap_analysis_agent
    if _gap_analysis_agent is None:
        from app.agents.gap_analysis_agent import GapAnalysisAgent
        _gap_analysis_agent = GapAnalysisAgent(_create_llm_client())
    return _gap_analysis_agent


def get_resume_rewrite_agent():
    """Return a singleton ResumeRewriteAgent instance (created lazily)."""
    global _resume_rewrite_agent
    if _resume_rewrite_agent is None:
        from app.agents.resume_rewrite_agent import ResumeRewriteAgent
        _resume_rewrite_agent = ResumeRewriteAgent(_create_llm_client())
    return _resume_rewrite_agent


def get_interview_research_agent():
    """Return a singleton InterviewResearchAgent instance (created lazily)."""
    global _interview_research_agent
    if _interview_research_agent is None:
        from app.agents.interview_research_agent import InterviewResearchAgent
        _interview_research_agent = InterviewResearchAgent(_create_llm_client())
    return _interview_research_agent


def get_cover_letter_agent():
    """Return a singleton CoverLetterAgent instance (created lazily)."""
    global _cover_letter_agent
    if _cover_letter_agent is None:
        from app.agents.cover_letter_agent import CoverLetterAgent
        _cover_letter_agent = CoverLetterAgent(_create_llm_client())
    return _cover_letter_agent


def reset_agent_singletons() -> None:
    """Drop cached agent instances so the next call rebuilds them with current env."""
    global _job_analyzer_agent, _resume_analyzer_agent, _resume_matcher_agent
    global _gap_analysis_agent, _resume_rewrite_agent, _interview_research_agent
    global _cover_letter_agent
    _job_analyzer_agent = None
    _resume_analyzer_agent = None
    _resume_matcher_agent = None
    _gap_analysis_agent = None
    _resume_rewrite_agent = None
    _interview_research_agent = None
    _cover_letter_agent = None


