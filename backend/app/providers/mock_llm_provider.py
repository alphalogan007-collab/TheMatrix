"""Mock LLM provider — deterministic stub for tests and local development."""

from __future__ import annotations

from app.providers.llm_provider import BaseLLMProvider, LLMRequest, LLMResponse


class MockLLMProvider(BaseLLMProvider):
    """Returns a fixed response. Useful for unit/integration tests."""

    def __init__(self, fixed_response: str = "This is a mock identity guidance response."):
        self._fixed_response = fixed_response

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text=self._fixed_response,
            prompt_tokens=len(request.system_prompt.split()) + len(request.user_message.split()),
            completion_tokens=len(self._fixed_response.split()),
            model_id="mock-llm-v1",
            finish_reason="stop",
        )

    def provider_name(self) -> str:
        return "MockLLMProvider"
