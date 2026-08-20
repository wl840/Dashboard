from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    context: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    answer: str
    provider: str
    tool_name: str | None
    context: dict[str, Any]
    evidence: dict[str, Any] | None
    chart_action: dict[str, Any] | None
    fallback_reason: str | None = None
