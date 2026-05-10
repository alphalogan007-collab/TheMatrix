"""Mock embedding provider — returns zero-vectors for tests."""

from __future__ import annotations

from app.providers.embedding_provider import BaseEmbeddingProvider, EmbeddingRequest, EmbeddingResponse

_MOCK_DIMS = 1536


class MockEmbeddingProvider(BaseEmbeddingProvider):
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        embeddings = [[0.0] * _MOCK_DIMS for _ in request.texts]
        return EmbeddingResponse(
            embeddings=embeddings,
            model_id="mock-embedding-v1",
            total_tokens=sum(len(t.split()) for t in request.texts),
        )

    def dimensions(self) -> int:
        return _MOCK_DIMS

    def provider_name(self) -> str:
        return "MockEmbeddingProvider"
