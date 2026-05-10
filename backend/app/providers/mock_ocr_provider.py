"""Mock OCR provider — returns fixed text for tests."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OCRResult:
    text: str
    confidence: float
    language: str


class MockOCRProvider:
    async def extract_text(self, image_bytes: bytes) -> OCRResult:
        return OCRResult(
            text="Mock OCR extracted text from screenshot.",
            confidence=0.95,
            language="en",
        )

    def provider_name(self) -> str:
        return "MockOCRProvider"
