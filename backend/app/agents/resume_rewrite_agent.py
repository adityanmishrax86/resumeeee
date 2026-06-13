from typing import Any

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.resume_rewrite_service import ResumeRewriteService
from app.schemas.resume_rewrite_schema import ResumeRewriteResult


class ResumeRewriteAgent(AgentAdapter):
    """Agent wrapper for the ResumeRewriteService."""

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db: Session, resume_id: str, gap_analysis_id: str | None = None, job_analysis_id: str | None = None) -> ResumeRewriteResult:
        system_prompt, user_prompt = ResumeRewriteService.prepare_prompts(db, resume_id, gap_analysis_id, job_analysis_id)

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        result = ResumeRewriteService.rewrite_resume(db=db, resume_id=resume_id, gap_analysis_id=gap_analysis_id, job_analysis_id=job_analysis_id, llm_client=replay)

        return result
