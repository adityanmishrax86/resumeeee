import json
import logging
import re
from typing import Any
from pathlib import Path

from sqlalchemy.orm import Session
from pydantic import ValidationError

from app.models.models import Resume
from app.models.analysis_models import JobAnalysis, GapAnalysis, ResumeRewrite
from app.schemas.resume_rewrite_schema import ResumeRewriteResult
from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMInvalidResponse

logger = logging.getLogger(__name__)

REQUIRED_VARIANTS = ("A_ats", "B_impact", "C_technical")
MIN_RESUME_WORDS = 700  # Practical lower bound for a dense, two-page Markdown resume.


_FENCE_RE = re.compile(r"^```(?:json)?\s*([\s\S]*?)\s*```\s*$", re.IGNORECASE)


def _extract_json(text: str) -> str:
    """Best-effort recovery of a JSON object from an LLM response, tolerating
    markdown fences and surrounding prose."""
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


def _parse_rewrite_or_raise(
    response_text: str, *, resume_id: str, source_resume: str | None = None
) -> ResumeRewriteResult:
    """Parse the LLM response into a ResumeRewriteResult, raising
    LLMInvalidResponse on JSON failure or missing variants."""
    json_text = _extract_json(response_text)
    try:
        data = json.loads(json_text)
    except Exception:
        try:
            data = json.loads(response_text)
        except Exception as exc:
            logger.warning(
                "resume_rewrite non-JSON response resume_id=%s (truncated, %d chars): %s",
                resume_id, len(response_text or ""), (response_text or "")[:1500],
            )
            raise LLMInvalidResponse(
                "resume_rewrite returned non-JSON output",
                provider="google",
            ) from exc

    try:
        analysis = ResumeRewriteResult.parse_obj(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise LLMInvalidResponse(f"resume_rewrite response did not match schema: {details}") from exc

    if not analysis.variants:
        logger.warning(
            "resume_rewrite empty variants resume_id=%s (truncated raw, %d chars): %s",
            resume_id, len(response_text or ""), (response_text or "")[:1500],
        )
        raise LLMInvalidResponse(
            "resume_rewrite returned an empty `variants` list",
            provider="google",
        )
    if len(analysis.variants) < 3:
        logger.warning(
            "resume_rewrite short variants resume_id=%s (%d variants; truncated raw, %d chars): %s",
            resume_id, len(analysis.variants), len(response_text or ""), (response_text or "")[:1500],
        )
        raise LLMInvalidResponse(
            f"resume_rewrite returned only {len(analysis.variants)} variant(s); expected 3",
            provider="google",
        )
    source_word_count = len(re.findall(r"\b[\w][\w+#./&'-]*\b", source_resume or ""))
    required_word_count = max(MIN_RESUME_WORDS, source_word_count)
    for variant in analysis.variants:
        word_count = len(re.findall(r"\b[\w][\w+#./&'-]*\b", variant.content_md))
        if word_count < required_word_count:
            raise LLMInvalidResponse(
                f"resume_rewrite variant {variant.variant} has {word_count} words; "
                f"expected at least {required_word_count} words for a two-page resume "
                "and to preserve the source resume's content",
                provider="google",
            )
    if source_resume:
        source_headings = re.findall(r"^\s*(#{1,6}\s+.+?)\s*$", source_resume, flags=re.MULTILINE)
        if source_headings:
            for variant in analysis.variants:
                output_headings = re.findall(r"^\s*(#{1,6}\s+.+?)\s*$", variant.content_md, flags=re.MULTILINE)
                if output_headings != source_headings:
                    raise LLMInvalidResponse(
                        f"resume_rewrite variant {variant.variant} changed, omitted, or reordered source headings",
                        provider="google",
                    )
    return analysis


class ResumeRewriteService:
    @staticmethod
    def rewrite_resume(db: Session, resume_id: str, gap_analysis_id: str | None, job_analysis_id: str | None, llm_client: BaseLLMClient, analyzer_version: str = "v1", custom_instructions: str | None = None) -> ResumeRewriteResult:
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

        if custom_instructions:
            user_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS (must be followed):\n{custom_instructions}"

        logger.debug("ResumeRewriteService: resume_id=%s", resume_id)

        try:
            response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=user_prompt)
            logger.debug("ResumeRewriteService: raw LLM response (truncated)=%s", str(response_text)[:2000])
        except Exception:
            logger.exception("LLM client failed to generate resume rewrites for resume_id=%s", resume_id)
            raise

        try:
            resume_text = getattr(resume, "content_md", None) or getattr(resume, "content", "") or ""
            analysis = _parse_rewrite_or_raise(
                response_text, resume_id=resume_id, source_resume=resume_text
            )
        except LLMInvalidResponse as first_err:
            # Corrective retry: append an explicit instruction reminding the
            # model that variants is required and must contain three entries.
            logger.warning(
                "Resume rewrite: first attempt invalid (%s) — corrective retry for resume_id=%s",
                first_err, resume_id,
            )
            corrective = (
                user_prompt
                + f"\n\nIMPORTANT: Your previous response failed validation: {first_err}. Return exactly three complete edited resumes (`A_ats`, `B_impact`, `C_technical`) that meet the stated word-count target. Preserve every original heading verbatim and edit the supplied resume in place. Do not invent facts or omit source sections."
            )
            try:
                response_text = llm_client.generate(system_prompt=system_prompt, user_prompt=corrective)
            except Exception:
                logger.exception("Resume rewrite corrective retry call failed resume_id=%s", resume_id)
                raise
            analysis = _parse_rewrite_or_raise(
                response_text, resume_id=resume_id, source_resume=resume_text
            )

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
    def prepare_prompts(db: Session, resume_id: str, gap_analysis_id: str | None, job_analysis_id: str | None, custom_instructions: str | None = None) -> tuple[str, str]:
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

        if custom_instructions:
            user_prompt += f"\n\nADDITIONAL USER INSTRUCTIONS (must be followed):\n{custom_instructions}"

        return system_prompt, user_prompt
