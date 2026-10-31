"""LangGraph state for one recon row, with explicit per-node ownership.

Each key has exactly one owning node, except the append-only collections at the
bottom, which any node may extend through a reducer (it returns only its new items).
`build_graph` enforces OWNERS at runtime: a node returning a key it doesn't own
raises StateOwnershipError. This prevents one node silently overwriting another's
result (e.g. Synthesis clearing the graph's human-review flag).

`requires_human_review` is not stored: it is derived as bool(review_reasons), and
reasons can only be added, never removed.
"""
from __future__ import annotations

import operator
from typing import Annotated, TypedDict


class ReconState(TypedDict, total=False):
    # ingestion
    recon_row: dict
    # hypothesis graph
    current_hypothesis: str
    hypotheses_tested: list[str]
    hypotheses_ruled_out: list[str]
    graph_root_cause: str | None
    graph_confidence: float | None
    iterations: int
    tool_calls: list[dict]
    # evidence
    evidence_collected: Annotated[list[dict], operator.add]
    evidence_retry_count: int
    # retrieval
    rag_candidates: list[dict]
    reranked_candidates: list[dict]
    # synthesis
    rca_output: dict | None
    root_cause: str | None
    confidence: float | None
    synthesis_status: str | None
    # append-only, written by any node
    llm_calls: Annotated[list[dict], operator.add]
    total_latency_ms: Annotated[int, operator.add]
    review_reasons: Annotated[list[str], operator.add]


APPEND_ONLY = frozenset({"llm_calls", "total_latency_ms", "review_reasons"})

OWNERS: dict[str, frozenset[str]] = {
    "ingestion": frozenset({"recon_row"}),
    "hypothesis": frozenset({
        "current_hypothesis", "hypotheses_tested", "hypotheses_ruled_out",
        "graph_root_cause", "graph_confidence", "iterations", "tool_calls",
    }),
    "evidence": frozenset({"evidence_collected", "evidence_retry_count"}),
    "rag_retrieval": frozenset({"rag_candidates", "reranked_candidates"}),
    "synthesis": frozenset({"rca_output", "root_cause", "confidence", "synthesis_status"}),
}

# Why an incident needs human review. Add-only during a run.
REVIEW_REASONS = frozenset({
    "unknown_type",            # discrepancy type has no graph path
    "no_hypothesis_confirmed", # graph exhausted its hypotheses (root cause is a RAG-informed guess)
    "graph_low_confidence",    # a hypothesis was confirmed, but with graph confidence < 0.75
    "missing_evidence",        # a tested hypothesis has no evidence record
    "low_confidence",          # the LLM's own confidence < 0.75 (non-negotiable #3)
    "llm_unavailable",         # synthesis degraded because the LLM API failed
    "legacy_cache_flag",       # cache entry from before reasons existed carried a review flag
})


class StateOwnershipError(RuntimeError):
    pass


def initial_state(recon_row: dict) -> ReconState:
    return {
        "recon_row": recon_row,
        "current_hypothesis": "",
        "hypotheses_tested": [],
        "hypotheses_ruled_out": [],
        "graph_root_cause": None,
        "graph_confidence": None,
        "iterations": 0,
        "tool_calls": [],
        "evidence_collected": [],
        "evidence_retry_count": 0,
        "rag_candidates": [],
        "reranked_candidates": [],
        "rca_output": None,
        "root_cause": None,
        "confidence": None,
        "synthesis_status": None,
        "llm_calls": [],
        "total_latency_ms": 0,
        "review_reasons": [],
    }


def check_node_output(node: str, output: dict) -> dict:
    """Raise if a node writes keys it doesn't own; validate append-only shapes."""
    allowed = OWNERS[node] | APPEND_ONLY
    foreign = set(output) - allowed
    if foreign:
        raise StateOwnershipError(f"node '{node}' wrote keys it does not own: {sorted(foreign)}")
    for key in ("llm_calls", "review_reasons", "evidence_collected"):
        if key in output and not isinstance(output[key], list):
            raise StateOwnershipError(f"node '{node}' must append a list to '{key}'")
    unknown = set(output.get("review_reasons", [])) - REVIEW_REASONS
    if unknown:
        raise StateOwnershipError(f"node '{node}' added unknown review reasons: {sorted(unknown)}")
    return output


def review_reasons(state: dict) -> list[str]:
    """Deduplicated reasons in first-seen order."""
    return list(dict.fromkeys(state.get("review_reasons") or []))
