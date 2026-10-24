from pydantic import BaseModel, Field, model_validator
from typing import List, Literal


class ResumeVariant(BaseModel):
    variant: Literal["A_ats", "B_impact", "C_technical"]
    content_md: str
    changes_summary: List[str] = Field(default_factory=list)


class ResumeRewriteResult(BaseModel):
    variants: List[ResumeVariant] = Field(default_factory=list)
    shared_changes: List[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_required_variants(self):
        expected = {"A_ats", "B_impact", "C_technical"}
        actual = [variant.variant for variant in self.variants]
        if len(actual) != 3 or set(actual) != expected:
            raise ValueError("variants must contain exactly one A_ats, B_impact, and C_technical item")
        return self
