import json

from app.services.interview_research_service import InterviewResearchService
from app.llm.clients import MockLLMClient


class _FakeObj:
    def __init__(self, id: str, result: dict):
        self.id = id
        self.result = result


class _FakeQuery:
    def __init__(self, obj):
        self._obj = obj

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._obj


class _FakeDB:
    def __init__(self, job_analysis_obj):
        self._job = job_analysis_obj
        self.added = None
        self.committed = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "JobAnalysis":
            return _FakeQuery(self._job)
        return _FakeQuery(None)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


def test_interview_research_parses_mock_response():
    job = _FakeObj(id="ja1", result={"required_skills": ["Playwright"], "role_title": "QA Engineer"})
    db = _FakeDB(job)

    mock_response = json.dumps({
        "role_specific_questions": [
            {"question": "How do you reduce Playwright test flakiness?", "category": "technical", "why_asked": "Assess async timing handling", "strong_answer_tips": ["Describe retries", "Use deterministic selectors"]}
        ],
        "company_snapshot": "Mid-size SaaS with focus on web apps.",
        "tech_stack_intel": ["Playwright", "Python", "GitHub Actions"],
        "hiring_signals": ["CI/CD emphasis"],
        "culture_notes": "Fast-paced, collaborative engineering culture.",
        "red_flags": ["Salary not disclosed"],
        "prep_checklist": ["Prepare a Playwright demo project"]
    })

    client = MockLLMClient(mock_response=mock_response)

    result = InterviewResearchService.research_interview(db=db, job_analysis_id="ja1", company_name="Acme", role_title="QA Engineer", llm_client=client)

    assert len(result.role_specific_questions) == 1
    assert "Playwright" in result.tech_stack_intel
    assert db.added is not None
    assert db.committed is True
