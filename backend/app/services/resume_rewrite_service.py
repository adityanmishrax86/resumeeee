import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import Resume
from app.models.analysis_models import JobAnalysis, GapAnalysis, ResumeRewrite
from app.schemas.resume_rewrite_schema import ResumeRewriteResult
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


class ResumeRewriteService:
    @staticmethod
    def rewrite_resume(db: Session, resume_id: str, gap_analysis_id: str | None, job_analysis_id: str | None, llm_client: BaseLLMClient, analyzer_version: str = "v1") -> ResumeRewriteResult:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            raise ValueError(f"Resume with id {resume_id} not found")

        job_json = {}
        gap_json = {}

        if job_analysis_id:
            ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
            if not ja:
                raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")
            job_json = ja.result if isinstance(ja.result, dict) else {}

        if gap_analysis_id:
            ga = db.query(GapAnalysis).filter(GapAnalysis.id == gap_analysis_id).first()
            if not ga:
                raise ValueError(f"GapAnalysis with id {gap_analysis_id} not found")
            gap_json = ga.result if isinstance(ga.result, dict) else {}

        resume_text = getattr(resume, "content_md", None) or getattr(resume, "content", "") or ""

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "resume_rewriter" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "resume_rewriter" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert resume writer and career strategist. Produce three resume variants (ATS, Impact, Technical) as JSON matching the ResumeRewriteResult schema."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(resume_md=resume_text, job_analysis=json.dumps(job_json), gap_analysis=json.dumps(gap_json))
            except Exception:
                user_prompt = f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\ngap_analysis: {json.dumps(gap_json)}"
        else:
            user_prompt = f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\ngap_analysis: {json.dumps(gap_json)}"

        logger.debug("ResumeRewriteService: resume_id=%s", resume_id)

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("ResumeRewriteService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate resume rewrites for resume_id=%s", resume_id)
            raise

        json_text = _extract_json(response_text)

        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for resume rewrite resume_id=%s", resume_id)
                raise ValueError("LLM returned invalid JSON for resume rewrite")

        analysis = ResumeRewriteResult.parse_obj(data)

        entry = ResumeRewrite(
            resume_id=resume_id,
            gap_analysis_id=gap_analysis_id,
            job_analysis_id=job_analysis_id,
            result=analysis.model_dump(),
        )

        db.add(entry)
        db.commit()

        return analysis

    @staticmethod
    def prepare_prompts(db: Session, resume_id: str, gap_analysis_id: str | None, job_analysis_id: str | None) -> tuple[str, str]:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            raise ValueError(f"Resume with id {resume_id} not found")

        job_json = {}
        gap_json = {}

        if job_analysis_id:
            ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
            if not ja:
                raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")
            job_json = ja.result if isinstance(ja.result, dict) else {}

        if gap_analysis_id:
            ga = db.query(GapAnalysis).filter(GapAnalysis.id == gap_analysis_id).first()
            if not ga:
                raise ValueError(f"GapAnalysis with id {gap_analysis_id} not found")
            gap_json = ga.result if isinstance(ga.result, dict) else {}

        resume_text = getattr(resume, "content_md", None) or getattr(resume, "content", "") or ""

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "resume_rewriter" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "resume_rewriter" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert resume writer and career strategist. Produce three resume variants (ATS, Impact, Technical) as JSON matching the ResumeRewriteResult schema."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(resume_md=resume_text, job_analysis=json.dumps(job_json), gap_analysis=json.dumps(gap_json))
            except Exception:
                user_prompt = f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\ngap_analysis: {json.dumps(gap_json)}"
        else:
            user_prompt = f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\ngap_analysis: {json.dumps(gap_json)}"

        return system_prompt, user_prompt
