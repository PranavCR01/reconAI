import os

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class AgentConfig(BaseModel):
    ingestion_llm: str = "claude-haiku-4-5-20251001"
    hypothesis_llm: str = "claude-sonnet-4-6"
    evidence_llm: str = "claude-sonnet-4-6"
    reranker_llm: str = "claude-haiku-4-5-20251001"
    synthesis_llm: str = "claude-sonnet-4-6"


CONFIGS: dict[str, AgentConfig] = {
    "claude": AgentConfig(),
    "groq": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        hypothesis_llm="llama-3.3-70b-versatile",
        evidence_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
        synthesis_llm="llama-3.3-70b-versatile",
    ),
    "hybrid": AgentConfig(
        ingestion_llm="llama-3.3-70b-versatile",
        reranker_llm="llama-3.3-70b-versatile",
    ),
}


def get_config() -> AgentConfig:
    key = os.getenv("LLM_CONFIG", "claude")
    return CONFIGS.get(key, CONFIGS["claude"])


def get_config_by_key(key: str) -> AgentConfig:
    return CONFIGS.get(key, CONFIGS["claude"])
