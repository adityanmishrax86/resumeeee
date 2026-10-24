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


def _valid_questions(first=None):
    categories = (
        ["scenario"] * 4
        + ["analytical"] * 4
        + ["behavioural"] * 4
        + ["technical"] * 4
        + ["coding"] * 9
    )
    questions = []
    if first:
        questions.append(first)
    for index, category in enumerate(categories, start=1):
        if len(questions) >= 25:
            break
        questions.append({
            "question": f"How would you apply Playwright in distinct scenario {index}?",
            "category": category,
            "why_asked": "Assess role-relevant reasoning.",
            "strong_answer_tips": ["Use a concrete example", "Explain your reasoning", "Discuss trade-offs"],
        })
    while len(questions) < 25:
        index = len(questions) + 1
        questions.append({
            "question": f"How would you approach distinct Playwright task {index}?",
            "category": "technical",
            "why_asked": "Assess role-relevant reasoning.",
            "strong_answer_tips": ["Use a concrete example", "Explain your reasoning", "Discuss trade-offs"],
        })
    return questions


def test_interview_research_parses_mock_response():
    job = _FakeObj(id="ja1", result={"required_skills": ["Playwright"], "role_title": "QA Engineer"})
    db = _FakeDB(job)

    mock_response = json.dumps({
        "role_specific_questions": _valid_questions({"question": "How do you reduce Playwright test flakiness?", "category": "technical", "why_asked": "Assess async timing handling", "strong_answer_tips": ["Describe retries", "Use deterministic selectors", "Explain how you verify stability"]}),
        "company_snapshot": "Mid-size SaaS with focus on web apps.",
        "tech_stack_intel": ["Playwright", "Python", "GitHub Actions"],
        "hiring_signals": ["CI/CD emphasis"],
        "culture_notes": "Fast-paced, collaborative engineering culture.",
        "red_flags": ["Salary not disclosed"],
        "prep_checklist": ["Prepare a Playwright demo project"]
    })

    client = MockLLMClient(mock_response=mock_response)

    result = InterviewResearchService.research_interview(db=db, job_analysis_id="ja1", company_name="Acme", role_title="QA Engineer", llm_client=client)

    assert len(result.role_specific_questions) == 25
    assert result.role_specific_questions[0].question == "How do you reduce Playwright test flakiness?"
    assert "Playwright" in result.tech_stack_intel
    assert db.added is not None
    assert db.committed is True


def test_interview_research_retries_when_model_returns_too_few_questions():
    job = _FakeObj(id="ja1", result={"required_skills": ["Playwright"], "role_title": "QA Engineer"})
    db = _FakeDB(job)

    def payload(questions):
        return json.dumps({
            "role_specific_questions": questions,
            "company_snapshot": "Role-focused snapshot.",
            "tech_stack_intel": ["Playwright"],
            "hiring_signals": ["Playwright depth"],
            "culture_notes": "Cross-functional collaboration is mentioned.",
            "red_flags": ["Clarify team ownership"],
            "prep_checklist": ["Review the stated testing workflow"],
        })

    class SequenceClient:
        def __init__(self):
            self.responses = [payload(_valid_questions()[:21]), payload(_valid_questions())]

        def generate(self, system_prompt, user_prompt):
            return self.responses.pop(0)

    client = SequenceClient()
    result = InterviewResearchService.research_interview(
        db=db,
        job_analysis_id="ja1",
        company_name="Acme",
        role_title="QA Engineer",
        llm_client=client,
    )

    assert len(result.role_specific_questions) == 25
    assert not client.responses
    assert db.committed is True


