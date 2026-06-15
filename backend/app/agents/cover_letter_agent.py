from typing import Any, Optional

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.llm.exceptions import LLMInvalidResponse
from app.services.cover_letter_service import CoverLetterService, _parse_or_raise
from app.schemas.cover_letter_schema import CoverLetterResult

import logging

logger = logging.getLogger(__name__)


class CoverLetterAgent(AgentAdapter):
    """Agent wrapper for the CoverLetterService.

    Architecture: prepare prompts via the service, call the LLM, validate the
    response at the AGENT level so a corrective retry can actually reach the
    model (a _ReplayLLMClient would just echo back the same bad text). Only
    after we have a known-good response do we replay it into the service so a
    single code path owns parsing + persistence.
    """

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(
        self,
        db: Session,
        resume_id: str,
        job_analysis_id: Optional[str] = None,
        gap_analysis_id: Optional[str] = None,
        custom_instructions: Optional[str] = None,
    ) -> CoverLetterResult:
        system_prompt, user_prompt = CoverLetterService.prepare_prompts(
            db, resume_id, job_analysis_id, gap_analysis_id, custom_instructions
        )

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        try:
            _parse_or_raise(response_text)
        except LLMInvalidResponse as first_err:
            logger.warning(
                "cover_letter: first attempt invalid (%s) resume_id=%s — corrective retry against live LLM",
                first_err, resume_id,
            )
            corrective_user = (
                user_prompt
                + "\n\nIMPORTANT: Your previous response was rejected because the `variants` array did not "
                "contain EXACTLY three entries with the styles `professional`, `story`, and `startup`. "
                "Return a single JSON object — no markdown fences, no commentary — whose top-level "
                "`variants` array has EXACTLY 3 items, one per required style. Do not omit any variant."
            )
            response_text = await self._generate(system_prompt=system_prompt, user_prompt=corrective_user)
            try:
                _parse_or_raise(response_text)
            except LLMInvalidResponse:
                logger.error(
                    "cover_letter: corrective retry also invalid resume_id=%s", resume_id,
                )
                raise

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)
        return CoverLetterService.generate(
            db=db,
            resume_id=resume_id,
            job_analysis_id=job_analysis_id,
            gap_analysis_id=gap_analysis_id,
            llm_client=replay,
            custom_instructions=custom_instructions,
        )
