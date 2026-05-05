from __future__ import annotations

from typing import TypedDict


class ReconState(TypedDict):
    recon_row: dict
    current_hypothesis: str
    hypotheses_tested: list[str]
    hypotheses_ruled_out: list[str]
    evidence_collected: list[dict]
    rag_candidates: list[dict]
    reranked_candidates: list[dict]
    root_cause: str | None
    confidence: float | None
    rca_output: dict | None
    iterations: int
    requires_human_review: bool
    llm_calls: list[dict]
    tool_calls: list[dict]
    total_latency_ms: int
    evidence_retry_count: int
