"""Embedding provider abstract base."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class EmbeddingRequest:
    texts: list[str]
    model_id: str | None = None


@dataclass
class EmbeddingResponse:
    embeddings: list[list[float]]
    model_id: str
    total_tokens: int


class BaseEmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        ...

    @abstractmethod
    def dimensions(self) -> int:
        ...

    @abstractmethod
    def provider_name(self) -> str:
        ...
