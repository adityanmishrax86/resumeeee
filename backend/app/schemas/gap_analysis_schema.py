from pydantic import BaseModel, Field, model_validator
from typing import List, Literal, Optional


class GapItem(BaseModel):
    skill: str
    severity: Literal["critical", "moderate", "minor"]
    reason: str
    bridge_suggestion: str


class GapAnalysisResult(BaseModel):
    critical_gaps: List[GapItem] = Field(default_factory=list)
    moderate_gaps: List[GapItem] = Field(default_factory=list)
    minor_gaps: List[GapItem] = Field(default_factory=list)
    quick_wins: List[str] = Field(default_factory=list)
    resume_strategy: Optional[str] = ""
    cover_letter_angle: Optional[str] = ""
    honesty_flag: Optional[bool] = False
    honesty_note: Optional[str] = ""

    @model_validator(mode="after")
    def validate_severity_buckets(self):
        expected = (
            (self.critical_gaps, "critical"),
            (self.moderate_gaps, "moderate"),
            (self.minor_gaps, "minor"),
        )
        for items, severity in expected:
            if any(item.severity != severity for item in items):
                raise ValueError(f"All items in the {severity}_gaps bucket must have severity={severity}")
        if not self.honesty_flag and self.honesty_note:
            raise ValueError("honesty_note must be empty when honesty_flag is false")
        if self.honesty_flag and not self.honesty_note:
            raise ValueError("honesty_note is required when honesty_flag is true")
        return self
