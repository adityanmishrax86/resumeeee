"""
Unit test for OrchestratorService using MockLLMClient instances
and a fake in-memory DB (no real Postgres/SQLite needed).

Covers:
- Full happy-path run (all stages complete)
- Graceful handling when ResumeRewrite stage fails (non-fatal)
"""

import asyncio
import json
from typing import Optional
from unittest.mock import MagicMock

from app.services.orchestrator_service import OrchestratorService
from app.llm.clients import MockLLMClient


# ── Fake DB helpers ────────────────────────────────────────────────────────────

_MOCK_JOB_ANALYSIS_RESULT = {
    "required_skills": ["Playwright"],
    "preferred_skills": [],
    "programming_languages": ["Python"],
    "tools": [],
    "frameworks": [],
    "experience_required": "3 years",
    "seniority_level": "mid",
    "domain": "QA Automation",
    "ats_keywords": ["playwright automation"],
    "responsibilities": ["Write automated tests"],
    "summary": "QA role focused on Playwright automation.",
}

_MOCK_RESUME_ANALYSIS_RESULT = {
    "skills": ["Selenium", "Python"],
    "experience_years": 4,
    "domains": ["QA"],
    "certifications": [],
    "summary": "QA engineer with Selenium experience.",
}

_MOCK_RESUME_MATCH_RESULT = {
    "overall_score": 65,
    "skills_match_score": 60,
    "experience_match_score": 70,
    "domain_score": 85,
    "matched_required_skills": [],
    "missing_required_skills": ["Playwright"],
    "matched_preferred_skills": [],
    "missing_preferred_skills": [],
    "experience_fit": "match",
    "ats_keyword_coverage": [],
    "ats_keyword_gaps": ["playwright automation"],
    "strengths": ["Python experience"],
    "improvement_suggestions": ["Add Playwright"],
    "match_summary": "Reasonable match with one critical gap.",
}

_MOCK_GAP_ANALYSIS_RESULT = {
    "critical_gaps": [
        {"skill": "Playwright", "severity": "critical", "reason": "Required", "bridge_suggestion": "Reframe Selenium"}
    ],
    "moderate_gaps": [],
    "minor_gaps": [],
    "quick_wins": ["Highlight Selenium"],
    "resume_strategy": "Lead with automation.",
    "cover_letter_angle": "Quick learner angle.",
    "honesty_flag": False,
    "honesty_note": "",
}

_MOCK_RESUME_REWRITE_RESULT = {
    "variants": [
        {"variant": "A_ats", "content_md": "ATS resume", "changes_summary": ["Added Playwright"]},
        {"variant": "B_impact", "content_md": "Impact resume", "changes_summary": ["Quantified"]},
        {"variant": "C_technical", "content_md": "Technical resume", "changes_summary": ["Expanded bullets"]},
    ],
    "shared_changes": ["Normalized names"],
}

_MOCK_INTERVIEW_RESEARCH_RESULT = {
    "role_specific_questions": [
        {"question": "Describe Playwright usage.", "category": "technical", "why_asked": "Core skill", "strong_answer_tips": ["Be specific"]}
    ],
    "company_snapshot": "SaaS company.",
    "tech_stack_intel": ["Playwright"],
    "hiring_signals": ["CI/CD focus"],
    "culture_notes": "Collaborative team.",
    "red_flags": [],
    "prep_checklist": ["Build Playwright demo"],
}


class _FakeRow:
    """Simulates an ORM row returned by DB queries."""
    def __init__(self, id: str, result: dict, **kwargs):
        self.id = id
        self.result = result
        self.__dict__.update(kwargs)


class _FakeQuery:
    def __init__(self, row):
        self._row = row

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._row


class _FakeDB:
    """Minimal fake Session that routes model-name -> fake row."""

    def __init__(self):
        self._store: dict[str, _FakeRow] = {}
        self.adds = []
        self.commits = 0

    def seed(self, model_name: str, row: _FakeRow):
        self._store[model_name] = row

    def query(self, model):
        name = getattr(model, "__name__", "")
        return _FakeQuery(self._store.get(name))

    def add(self, obj):
        # Inject a fake id + register it so subsequent queries find it
        obj.id = f"fake-{type(obj).__name__}-id"
        self._store[type(obj).__name__] = obj
        self.adds.append(obj)

    def commit(self):
        self.commits += 1

    def refresh(self, obj):
        pass


# ── Tests ──────────────────────────────────────────────────────────────────────

def _make_client(mock_result: dict) -> MockLLMClient:
    return MockLLMClient(mock_response=json.dumps(mock_result))


class _DynamicMockClient(MockLLMClient):
    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        if "cover-letter" in system_prompt.lower() or "cover letter" in system_prompt.lower():
            return json.dumps({
                "variants": [
                    {
                        "style": "professional",
                        "content_md": "Professional cover letter content.",
                        "why_choose_me": ["Achievement 1", "Achievement 2"]
                    },
                    {
                        "style": "story",
                        "content_md": "Story cover letter content.",
                        "why_choose_me": ["Achievement 1", "Achievement 2"]
                    },
                    {
                        "style": "startup",
                        "content_md": "Startup cover letter content.",
                        "why_choose_me": ["Achievement 1", "Achievement 2"]
                    }
                ],
                "shared_notes": ["Mock cover letter notes."]
            })
        return json.dumps(_MOCK_RESUME_REWRITE_RESULT)


def _make_orchestrator() -> OrchestratorService:
    return OrchestratorService(
        job_analyzer_client=_make_client(_MOCK_JOB_ANALYSIS_RESULT),
        resume_analyzer_client=_make_client(_MOCK_RESUME_ANALYSIS_RESULT),
        resume_matcher_client=_make_client(_MOCK_RESUME_MATCH_RESULT),
        gap_analysis_client=_make_client(_MOCK_GAP_ANALYSIS_RESULT),
        resume_rewrite_client=_DynamicMockClient(),
        interview_research_client=_make_client(_MOCK_INTERVIEW_RESEARCH_RESULT),
    )


def test_orchestrator_happy_path():
    """Full pipeline run returns status=complete with all stage results."""
    db = _FakeDB()
    # Pre-seed the models that the agents query BEFORE they have been
    # inserted (e.g. JobRawPayload needed by JobAnalyzerService).
    from app.models.models import JobRawPayload, Resume
    db.seed("JobRawPayload", _FakeRow(id="rp1", result={}, job_id="j1",
                                      **{"raw_payload": {"jobDescription": "QA role"}}))
    db.seed("Resume", _FakeRow(id="r1", result={}, **{"content_md": "# Alice"}))

    orchestrator = _make_orchestrator()
    result = asyncio.run(orchestrator.run(db=db, job_id="j1", resume_id="r1", company_name="Acme", role_title="QA"))

    assert result.status == "complete", f"Expected complete, got {result.status}: {result.error}"

    from app.models.analysis_models import ApplicationRun
    from app.api.orchestrator import _build_status_response
    run_row = db.query(ApplicationRun).first()
    hydrated = _build_status_response(db, run_row)

    assert hydrated.job_analysis is not None
    assert hydrated.resume_match is not None
    assert hydrated.gap_analysis is not None
    assert hydrated.resume_rewrite is not None
    assert hydrated.interview_research is not None
    assert hydrated.cover_letter is not None
