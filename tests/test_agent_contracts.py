import json
from types import SimpleNamespace

import pytest

from app.models.analysis_models import JobAnalysis, ResumeAnalysis
from app.models.models import Resume
from app.schemas.cover_letter_schema import CoverLetterResult
from app.schemas.gap_analysis_schema import GapAnalysisResult
from app.schemas.interview_research_schema import InterviewQuestion, InterviewResearchResult
from app.schemas.resume_rewrite_schema import ResumeRewriteResult
from app.services.interview_research_service import InterviewResearchService
from app.services.resume_service import ResumeService


class _Query:
    def __init__(self, row):
        self.row = row

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.row


class _DB:
    def __init__(self, rows):
        self.rows = rows

    def query(self, model):
        return _Query(self.rows[model])


def test_resume_match_scores_and_partitions_are_derived_from_source_data():
    resume = SimpleNamespace(
        id="resume-1",
        content_md="Backend engineer using Python, JavaScript, Docker and continuous integration.",
    )
    job = SimpleNamespace(
        id="job-analysis-1",
        result={
            "required_skills": ["Python", "Java", "JavaScript"],
            "preferred_skills": ["Docker", "Kubernetes"],
            "ats_keywords": ["Python", "Kubernetes"],
            "experience_required": "5+ years",
            "domain": "Backend Python",
        },
    )
    resume_analysis = SimpleNamespace(
        result={"experience_years": 4, "domains": ["Backend Python"]}
    )
    db = _DB({Resume: resume, JobAnalysis: job, ResumeAnalysis: resume_analysis})
    draft = json.dumps({
        "strengths": ["Used Python in backend engineering."],
        "improvement_suggestions": ["Address the Kubernetes gap honestly."],
        "match_summary": "Python and backend experience align with the role; Kubernetes is not evidenced.",
    })

    result = ResumeService.match_resume(db, draft, "resume-1", "job-analysis-1")

    assert result.matched_required_skills == ["Python", "JavaScript"]
    assert result.missing_required_skills == ["Java"]
    assert result.matched_preferred_skills == ["Docker"]
    assert result.missing_preferred_skills == ["Kubernetes"]
    assert result.ats_keyword_coverage == ["Python"]
    assert result.ats_keyword_gaps == ["Kubernetes"]
    assert result.skills_match_score == 67
    assert result.experience_match_score == 72
    assert result.domain_score == 95
    assert result.overall_score == 74


def test_cover_letter_accepts_legacy_field_names_but_emits_canonical_shape():
    payload = {
        "variants": [
            {"variant": name, "content": "Letter", "changes_summary": ["Grounded in Python work"]}
            for name in ("professional", "story", "startup")
        ]
    }

    result = CoverLetterResult.model_validate(payload)

    assert [item.style for item in result.variants] == ["professional", "story", "startup"]
    assert set(result.model_dump()["variants"][0]) == {"style", "content_md", "why_choose_me"}


def test_resume_rewrite_rejects_duplicate_variant_labels():
    payload = {"variants": [
        {"variant": "A_ats", "content_md": "A", "changes_summary": []},
        {"variant": "A_ats", "content_md": "B", "changes_summary": []},
        {"variant": "C_technical", "content_md": "C", "changes_summary": []},
    ]}
    with pytest.raises(ValueError):
        ResumeRewriteResult.model_validate(payload)


def test_gap_analysis_rejects_wrong_severity_bucket():
    with pytest.raises(ValueError):
        GapAnalysisResult.model_validate({
            "critical_gaps": [{
                "skill": "Kubernetes", "severity": "moderate",
                "reason": "Not listed", "bridge_suggestion": "Address directly",
            }]
        })


def test_interview_research_contract_checks_question_and_section_counts():
    categories = ["coding", "scenario", "analytical", "behavioural", "technical"]
    questions = [
        InterviewQuestion(
            question=f"Question {index}",
            category=categories[index % len(categories)],
            strong_answer_tips=["One", "Two", "Three"],
        )
        for index in range(25)
    ]
    result = InterviewResearchResult(
        role_specific_questions=questions,
        hiring_signals=["Signal"] * 5,
        red_flags=["Clarify scope"] * 4,
        prep_checklist=["Prepare"] * 10,
    )

    InterviewResearchService._validate_generated_result(result)

    result.role_specific_questions.pop()
    with pytest.raises(ValueError, match="exactly 25"):
        InterviewResearchService._validate_generated_result(result)
