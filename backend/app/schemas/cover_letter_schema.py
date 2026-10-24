from typing import List

from pydantic import AliasChoices, BaseModel, Field


class CoverLetterVariant(BaseModel):
    """One cover-letter style.

    Required `style` values:
      - `professional` — formal, achievement-led, third-paragraph close.
      - `story`        — opens with a 2-3 sentence narrative hook tied to a real experience.
      - `startup`      — concise, energetic, focused on ownership and shipping.
    """

    style: str = Field(validation_alias=AliasChoices("style", "variant"))
    content_md: str = Field(validation_alias=AliasChoices("content_md", "content"))
    why_choose_me: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("why_choose_me", "changes_summary"),
    )


class CoverLetterResult(BaseModel):
    variants: List[CoverLetterVariant] = Field(default_factory=list)
    shared_notes: List[str] = Field(default_factory=list)
