from pydantic import BaseModel, Field
from typing import List


class ResumeAnalysisResult(BaseModel):
    skills: List[str] = Field(default_factory=list)
    experience_years: str = ""
    domains: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
    summary: str = ""
