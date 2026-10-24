from typing import Any

from sqlalchemy.orm import Session

import logging

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMInvalidResponse
from app.services.resume_rewrite_service import (
    MIN_RESUME_WORDS,
    ResumeRewriteService,
    _parse_rewrite_or_raise,
)
from app.schemas.resume_rewrite_schema import ResumeRewriteResult
from app.models.models import Resume

logger = logging.getLogger(__name__)


class ResumeRewriteAgent(AgentAdapter):
    """Agent wrapper for the ResumeRewriteService.

    Validation + corrective retry live at the agent layer so the second attempt
    actually hits the live LLM; the service-internal retry would otherwise loop
    against a cached _ReplayLLMClient string and fail identically.
    """

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)
        if hasattr(self.llm_client, "output_type") and getattr(self.llm_client, "output_type", None) is None:
            self.llm_client.output_type = ResumeRewriteResult

    async def run(self, db: Session, resume_id: str, gap_analysis_id: str | None = None, job_analysis_id: str | None = None, custom_instructions: str | None = None) -> ResumeRewriteResult:
        system_prompt, user_prompt = ResumeRewriteService.prepare_prompts(db, resume_id, gap_analysis_id, job_analysis_id, custom_instructions)
        source_resume = db.query(Resume).filter(Resume.id == resume_id).first()
        source_resume_text = (getattr(source_resume, "content_md", None) or "") if source_resume else ""

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt, output_type=ResumeRewriteResult)

        try:
            _parse_rewrite_or_raise(response_text, resume_id=resume_id, source_resume=source_resume_text)
        except LLMInvalidResponse as first_err:
            logger.warning(
                "resume_rewrite: first attempt invalid (%s) resume_id=%s — corrective retry against live LLM",
                first_err, resume_id,
            )
            corrective_user = (
                user_prompt
                + f"\n\nIMPORTANT: Your previous response failed validation: {first_err}. Return one valid JSON object with exactly three complete edited resumes (`A_ats`, `B_impact`, `C_technical`), each meeting the validation word-count target (at least {MIN_RESUME_WORDS} words and never shorter than the source resume). Edit the supplied resume in place, preserve every heading verbatim, and focus edits on KEY ACHIEVEMENTS, PROFESSIONAL EXPERIENCE, SELECTED PROJECTS & ACHIEVEMENTS, and TECHNICAL SKILLS. Do not invent facts or omit original sections."
            )
            response_text = await self._generate(system_prompt=system_prompt, user_prompt=corrective_user, output_type=ResumeRewriteResult)
            try:
                _parse_rewrite_or_raise(response_text, resume_id=resume_id, source_resume=source_resume_text)
            except LLMInvalidResponse:
                logger.error(
                    "resume_rewrite: corrective retry also invalid resume_id=%s", resume_id,
                )
                raise

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        result = ResumeRewriteService.rewrite_resume(db=db, resume_id=resume_id, gap_analysis_id=gap_analysis_id, job_analysis_id=job_analysis_id, llm_client=replay, custom_instructions=custom_instructions)

        return result
