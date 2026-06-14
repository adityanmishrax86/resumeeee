"""CoverLetterService — generates 3-variant cover letters."""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMInvalidResponse
from app.models.models import Resume
from app.models.analysis_models import (
    JobAnalysis,
    GapAnalysis,
    CoverLetter,
)
from app.schemas.cover_letter_schema import CoverLetterResult

logger = logging.getLogger(__name__)

REQUIRED_STYLES = ("professional", "story", "startup")


_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)


def _extract_json(text: str) -> str:
    """Best-effort recovery of a JSON object from an LLM response.

    Handles three common LLM violations of "return only JSON":
      1. Markdown fences:  ```json\n{...}\n```
      2. Leading prose:    "Sure, here is the JSON: {...}"
      3. Trailing prose:   "{...}\n\nLet me know if you need changes."
    """
    if not text:
        return ""
    stripped = text.strip()
    fence = _FENCE_RE.match(stripped)
    if fence:
        stripped = fence.group(1).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end != -1 and end > start:
        return stripped[start:end + 1]
    match = re.search(r"(\{[\s\S]*\})", stripped)
    if match:
        return match.group(1)
    return stripped


def _parse_or_raise(response_text: str) -> CoverLetterResult:
    json_text = _extract_json(response_text)
    try:
        data = json.loads(json_text)
    except Exception:
        try:
            data = json.loads(response_text)
        except Exception as exc:
            logger.warning(
                "cover_letter non-JSON response (truncated, %d chars): %s",
                len(response_text or ""), (response_text or "")[:1500],
            )
            raise LLMInvalidResponse("cover_letter returned non-JSON output") from exc
    result = CoverLetterResult.parse_obj(data)
    if not result.variants or len(result.variants) < 3:
        logger.warning(
            "cover_letter wrong-shape response (%d variants; truncated raw, %d chars): %s",
            len(result.variants), len(response_text or ""), (response_text or "")[:1500],
        )
        raise LLMInvalidResponse(
            f"cover_letter returned only {len(result.variants)} variant(s); expected 3"
        )
    return result


class CoverLetterService:
    @staticmethod
    def prepare_prompts(
        db: Session,
        resume_id: str,
        job_analysis_id: Optional[str],
        gap_analysis_id: Optional[str],
        custom_instructions: Optional[str],
    ) -> tuple[str, str]:
        resume = db.query(Resume).filter(Resume.id == resume_id).first()
        if not resume:
            raise ValueError(f"Resume with id {resume_id} not found")

        job_json: dict = {}
        gap_json: dict = {}

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
        system_prompt_path = base_dir / "prompts" / "cover_letter" / "system_prompt.txt"
        user_template_path = base_dir / "prompts" / "cover_letter" / "user_prompt_template.txt"

        system_prompt = (
            system_prompt_path.read_text(encoding="utf-8")
            if system_prompt_path.exists()
            else "Produce a CoverLetterResult JSON with exactly three variants: professional, story, startup."
        )

        if user_template_path.exists():
            user_template = user_template_path.read_text(encoding="utf-8")
            try:
                user_prompt = user_template.format(
                    resume_md=resume_text,
                    job_analysis=json.dumps(job_json),
                    gap_analysis=json.dumps(gap_json),
                    custom_instructions=custom_instructions or "",
                )
            except Exception:
                user_prompt = (
                    f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\n"
                    f"gap_analysis: {json.dumps(gap_json)}\ncustom_instructions: {custom_instructions or ''}"
                )
        else:
            user_prompt = (
                f"resume: {resume_text}\njob_analysis: {json.dumps(job_json)}\n"
                f"gap_analysis: {json.dumps(gap_json)}\ncustom_instructions: {custom_instructions or ''}"
            )

        return system_prompt, user_prompt

    @staticmethod
    def generate(
        db: Session,
        resume_id: str,
        job_analysis_id: Optional[str],
        gap_analysis_id: Optional[str],
        llm_client: BaseLLMClient,
        custom_instructions: Optional[str] = None,
    ) -> CoverLetterResult:
        system_prompt, user_prompt = CoverLetterService.prepare_prompts(
            db, resume_id, job_analysis_id, gap_analysis_id, custom_instructions
        )

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
        except Exception:
            logger.exception("Cover letter generation failed resume_id=%s", resume_id)
            raise

        try:
            result = _parse_or_raise(response_text)
        except LLMInvalidResponse as first_err:
            logger.warning(
                "Cover letter: first attempt invalid (%s) — corrective retry for resume_id=%s",
                first_err, resume_id,
            )
            corrective = (
                user_prompt
                + "\n\nIMPORTANT: Your previous response was rejected because the `variants` array did not contain exactly three entries. "
                "Return a JSON object whose `variants` array contains EXACTLY 3 items with the styles `professional`, `story`, and `startup`."
            )
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=corrective)
            result = _parse_or_raise(response_text)

        entry = CoverLetter(
            resume_id=resume_id,
            job_analysis_id=job_analysis_id,
            gap_analysis_id=gap_analysis_id,
            result=result.model_dump(),
            custom_instructions=custom_instructions,
        )
        db.add(entry)
        db.commit()
        return result
