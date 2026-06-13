from pydantic import BaseModel, Field
from typing import List


class GapItem(BaseModel):
    skill: str
    severity: str
    reason: str
    bridge_suggestion: str


class GapAnalysisResult(BaseModel):
    critical_gaps: List[GapItem] = Field(default_factory=list)
    moderate_gaps: List[GapItem] = Field(default_factory=list)
    minor_gaps: List[GapItem] = Field(default_factory=list)
    quick_wins: List[str] = Field(default_factory=list)
    resume_strategy: str = ""
    cover_letter_angle: str = ""
    honesty_flag: bool = False
    honesty_note: str = ""
