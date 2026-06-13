import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.analysis_models import JobAnalysis, InterviewResearch
from app.schemas.interview_research_schema import InterviewResearchResult
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


class InterviewResearchService:
    @staticmethod
    def research_interview(db: Session, job_analysis_id: str, company_name: str | None, role_title: str | None, llm_client: BaseLLMClient, analyzer_version: str = "v1") -> InterviewResearchResult:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "interview_researcher" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert interview coach. Produce an InterviewResearchResult JSON object with role-specific questions, company snapshot, tech stack, hiring signals, culture notes, red flags, and a prep checklist."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), company_name=company_name or "", role_title=role_title or "")
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"

        logger.debug("InterviewResearchService: job_analysis_id=%s company=%s role=%s", job_analysis_id, company_name, role_title)

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("InterviewResearchService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate interview research for job_analysis_id=%s", job_analysis_id)
            raise

        json_text = _extract_json(response_text)

        try:
            data = json.loads(json_text)
        except Exception:
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for interview research job_analysis_id=%s", job_analysis_id)
                raise ValueError("LLM returned invalid JSON for interview research")

        analysis = InterviewResearchResult.parse_obj(data)

        InterviewResearchService.persist_result(db=db, job_analysis_id=job_analysis_id, result=analysis)

        return analysis

    @staticmethod
    def persist_result(db: Session, job_analysis_id: str, result: "InterviewResearchResult") -> None:
        """Persist an already-validated InterviewResearchResult to the DB.

        Separated so the pydantic-ai tool agent can reuse it without going
        through the full LLM-generate-then-parse flow.
        """
        entry = InterviewResearch(
            job_analysis_id=job_analysis_id,
            result=result.model_dump(),
        )
        db.add(entry)
        db.commit()

    @staticmethod
    def prepare_prompts(db: Session, job_analysis_id: str, company_name: str | None, role_title: str | None) -> tuple[str, str]:
        ja = db.query(JobAnalysis).filter(JobAnalysis.id == job_analysis_id).first()
        if not ja:
            raise ValueError(f"JobAnalysis with id {job_analysis_id} not found")

        job_json = ja.result if isinstance(ja.result, dict) else {}

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "interview_researcher" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "interview_researcher" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert interview coach. Produce an InterviewResearchResult JSON object with role-specific questions, company snapshot, tech stack, hiring signals, culture notes, red flags, and a prep checklist."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_analysis=json.dumps(job_json), company_name=company_name or "", role_title=role_title or "")
            except Exception:
                user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"
        else:
            user_prompt = f"job_analysis: {json.dumps(job_json)}\ncompany_name: {company_name}\nrole_title: {role_title}"

        return system_prompt, user_prompt
