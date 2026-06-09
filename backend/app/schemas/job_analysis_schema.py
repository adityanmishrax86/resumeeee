from pydantic import BaseModel, Field
from typing import List


class JobAnalysisResult(BaseModel):
    required_skills: List[str] = Field(default_factory=list)
    preferred_skills: List[str] = Field(default_factory=list)
    programming_languages: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    frameworks: List[str] = Field(default_factory=list)
    experience_required: str = ""
    seniority_level: str = ""
    domain: str = ""
    ats_keywords: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    summary: str = ""
