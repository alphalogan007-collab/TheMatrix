"""llm_router.py — Ollama gateway.

Single entry point for all language model calls. Routes that need text
generation import this module instead of calling httpx directly.

  Endpoint: http://matrix_ollama:11434   (hardcoded — same container network)
  Model:    llama3.2 (overridable via OLLAMA_MODEL env var)
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import httpx

OLLAMA_URL   = "http://matrix_ollama:11434"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2")


def provider_status() -> Dict[str, dict]:
    return {"ollama": {"url": OLLAMA_URL, "model": OLLAMA_MODEL}}


def active_provider() -> Optional[str]:
    return "ollama"


async def ask(
    prompt: str,
    *,
    max_tokens: int = 1000,
    temperature: float = 0.4,
    api_key: str = "",   # accepted for call-site compatibility, not used
    model: str = "",
) -> str:
    """Send a single prompt to Ollama. Returns the response text."""
    effective_model = model or OLLAMA_MODEL
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model":   effective_model,
                "prompt":  prompt,
                "stream":  False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
        )
        resp.raise_for_status()
        return resp.json().get("response", "")


async def chat(
    messages: List[Dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.4,
) -> Tuple[str, str]:
    """Send a message list to Ollama. Returns (response_text, model_name)."""
    prompt = "\n".join(
        f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content']}"
        for m in messages
    )
    text = await ask(prompt, max_tokens=max_tokens, temperature=temperature)
    return text, OLLAMA_MODEL


async def chat_skip_ollama(
    messages: List[Dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.4,
) -> Tuple[str, str]:
    """Alias for chat() — kept for call-site compatibility."""
    return await chat(messages, max_tokens=max_tokens, temperature=temperature)