def test_research_interview_backfills_empty_sections():
    """When the LLM returns empty hiring_signals/red_flags/prep_checklist,
    the service must synthesise JD-grounded fallbacks so the UI never shows
    empty 'Things to Watch Out For' / 'Prep Checklist' sections."""
    job = _FakeObj(
        id="ja1",
        result={
            "required_skills": ["Python", "LLM testing", "CI/CD pipelines"],
            "preferred_skills": ["MLOps workflows"],
            "tools": ["FAISS", "Pinecone", "Docker", "Kubernetes", "Terraform", "AWS Bedrock"],
            "frameworks": ["LangChain", "LlamaIndex"],
            "responsibilities": [
                "Integrate testing into CI/CD pipelines with DevOps/MLOps teams",
                "Ensure performance, cost optimization, and scalability of AI solutions",
            ],
            "seniority_level": "Senior/Architect",
            "experience_required": "8-12 years",
            "domain": "QA Automation / Gen AI",
            "programming_languages": ["Python"],
            "role_title": "Gen AI Automation Testing",
        },
    )
    db = _FakeDB(job)

    mock_response = json.dumps({
        "role_specific_questions": _valid_questions({"question": "Q1", "category": "coding", "why_asked": "x", "strong_answer_tips": ["a", "b", "c"]}),
        "company_snapshot": "Snapshot.",
        "tech_stack_intel": ["Python"],
        "hiring_signals": [],
        "culture_notes": "Notes.",
        "red_flags": [],
        "prep_checklist": [],
    })
    client = MockLLMClient(mock_response=mock_response)

    result = InterviewResearchService.research_interview(
        db=db, job_analysis_id="ja1", company_name="Cognizant",
        role_title="Gen AI Automation Testing", llm_client=client,
    )

    assert len(result.hiring_signals) >= 5, "must backfill hiring_signals from JD"
    assert len(result.red_flags) >= 4, "must backfill red_flags from JD"
    assert len(result.prep_checklist) >= 10, "must backfill prep_checklist from JD"
    # Spot-check that backfill uses JD content rather than canned text.
    combined = " ".join(result.hiring_signals + result.red_flags + result.prep_checklist).lower()
    assert "python" in combined or "ci/cd" in combined or "mlops" in combined


def test_research_interview_preserves_nonempty_sections():
    """Backfill must NOT overwrite sections the LLM already populated."""
    job = _FakeObj(id="ja1", result={"required_skills": ["Python"], "role_title": "QA"})
    db = _FakeDB(job)

    mock_response = json.dumps({
        "role_specific_questions": _valid_questions({"question": "Q1", "category": "coding", "why_asked": "x", "strong_answer_tips": ["a", "b", "c"]}),
        "company_snapshot": "Snapshot.",
        "tech_stack_intel": ["Python"],
        "hiring_signals": ["Only one signal"],
        "culture_notes": "Notes.",
        "red_flags": ["Only one flag"],
        "prep_checklist": ["Only one prep item"],
    })
    client = MockLLMClient(mock_response=mock_response)

    result = InterviewResearchService.research_interview(
        db=db, job_analysis_id="ja1", company_name="Acme",
        role_title="QA", llm_client=client,
    )

    assert result.hiring_signals[0] == "Only one signal"
    assert result.red_flags[0] == "Only one flag"
    assert result.prep_checklist[0] == "Only one prep item"
    assert len(result.hiring_signals) >= 5
    assert len(result.red_flags) >= 4
    assert len(result.prep_checklist) >= 10


# ── Tests for new methods (save_user_items / generate_profile_questions /
#    stream_detailed_answer) ────────────────────────────────────────────────

import asyncio
import os

from app.models.models import Resume
from app.models.analysis_models import InterviewResearch


class _FakeResume:
    def __init__(self, id: str, content_md: str):
        self.id = id
        self.content_md = content_md


class _FakeInterviewResearchRow:
    def __init__(self, job_analysis_id: str, result: dict):
        self.job_analysis_id = job_analysis_id
        self.result = result


class _FakeOrderedQuery:
    """Query stub that supports filter().order_by().first() chaining."""

    def __init__(self, obj):
        self._obj = obj

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def first(self):
        return self._obj


class _FakeDBMulti:
    """Fake DB that resolves multiple model types by name."""

    def __init__(self, *, job=None, resume=None, interview_row=None):
        self._job = job
        self._resume = resume
        self._interview_row = interview_row
        self.added = None
        self.committed = False

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "JobAnalysis":
            return _FakeQuery(self._job)
        if name == "Resume":
            return _FakeQuery(self._resume)
        if name == "InterviewResearch":
            return _FakeOrderedQuery(self._interview_row)
        return _FakeQuery(None)

    def add(self, obj):
        self.added = obj

    def commit(self):
        self.committed = True


