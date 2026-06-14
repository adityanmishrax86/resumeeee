from typing import Any

from sqlalchemy.orm import Session

import logging

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMInvalidResponse
from app.services.resume_rewrite_service import ResumeRewriteService, _parse_rewrite_or_raise
from app.schemas.resume_rewrite_schema import ResumeRewriteResult

logger = logging.getLogger(__name__)


class ResumeRewriteAgent(AgentAdapter):
    """Agent wrapper for the ResumeRewriteService.

    Validation + corrective retry live at the agent layer so the second attempt
    actually hits the live LLM; the service-internal retry would otherwise loop
    against a cached _ReplayLLMClient string and fail identically.
    """

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db: Session, resume_id: str, gap_analysis_id: str | None = None, job_analysis_id: str | None = None, custom_instructions: str | None = None) -> ResumeRewriteResult:
        system_prompt, user_prompt = ResumeRewriteService.prepare_prompts(db, resume_id, gap_analysis_id, job_analysis_id, custom_instructions)

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            _parse_rewrite_or_raise(response_text, resume_id=resume_id)
        except LLMInvalidResponse as first_err:
            logger.warning(
                "resume_rewrite: first attempt invalid (%s) resume_id=%s — corrective retry against live LLM",
                first_err, resume_id,
            )
            corrective_user = (
                user_prompt
                + "\n\nIMPORTANT: Your previous response was rejected because the `variants` array was missing "
                "or did not contain EXACTLY three entries. Return a single JSON object — no markdown fences, no "
                "commentary — whose top-level `variants` array has EXACTLY 3 items with the labels `A_ats`, "
                "`B_impact`, and `C_technical`. Do not omit any variant."
            )
            response_text = await self._generate(system_prompt=system_prompt, user_prompt=corrective_user)
            try:
                _parse_rewrite_or_raise(response_text, resume_id=resume_id)
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
