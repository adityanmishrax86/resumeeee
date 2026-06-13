from pydantic import BaseModel, Field
from typing import List


class ResumeVariant(BaseModel):
    variant: str
    content_md: str
    changes_summary: List[str] = Field(default_factory=list)


class ResumeRewriteResult(BaseModel):
    variants: List[ResumeVariant] = Field(default_factory=list)
    shared_changes: List[str] = Field(default_factory=list)
