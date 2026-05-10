"""Mock search provider — returns empty results for tests."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SearchResult:
    chunk_id: str
    text: str
    score: float
    metadata: dict = field(default_factory=dict)


class MockSearchProvider:
    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[SearchResult]:
        return []

    def provider_name(self) -> str:
        return "MockSearchProvider"
