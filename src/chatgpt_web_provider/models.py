from __future__ import annotations

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str
    content: str | list | dict | None = ""

    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return str(self.content or "")


class ChatCompletionRequest(BaseModel):
    model: str | None = None
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False


class ResponsesRequest(BaseModel):
    model: str | None = None
    input: str | list | dict
    temperature: float | None = None
    max_output_tokens: int | None = None
    stream: bool = False


class CompletionResult(BaseModel):
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class ErrorBody(BaseModel):
    error: dict[str, str] = Field(default_factory=dict)
