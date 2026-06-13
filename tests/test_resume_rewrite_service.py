import json

from app.services.resume_rewrite_service import ResumeRewriteService
from app.llm.clients import MockLLMClient


class _FakeResume:
    def __init__(self, id: str, name: str, content_md: str):
        self.id = id
        self.name = name
        self.content_md = content_md


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
    def __init__(self, resume_obj, job_obj, gap_obj):
        self._resume = resume_obj
        self._job = job_obj
        self._gap = gap_obj
        self.added = None
        self.committed = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Resume":
            return _FakeQuery(self._resume)
        if name == "JobAnalysis":
            return _FakeQuery(self._job)
        if name == "GapAnalysis":
            return _FakeQuery(self._gap)
        return _FakeQuery(None)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


def test_resume_rewrite_parses_mock_response():
    resume = _FakeResume(id="r1", name="Alice", content_md="# Alice\nExperienced engineer")
    job = _FakeObj(id="ja1", result={"required_skills": ["Playwright"]})
    gap = _FakeObj(id="ga1", result={"critical_gaps": []})
    db = _FakeDB(resume, job, gap)

    mock_response = json.dumps({
        "variants": [
            {"variant": "A_ats", "content_md": "ATS content", "changes_summary": ["Added Playwright to skills"]},
            {"variant": "B_impact", "content_md": "Impact content", "changes_summary": ["Quantified impact"]},
            {"variant": "C_technical", "content_md": "Technical content", "changes_summary": ["Added technical highlights"]}
        ],
        "shared_changes": ["Normalized tech names"]
    })

    client = MockLLMClient(mock_response=mock_response)

    result = ResumeRewriteService.rewrite_resume(db=db, resume_id="r1", gap_analysis_id="ga1", job_analysis_id="ja1", llm_client=client)

    assert len(result.variants) == 3
    assert result.shared_changes == ["Normalized tech names"]
    assert db.added is not None
    assert db.committed is True
