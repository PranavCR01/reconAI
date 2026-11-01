from __future__ import annotations

import time
from datetime import datetime, timezone

from langgraph.graph import END, StateGraph

from backend.agents.evidence import run_evidence
from backend.agents.hypothesis import HypothesisAgent
from backend.agents.ingestion import IngestionAgent
from backend.agents.explanation import run_critic, run_judge, run_proposer
from backend.config import AgentConfig
from backend.models.state import ReconState, check_node_output
from backend.tools.rag_tools import rerank_candidates, retrieve_similar_artifacts

MAX_ITERATIONS = 10  # one hypothesis per step; the longest plan has 5


def _detail(node: str, state: dict, out: dict) -> dict:
    """What a node did, in a form a person reading the trace can follow."""
    if node == "ingestion":
        row = out.get("recon_row") or {}
        return {"discrepancy_type": row.get("discrepancy_type"), "severity": row.get("severity")}
    if node == "hypothesis":
        latest = (out.get("hypothesis_verdicts") or [])[-1:] or [None]
        queued = [c["hypothesis_key"] for c in out.get("tool_calls") or []]
        return {"status": out.get("graph_status"), "queued": queued,
                "evaluated": latest[0] and {k: latest[0][k] for k in ("hypothesis_id", "verdict", "reason")}}
    if node == "evidence":
        return {"tools": [{"hypothesis": e.get("hypothesis_key"), "tool": e.get("tool"), "outcome": e.get("outcome")}
                          for e in out.get("evidence_collected") or []]}
    if node == "rag_retrieval":
        return {"candidates": len(out.get("rag_candidates") or []), "reranked": len(out.get("reranked_candidates") or []),
                "error": out.get("retrieval_error")}
    if node == "proposer":
        return {"status": out.get("synthesis_status"), "claims": len((out.get("proposal") or {}).get("claims") or []),
                "round": out.get("proposal_count")}
    if node == "critic":
        verdicts = [v["verdict"] for v in out.get("critic_verdicts") or []]
        return {"status": out.get("critic_status"), **{k: verdicts.count(k) for k in ("supported", "unsupported", "contradicted")}}
    if node == "judge":
        return {"decision": out.get("judge_decision")}
    return {}


def _traced(node: str, fn):
    """Time a node and append one trace step (with the LLM calls it made) to its output."""
    def run(state):
        started = datetime.now(timezone.utc)
        t0 = time.monotonic()
        out = fn(state)
        step = {
            "node": node,
            "started_at": started.isoformat(),
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "detail": _detail(node, state, out),
            "llm_calls": [{k: c.get(k) for k in ("agent", "model", "attempt", "input_tokens", "output_tokens",
                                                   "latency_ms", "error") if c.get(k) is not None}
                          for c in out.get("llm_calls") or []],
        }
        return {**out, "trace": [step]}
    return run


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
        try:
            candidates, error = retrieve_similar_artifacts(state, storage), None
        except Exception as exc:
            candidates, error = [], f"{type(exc).__name__}: {exc}"[:300]
        reranked, llm_call = rerank_candidates(candidates, state, config)
        out: dict = {"rag_candidates": candidates, "reranked_candidates": reranked, "retrieval_error": error}
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
    builder.add_node("ingestion", _traced("ingestion", _ingestion))
    builder.add_node("hypothesis", _traced("hypothesis", _hypothesis))
    builder.add_node("evidence", _traced("evidence", _evidence))
    builder.add_node("rag_retrieval", _traced("rag_retrieval", _rag_retrieval))
    builder.add_node("proposer", _traced("proposer", _proposer))
    builder.add_node("critic", _traced("critic", _critic))
    builder.add_node("judge", _traced("judge", _judge))

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
