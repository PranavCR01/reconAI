import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class AgentConfig(BaseModel):
    ingestion_llm: str = "claude-haiku-4-5-20251001"
    # hypothesis_llm / evidence_llm are reserved: both agents are deterministic and make no LLM calls.
    hypothesis_llm: str = "claude-sonnet-4-6"
    evidence_llm: str = "claude-sonnet-4-6"
    reranker_llm: str = "claude-haiku-4-5-20251001"
    synthesis_llm: str = "claude-sonnet-4-6"   # proposer (writes the explanation)
    critic_llm: str = "claude-sonnet-4-6"      # reviews the explanation against the evidence


CONFIGS: dict[str, AgentConfig] = {
    "claude": AgentConfig(),
    "groq": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        hypothesis_llm="llama-3.3-70b-versatile",
        evidence_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
        synthesis_llm="llama-3.3-70b-versatile",
        critic_llm="llama-3.3-70b-versatile",
    ),
    "hybrid": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
    ),
}


# USD per million tokens (input, output). Anthropic first-party rates; check before
# quoting externally. A model missing here gets cost None plus a warning, never $0.
PRICING_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Groq list price for Llama 3.3 70B Versatile (verify on groq.com before quoting).
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def call_cost_usd(call: dict) -> float | None:
    price = PRICING_PER_MTOK.get(call.get("model", ""))
    if price is None:
        return None
    return (call.get("input_tokens", 0) * price[0] + call.get("output_tokens", 0) * price[1]) / 1_000_000


def incident_cost(llm_calls: list[dict]) -> tuple[float | None, list[str]]:
    """Total USD for an incident's calls. Any unpriced model makes the total None (never a silent undercount)."""
    unknown = sorted({c.get("model") or "<missing>" for c in llm_calls if call_cost_usd(c) is None})
    if unknown:
        return None, [f"no price for model {m}" for m in unknown]
    return round(sum(call_cost_usd(c) for c in llm_calls), 6), []


def get_config() -> AgentConfig:
    key = os.getenv("LLM_CONFIG", "claude")
    return CONFIGS.get(key, CONFIGS["claude"])


def get_config_by_key(key: str) -> AgentConfig:
    return CONFIGS.get(key, CONFIGS["claude"])
