from typing import Any

from sqlalchemy.orm import Session

from app.agents.agent_adapter import AgentAdapter
from app.llm.clients import BaseLLMClient
from app.schemas.resume_schema import ResumeMatchResult
from app.services.resume_service import ResumeService


class ResumeMatcherAgent(AgentAdapter):
    """Agent wrapper for ResumeMatcherAgent

    This agent does something which i will update later
    """

    def __init__(self, llm_client:BaseLLMClient):
        super().__init__(llm_client)

    async def run(self, db:Session, resume_id: str, job_analysis_id:str ) -> ResumeMatchResult:
        system_prompt, user_prompt = ResumeService.prepare_prompts(db, resume_id, job_analysis_id)

        response_text = await self._generate(system_prompt=system_prompt, user_prompt=user_prompt)

        result = ResumeService.match_resume(db, response_text)

        return result