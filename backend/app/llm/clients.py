import json
import logging
from typing import Optional

from app.llm.exceptions import (
    LLMError,
    LLMServiceUnavailable,
    LLMRateLimited,
    LLMTimeout,
    classify_provider_error,
)

logger = logging.getLogger(__name__)


class BaseLLMClient:
    """Simple provider interface for LLMs.

    Implementations should provide a `generate(system_prompt, user_prompt)`
    method that returns a string response (often JSON)."""

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        raise NotImplementedError()


class MockLLMClient(BaseLLMClient):
    """Mock client that returns a deterministic JSON string suitable for
    testing the parsing and persistence flow.
    """

    def __init__(self, mock_response: Optional[str] = None):
        self.mock_response = mock_response

    def generate(self, system_prompt: str, user_prompt: str, **kwargs) -> str:
        if self.mock_response:
            return self.mock_response

        # Generate a minimal valid JSON response matching the JobAnalysisResult
        # schema. Keep lists empty if nothing can be inferred from the prompt.
        result = {
            "required_skills": [],
            "preferred_skills": [],
            "programming_languages": [],
            "tools": [],
            "frameworks": [],
            "experience_required": "",
            "seniority_level": "",
            "domain": "",
            "ats_keywords": [],
            "responsibilities": [],
            "summary": "Mock analysis generated."
        }

        return json.dumps(result)

