"""LLM provider abstract base — all LLM calls go through this interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class LLMRequest:
    system_prompt: str
    user_message: str
    max_tokens: int = 512
    temperature: float = 0.3
    stop_sequences: list[str] | None = None


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str
    finish_reason: str   # "stop" | "length" | "content_filter"


class BaseLLMProvider(ABC):
    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    @abstractmethod
    def provider_name(self) -> str:
        ...
