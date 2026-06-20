import json

from app.services.resume_analyzer_service import ResumeAnalyzerService
from app.llm.clients import MockLLMClient


class _FakeResume:
    def __init__(self, id: str, name: str, content_md: str):
        self.id = id
        self.name = name
        self.content_md = content_md


class _FakeQuery:
    def __init__(self, resume):
        self._resume = resume

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._resume


class _FakeDB:
    def __init__(self, resume):
        self._resume = resume
        self.added = None
        self.committed = False

    def query(self, model):
        return _FakeQuery(self._resume)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


def test_resume_analyzer_parses_mock_response():
    resume = _FakeResume(id="r1", name="Alice", content_md="# Alice\nExperienced engineer")
    db = _FakeDB(resume)

    mock_response = json.dumps({
        "skills": ["Python", "Playwright"],
        "experience_years": 4,
        "domains": ["QA Automation"],
        "certifications": ["ISTQB"],
        "summary": "Experienced QA engineer with automation focus."
    })

    client = MockLLMClient(mock_response=mock_response)

    result = ResumeAnalyzerService.analyze_resume(db=db, resume_id="r1", llm_client=client)

    assert result.skills == ["Python", "Playwright"]
    assert result.experience_years == 4
    assert result.domains == ["QA Automation"]
    assert result.certifications == ["ISTQB"]
    assert result.summary.startswith("Experienced QA engineer")
    assert db.added is not None
    assert db.committed is True
