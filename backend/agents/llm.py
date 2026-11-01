"""Model transport shared by the LLM-backed agents (proposer, critic).

Routes `claude-*` models to the Anthropic SDK and everything else to Groq, and
reports token usage and latency for logging (non-negotiable #4).
"""
from __future__ import annotations

import time


def call_llm(prompt: str, model: str) -> tuple[str, int, int, int]:
    """Returns (raw_text, input_tokens, output_tokens, latency_ms)."""
    start = time.monotonic()
    if model.startswith("claude"):
        import anthropic
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        input_tokens = msg.usage.input_tokens
        output_tokens = msg.usage.output_tokens
    else:
        import os
        import groq as groq_sdk
        gclient = groq_sdk.Groq(api_key=os.environ.get("GROQ_API_KEY", ""))
        resp = gclient.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2048,
        )
        raw = resp.choices[0].message.content.strip()
        usage = resp.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

    latency_ms = int((time.monotonic() - start) * 1000)
    return raw, input_tokens, output_tokens, latency_ms


def is_api_unavailable(exc: Exception) -> bool:
    try:
        import anthropic
        if isinstance(exc, (anthropic.APIError, anthropic.APIStatusError)):
            return True
    except ImportError:
        pass
    try:
        import groq as groq_sdk
        if isinstance(exc, groq_sdk.APIError):
            return True
    except ImportError:
        pass
    return False