def _make_existing_research_row(job_analysis_id: str = "ja1") -> _FakeInterviewResearchRow:
    return _FakeInterviewResearchRow(
        job_analysis_id=job_analysis_id,
        result={
            "role_specific_questions": [
                {
                    "question": "How do you reduce Playwright test flakiness?",
                    "category": "technical",
                    "why_asked": "Assess async timing handling",
                    "strong_answer_tips": ["Describe retries"],
                }
            ],
            "behavioral_questions": [],
            "technical_questions": [],
            "company_snapshot": "snapshot",
            "tech_stack_intel": ["Playwright"],
            "hiring_signals": [],
            "culture_notes": "",
            "red_flags": [],
            "prep_checklist": [],
        },
    )


def test_save_user_items_prepends_and_dedupes():
    row = _make_existing_research_row()
    db = _FakeDBMulti(interview_row=row)

    result = InterviewResearchService.save_user_items(
        db=db,
        job_analysis_id="ja1",
        user_questions=[
            {"question": "What is your favorite test pattern?", "category": "behavioural"},
            # Duplicate of existing (case/whitespace insensitive) — should be dropped.
            {"question": "  how do you reduce playwright test flakiness?  "},
        ],
    )

    questions = result.role_specific_questions
    assert len(questions) == 2, "duplicate must be dropped"
    assert questions[0].question == "What is your favorite test pattern?"
    assert questions[0].source == "user", "default source must be 'user'"
    assert questions[1].question == "How do you reduce Playwright test flakiness?"
    assert db.committed is True


def test_save_user_items_sets_detailed_answer():
    row = _make_existing_research_row()
    db = _FakeDBMulti(interview_row=row)

    result = InterviewResearchService.save_user_items(
        db=db,
        job_analysis_id="ja1",
        updated_answers=[
            {
                "question": "How do you reduce Playwright test flakiness?",
                "detailed_answer": "Use deterministic selectors and proper waits.",
            },
            # No match — should be ignored, not raise.
            {"question": "Nonexistent question", "detailed_answer": "ignored"},
        ],
    )

    matched = result.role_specific_questions[0]
    assert matched.detailed_answer == "Use deterministic selectors and proper waits."


def test_generate_profile_questions_returns_n_items():
    resume = _FakeResume(
        id="r1",
        content_md="# John Doe\n\nQA engineer with 5 years of Selenium experience.",
    )
    job = _FakeObj(id="ja1", result={"required_skills": ["Playwright"], "role_title": "QA"})
    db = _FakeDBMulti(job=job, resume=resume)

    mock_response = json.dumps({
        "questions": [
            {
                "question": "Walk me through your Selenium-to-Playwright migration.",
                "category": "scenario",
                "why_asked": "Probe migration depth",
                "strong_answer_tips": ["Cite a specific migration", "Explain your own contribution", "Describe the outcome"],
            },
            {
                "question": "Describe a flaky test you debugged.",
                "category": "behavioural",
                "why_asked": "Assess debugging rigor",
                "strong_answer_tips": ["Set the situation", "Describe your actions", "Share the result"],
            },
        ]
    })
    client = MockLLMClient(mock_response=mock_response)

    out = asyncio.run(
        InterviewResearchService.generate_profile_questions(
            db=db,
            resume_id="r1",
            job_analysis_id="ja1",
            count=2,
            llm_client=client,
            company_name="Acme",
            role_title="QA Engineer",
        )
    )

    assert len(out) == 2
    assert all(q.source == "profile" for q in out)
    assert out[0].question.startswith("Walk me through")


def test_stream_detailed_answer_yields_tokens(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    job = _FakeObj(id="ja1", result={"role_title": "QA"})
    db = _FakeDBMulti(job=job)

    async def collect():
        chunks = []
        async for chunk in InterviewResearchService.stream_detailed_answer(
            db=db,
            job_analysis_id="ja1",
            question="Tell me about a hard bug you fixed.",
            category="behavioural",
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())

    assert len(chunks) > 0, "mock stream must yield at least one chunk"
    combined = "".join(chunks)
    assert combined.strip(), "concatenated stream must be non-empty"

