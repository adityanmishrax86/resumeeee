from typing import Any

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.services.job_analyzer_service import JobAnalyzerService
from app.schemas.job_analysis_schema import JobAnalysisResult


class JobAnalyzerAgent(AgentAdapter):
    """Agent wrapper for the JobAnalyzerService.

    This agent prepares prompts, calls the configured LLM client via the
    shared adapter, and delegates parsing and persistence to the service
    by replaying the LLM response into the existing service path.
    """

    def __init__(self, llm_client: BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db: Session, job_id: str, analyzer_version: str = "v1") -> JobAnalysisResult:
        # Prepare prompts using the existing service helper
        system_prompt, user_prompt = JobAnalyzerService.prepare_prompts(db, job_id)

        # Generate text from the underlying LLM (async-safe)
        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        # Replay client that returns the generated text so the service can
        # reuse its existing parsing and persistence logic.
        class _ReplayLLMClient(BaseLLMClient):
            def __init__(self, text: str):
                self._text = text

            def generate(self, system_prompt: str, user_prompt: str, **kwargs: Any) -> str:
                return self._text

        replay = _ReplayLLMClient(response_text)

        # Let the service validate and persist the parsed result
        result = JobAnalyzerService.analyze_job(db=db, job_id=job_id, llm_client=replay, analyzer_version=analyzer_version)

        return result
