from typing import Any

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.resume_analyzer_service import ResumeAnalyzerService
from app.schemas.resume_analysis_schema import ResumeAnalysisResult


class ResumeAnalyzerAgent(AgentAdapter):
    """Agent wrapper for the ResumeAnalyzerService."""

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db: Session, resume_id: str, analyzer_version: str = "v1") -> ResumeAnalysisResult:
        system_prompt, user_prompt = ResumeAnalyzerService.prepare_prompts(db, resume_id)

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        result = ResumeAnalyzerService.analyze_resume(db=db, resume_id=resume_id, llm_client=replay, analyzer_version=analyzer_version)

        return result
