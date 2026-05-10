"""llm_router.py — LLM removed from this architecture.

This system learns by mining data (Wikipedia, DuckDuckGo, YouTube).
The mind builds knowledge from real-world sources, not language models.
No LLM providers are configured. No API keys are used.

All calls to chat() / chat_skip_ollama() / ask() are no-ops that raise
immediately so any caller that missed the memo fails loudly.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Stubs — nothing here calls an external API
# ---------------------------------------------------------------------------


def provider_status() -> Dict[str, dict]:
    """Return empty provider status — no LLM providers configured."""
    return {}


def active_provider() -> Optional[str]:
    """No LLM providers are active in this architecture."""
    return None


async def chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.4,
) -> Tuple[str, str]:
    """Not used. This architecture learns from mined data, not LLMs."""
    raise RuntimeError(
        "LLM is not used in this architecture. "
        "Knowledge comes from Wikipedia/DuckDuckGo/YouTube mining."
    )


async def chat_skip_ollama(
    messages: List[Dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.4,
) -> Tuple[str, str]:
    """Not used. This architecture learns from mined data, not LLMs."""
    raise RuntimeError(
        "LLM is not used in this architecture. "
        "Knowledge comes from Wikipedia/DuckDuckGo/YouTube mining."
    )


async def ask(
    prompt: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.4,
    api_key: str = "",
    model: str = "",
) -> str:
    """Not used. This architecture learns from mined data, not LLMs."""
    raise RuntimeError(
        "LLM is not used in this architecture. "
        "Knowledge comes from Wikipedia/DuckDuckGo/YouTube mining."
    )


async def ask(
    prompt: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.4,
    # Legacy params — accepted but ignored; router reads keys from settings
    api_key: str = "",
    model: str = "",
) -> str:
    """Drop-in replacement for a direct OpenAI call.

    api_key and model are accepted for backwards-compatible call sites but
    the router always uses the live settings + provider priority list.
    """
    text, _ = await chat(
        [{"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return text
