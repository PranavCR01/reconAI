from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agents.evidence import run_evidence
from backend.agents.hypothesis import HypothesisAgent
from backend.agents.ingestion import IngestionAgent
from backend.agents.synthesis import run_synthesis
from backend.config import AgentConfig
from backend.models.state import ReconState
from backend.tools.rag_tools import rerank_candidates, retrieve_similar_artifacts

MAX_ITERATIONS = 6
MAX_EVIDENCE_RETRIES = 2


def build_graph(config: AgentConfig, storage):
    ingestion_agent = IngestionAgent(config)
    hypothesis_agent = HypothesisAgent(config)

    def _ingestion(state: ReconState) -> dict:
        return ingestion_agent.run(state)

    def _hypothesis(state: ReconState) -> dict:
        return hypothesis_agent.run(state)

    def _evidence(state: ReconState) -> dict:
        return run_evidence(state)

    def _rag_retrieval(state: ReconState) -> dict:
        candidates = retrieve_similar_artifacts(state, storage)
        reranked = rerank_candidates(candidates, state, config) if candidates else []
        return {
            "rag_candidates": candidates,
            "reranked_candidates": reranked,
        }

    def _synthesis(state: ReconState) -> dict:
        # Non-negotiable #1: every tested hypothesis must have ≥1 evidence entry.
        tested = set(state.get("hypotheses_tested") or [])
        covered = {e.get("hypothesis_key") for e in state.get("evidence_collected") or []}
        result = run_synthesis(state, config)
        if tested and not tested.issubset(covered):
            result["requires_human_review"] = True
            rca = result.get("rca_output") or {}
            rca["requires_human_review"] = True
            result["rca_output"] = rca
        return result

    def _route_after_hypothesis(state: ReconState) -> str:
        if state["iterations"] >= MAX_ITERATIONS:
            return "rag_retrieval"
        if state.get("tool_calls"):
            return "evidence"
        # Evidence coverage check — retry before surfacing incomplete RCA.
        tested = set(state.get("hypotheses_tested") or [])
        covered = {e.get("hypothesis_key") for e in state.get("evidence_collected") or []}
        if tested and not tested.issubset(covered):
            retries = state.get("evidence_retry_count", 0)
            if retries < MAX_EVIDENCE_RETRIES:
                return "evidence"
        return "rag_retrieval"

    builder = StateGraph(ReconState)
    builder.add_node("ingestion", _ingestion)
    builder.add_node("hypothesis", _hypothesis)
    builder.add_node("evidence", _evidence)
    builder.add_node("rag_retrieval", _rag_retrieval)
    builder.add_node("synthesis", _synthesis)

    builder.set_entry_point("ingestion")
    builder.add_edge("ingestion", "hypothesis")
    builder.add_conditional_edges(
        "hypothesis",
        _route_after_hypothesis,
        {"evidence": "evidence", "rag_retrieval": "rag_retrieval"},
    )
    builder.add_edge("evidence", "hypothesis")
    builder.add_edge("rag_retrieval", "synthesis")
    builder.add_edge("synthesis", END)

    return builder.compile()
