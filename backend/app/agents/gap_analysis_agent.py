from typing import Any

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.gap_analysis_service import GapAnalysisService
from app.schemas.gap_analysis_schema import GapAnalysisResult


class GapAnalysisAgent(AgentAdapter):
    """Agent wrapper for the GapAnalysisService."""

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db: Session, job_analysis_id: str, resume_match_id: str) -> GapAnalysisResult:
        system_prompt, user_prompt = GapAnalysisService.prepare_prompts(db, job_analysis_id, resume_match_id)

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        result = GapAnalysisService.analyze_gaps(db=db, job_analysis_id=job_analysis_id, resume_match_id=resume_match_id, llm_client=replay)

        return result
