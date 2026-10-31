from __future__ import annotations

from langgraph.graph import END, StateGraph

from backend.agents.evidence import run_evidence
from backend.agents.hypothesis import HypothesisAgent
from backend.agents.ingestion import IngestionAgent
from backend.agents.explanation import run_critic, run_judge, run_proposer
from backend.config import AgentConfig
from backend.models.state import ReconState, check_node_output
from backend.tools.rag_tools import rerank_candidates, retrieve_similar_artifacts

MAX_ITERATIONS = 10  # one hypothesis per step; the longest plan has 5
MAX_EVIDENCE_RETRIES = 2


def build_graph(config: AgentConfig, storage):
    ingestion_agent = IngestionAgent(config)
    hypothesis_agent = HypothesisAgent(config)

    def _ingestion(state: ReconState) -> dict:
        return check_node_output("ingestion", ingestion_agent.run(state))

    def _hypothesis(state: ReconState) -> dict:
        return check_node_output("hypothesis", hypothesis_agent.run(state))

    def _evidence(state: ReconState) -> dict:
        return check_node_output("evidence", run_evidence(state))

    def _rag_retrieval(state: ReconState) -> dict:
        candidates = retrieve_similar_artifacts(state, storage)
        reranked, llm_call = rerank_candidates(candidates, state, config)
        out: dict = {"rag_candidates": candidates, "reranked_candidates": reranked}
        if llm_call:
            # Non-negotiable #4: append the reranker call; the reducer keeps earlier entries.
            out["llm_calls"] = [llm_call]
            out["total_latency_ms"] = llm_call["latency_ms"]
        return check_node_output("rag_retrieval", out)

    def _proposer(state: ReconState) -> dict:
        return check_node_output("proposer", run_proposer(state, config))

    def _critic(state: ReconState) -> dict:
        return check_node_output("critic", run_critic(state, config))

    def _judge(state: ReconState) -> dict:
        return check_node_output("judge", run_judge(state))

    def _route_after_judge(state: ReconState) -> str:
        return "proposer" if state.get("judge_decision") == "revise" else END

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
    builder.add_node("proposer", _proposer)
    builder.add_node("critic", _critic)
    builder.add_node("judge", _judge)

    builder.set_entry_point("ingestion")
    builder.add_edge("ingestion", "hypothesis")
    builder.add_conditional_edges(
        "hypothesis",
        _route_after_hypothesis,
        {"evidence": "evidence", "rag_retrieval": "rag_retrieval"},
    )
    builder.add_edge("evidence", "hypothesis")
    builder.add_edge("rag_retrieval", "proposer")
    builder.add_edge("proposer", "critic")
    builder.add_edge("critic", "judge")
    builder.add_conditional_edges("judge", _route_after_judge, {"proposer": "proposer", END: END})

    return builder.compile()
