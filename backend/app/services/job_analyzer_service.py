import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.models import JobRawPayload
from app.models.analysis_models import JobAnalysis
from app.schemas.job_analysis_schema import JobAnalysisResult
from app.llm.clients import BaseLLMClient

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Try to extract the first JSON object from a string."""
    if not text:
        return ""

    # Quick heuristic: find the first { and the last } and try to parse.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end+1]
        return candidate

    # Fallback: try to find a JSON-like substring using regex
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        return match.group(1)

    return text


class JobAnalyzerService:
    @staticmethod
    def analyze_job(db: Session, job_id: str, llm_client: BaseLLMClient, analyzer_version: str = "v1") -> JobAnalysisResult:
        # Load raw payload
        raw = db.query(JobRawPayload).filter(JobRawPayload.job_id == job_id).first()

        if not raw:
            raise ValueError(f"Job with id {job_id} not found or has no raw payload")

        job_payload = raw.raw_payload or {}
        job_text = job_payload.get("jobDescription") or json.dumps(job_payload)

        # Load system prompt and user prompt template from prompts folder
        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "jd_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "jd_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            # Fallback to a short inline prompt (should not happen if prompts are managed)
            system_prompt = (
                "You are an expert technical recruiter and job description analyst.\n"
                "Extract structured factual information from this job description as JSON matching the schema:" 
                " required_skills, preferred_skills, programming_languages, tools, frameworks,"
                " experience_required, seniority_level, domain, ats_keywords, responsibilities, summary."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_text=job_text)
            except Exception:
                # If formatting fails, fallback to raw job text
                user_prompt = job_text
        else:
            user_prompt = job_text
        # Debug: log prompts being sent (truncated)
        logger.debug("JobAnalyzerService: job_id=%s job_text_len=%d", job_id, len(job_text))
        logger.debug("JobAnalyzerService: system_prompt_preview=%s", system_prompt[:3000])
        logger.debug("JobAnalyzerService: user_prompt_preview=%s", user_prompt[:3000])

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("JobAnalyzerService: raw LLM response (truncated)=%s", str(response_text)[:5000])
        except Exception:
            logger.exception("LLM client failed to generate analysis for job_id=%s", job_id)
            raise

        # Extract JSON and parse
        json_text = _extract_json(response_text)
        logger.debug("JobAnalyzerService: extracted json_text_preview=%s", json_text[:5000])

        try:
            data = json.loads(json_text)
        except Exception:
            logger.exception("Failed to parse JSON from extracted LLM response for job_id=%s", job_id)
            logger.debug("JobAnalyzerService: raw response preview=%s", str(response_text)[:5000])
            # Try to parse raw response as JSON directly
            try:
                data = json.loads(response_text)
            except Exception:
                logger.error("LLM returned invalid JSON for job analysis job_id=%s", job_id)
                raise ValueError("LLM returned invalid JSON for job analysis")

        # Validate against schema — this will fill defaults for missing fields
        analysis = JobAnalysisResult.parse_obj(data)

        # Persist validated (and normalized) result so missing keys become explicit
        entry = JobAnalysis(
            job_id=job_id,
            result=analysis.model_dump(),
            analyzer_version=analyzer_version
        )

        db.add(entry)
        db.commit()

        return analysis

    @staticmethod
    def prepare_prompts(db: Session, job_id: str) -> tuple[str, str]:
        """Load the job raw payload and return (system_prompt, user_prompt).

        This isolates prompt construction so streaming endpoints can reuse it.
        """
        raw = db.query(JobRawPayload).filter(JobRawPayload.job_id == job_id).first()

        if not raw:
            raise ValueError(f"Job with id {job_id} not found or has no raw payload")

        job_payload = raw.raw_payload or {}
        job_text = job_payload.get("jobDescription") or json.dumps(job_payload)

        base_dir = Path(__file__).resolve().parent.parent
        system_prompt_path = base_dir / "prompts" / "jd_analyzer" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "jd_analyzer" / "user_prompt_template.txt"

        if system_prompt_path.exists():
            system_prompt = system_prompt_path.read_text(encoding="utf-8")
        else:
            system_prompt = (
                "You are an expert technical recruiter and job description analyst.\n"
                "Extract structured factual information from this job description as JSON matching the schema:" 
                " required_skills, preferred_skills, programming_languages, tools, frameworks,"
                " experience_required, seniority_level, domain, ats_keywords, responsibilities, summary."
            )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(job_text=job_text)
            except Exception:
                user_prompt = job_text
        else:
            user_prompt = job_text

        return system_prompt, user_prompt
