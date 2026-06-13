import json

from app.services.gap_analysis_service import GapAnalysisService
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
    def __init__(self, job_analysis_obj, resume_match_obj):
        self._job = job_analysis_obj
        self._resume_match = resume_match_obj
        self.added = None
        self.committed = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "JobAnalysis":
            return _FakeQuery(self._job)
        if name == "ResumeMatch":
            return _FakeQuery(self._resume_match)
        return _FakeQuery(None)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


def test_gap_analysis_parses_mock_response():
    job_analysis = _FakeObj(id="ja1", result={"required_skills": ["Playwright"]})
    resume_match = _FakeObj(id="rm1", result={"overall_score": 50})
    db = _FakeDB(job_analysis, resume_match)

    mock_response = json.dumps({
        "critical_gaps": [
            {"skill": "Playwright", "severity": "critical", "reason": "Required by JD", "bridge_suggestion": "Reframe Selenium experience"}
        ],
        "moderate_gaps": [],
        "minor_gaps": [],
        "quick_wins": ["Highlight Selenium->Playwright work"],
        "resume_strategy": "Lead with automation impact.",
        "cover_letter_angle": "Show quick learning and relevant experience.",
        "honesty_flag": False,
        "honesty_note": ""
    })

    client = MockLLMClient(mock_response=mock_response)

    result = GapAnalysisService.analyze_gaps(db=db, job_analysis_id="ja1", resume_match_id="rm1", llm_client=client)

    assert len(result.critical_gaps) == 1
    assert result.critical_gaps[0].skill == "Playwright"
    assert "Highlight Selenium" in result.quick_wins[0]
    assert db.added is not None
    assert db.committed is True
