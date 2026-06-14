from pydantic import BaseModel, Field
from typing import List, Optional


class InterviewQuestion(BaseModel):
    question: str
    category: str = ""
    why_asked: str = ""
    strong_answer_tips: List[str] = Field(default_factory=list)
    detailed_answer: Optional[str] = None
    source: Optional[str] = None  # "company" | "profile" | "user"


class InterviewResearchResult(BaseModel):
    role_specific_questions: List[InterviewQuestion] = Field(default_factory=list)
    company_snapshot: str = ""
    tech_stack_intel: List[str] = Field(default_factory=list)
    hiring_signals: List[str] = Field(default_factory=list)
    culture_notes: str = ""
    red_flags: List[str] = Field(default_factory=list)
    prep_checklist: List[str] = Field(default_factory=list)
