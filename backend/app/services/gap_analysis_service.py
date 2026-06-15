import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.analysis_models import JobAnalysis, ResumeMatch, GapAnalysis
from app.schemas.gap_analysis_schema import GapAnalysisResult
from app.llm.clients import BaseLLMClient

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    if not text:
        return ""

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end+1]

    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        return match.group(1)

    return text


class GapAnalysisService:
    @staticmethod
    def analyze_gaps(db: Session, job_analysis_id: str, resume_match_id: str, llm_client: BaseLLMClient, analyzer_version: str = "v1") -> GapAnalysisResult:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        rm = db.query(ResumeMatch).filter(ResumeMatch.id == resume_match_id).first()
        if not rm:
            raise ValueError(f"ResumeMatch with id {resume_match_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}
        resume_match_json = rm.result if isinstance(rm.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "gap_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "gap_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are a senior career coach. Given job_analysis and resume_match JSON objects,"
                " produce a GapAnalysisResult JSON object describing critical/moderate/minor gaps, quick wins, resume strategy, and cover letter angle."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), resume_match=json.dumps(resume_match_json))
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\nresume_match: {json.dumps(resume_match_json)}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\nresume_match: {json.dumps(resume_match_json)}"

        logger.debug("GapAnalysisService: job_analysis_id=%s resume_match_id=%s", job_analysis_id, resume_match_id)

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("GapAnalysisService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate gap analysis for job_analysis_id=%s resume_match_id=%s", job_analysis_id, resume_match_id)
            raise

        json_text = _extract_json(response_text)

        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for gap analysis job_analysis_id=%s resume_match_id=%s", job_analysis_id, resume_match_id)
                raise ValueError("LLM returned invalid JSON for gap analysis")

        analysis = GapAnalysisResult.parse_obj(data)

        entry = GapAnalysis(
            job_analysis_id=job_analysis_id,
            resume_match_id=resume_match_id,
            result=analysis.model_dump(),
        )

        db.add(entry)
        db.commit()

        return analysis

    @staticmethod
    def prepare_prompts(db: Session, job_analysis_id: str, resume_match_id: str) -> tuple[str, str]:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        rm = db.query(ResumeMatch).filter(ResumeMatch.id == resume_match_id).first()
        if not rm:
            raise ValueError(f"ResumeMatch with id {resume_match_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}
        resume_match_json = rm.result if isinstance(rm.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "gap_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "gap_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are a senior career coach. Given job_analysis and resume_match JSON objects,"
                " produce a GapAnalysisResult JSON object describing critical/moderate/minor gaps, quick wins, resume strategy, and cover letter angle."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), resume_match=json.dumps(resume_match_json))
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\nresume_match: {json.dumps(resume_match_json)}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\nresume_match: {json.dumps(resume_match_json)}"

        return system_prompt, user_prompt
