import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import Resume
from app.models.analysis_models import ResumeAnalysis
from app.schemas.resume_analysis_schema import ResumeAnalysisResult
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


class ResumeAnalyzerService:
    @staticmethod
    def analyze_resume(db: Session, resume_id: str, llm_client: BaseLLMClient, analyzer_version: str = "v1") -> ResumeAnalysisResult:
        # Load resume content
        resume = db.query(Resume).filter(Resume.id == resume_id).first()

        if not resume:
            raise ValueError(f"Resume with id {resume_id} not found")

        resume_text = getattr(resume, "content_md", None) or getattr(resume, "content", "") or ""

        # Load prompts
        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "resume_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "resume_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert resume analyst. Extract structured information from the resume"
                " into JSON with fields: skills, experience_years, domains, certifications, summary."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(resume_md=resume_text)
            except Exception:
                user_prompt = resume_text
        else:
            user_prompt = resume_text

        logger.debug("ResumeAnalyzerService: resume_id=%s content_len=%d", resume_id, len(resume_text or ""))

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("ResumeAnalyzerService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate resume analysis for resume_id=%s", resume_id)
            raise

        json_text = _extract_json(response_text)

        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for resume analysis resume_id=%s", resume_id)
                raise ValueError("LLM returned invalid JSON for resume analysis")

        analysis = ResumeAnalysisResult.parse_obj(data)

        entry = ResumeAnalysis(
            resume_id=resume_id,
            result=analysis.model_dump(),
            analyzer_version=analyzer_version,
        )

        db.add(entry)
        db.commit()

        return analysis

    @staticmethod
    def prepare_prompts(db: Session, resume_id: str) -> tuple[str, str]:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()

        if not resume:
            raise ValueError(f"Resume with id {resume_id} not found")

        resume_text = getattr(resume, "content_md", None) or getattr(resume, "content", "") or ""

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "resume_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "resume_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert resume analyst. Extract structured information from the resume"
                " into JSON with fields: skills, experience_years, domains, certifications, summary."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(resume_md=resume_text)
            except Exception:
                user_prompt = resume_text
        else:
            user_prompt = resume_text

        return system_prompt, user_prompt
