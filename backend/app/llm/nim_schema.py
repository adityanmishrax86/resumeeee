from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class NimMessage(BaseModel):
    role: str
    content: str


class NimChatRequest(BaseModel):
    model: str
    messages: List[NimMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 0.95
    max_tokens: Optional[int] = 16384
    reasoning_budget: Optional[int] = None
    chat_template_kwargs: Optional[Dict[str, Any]] = None
    stream: Optional[bool] = False
