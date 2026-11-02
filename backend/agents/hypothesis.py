"""Hypothesis Agent: walks the declarative catalogue (backend/graph/hypotheses.py).

Deterministic Python, no LLM. Each run re-derives every verdict from the evidence
collected so far, queues the next untested check, and stops at the first confirmed
hypothesis. Verdicts are explicit per hypothesis: confirmed / refuted / inconclusive
(a check that couldn't run is inconclusive, never refuted).
"""
from __future__ import annotations

from backend.config import AgentConfig
from backend.graph.hypotheses import CATALOGUE, GRAPH_VERSION, REVIEW_THRESHOLD, Hypothesis, evaluate
from backend.models.state import ReconState


def _verdict_record(h: Hypothesis, verdict: str, reason: str, evidence: list[dict], confidence: float | None) -> dict:
    return {
        "hypothesis_id": h.id,
        "label": h.label,
        "kind": h.kind,
        "category": h.category,
        "verdict": verdict,
        "reason": reason,
        "confidence": confidence if verdict == "confirmed" else None,
        "evidence_ids": [e["evidence_id"] for e in evidence if e.get("evidence_id")],
    }


class HypothesisAgent:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def run(self, state: ReconState) -> dict:
        row = state["recon_row"]
        discrepancy_type = row.get("discrepancy_type")
        iterations = state.get("iterations", 0) + 1
        factors = ["deployment_within_24h"] if row.get("deployment_correlated") else []
        base = {"iterations": iterations, "contributing_factors": factors, "graph_version": GRAPH_VERSION}

        plan = CATALOGUE.get(discrepancy_type)
        if not plan:
            return {
                **base,
                "current_hypothesis": f"UNKNOWN: {discrepancy_type} — no graph path defined",
                "graph_status": "unknown_type",
                "root_cause_category": None,
                "hypothesis_verdicts": [],
                "tool_calls": [],
                "review_reasons": ["unknown_type"],
            }

        tested = state.get("hypotheses_tested") or []
        evidence = state.get("evidence_collected") or []
        verdicts: list[dict] = []

        for h in plan:
            if h.id not in tested:
                return {
                    **base,
                    "current_hypothesis": f"{h.id}: {h.label}",
                    "hypotheses_tested": tested + [h.id],
                    "hypothesis_verdicts": verdicts,
                    "graph_status": "running",
                    "tool_calls": [{"tool": h.tool, "args": h.args(row), "hypothesis_key": h.id}],
                }

            records = [e for e in evidence if e.get("hypothesis_key") == h.id]
            usable = next((e for e in records if e.get("tool") == h.tool and e.get("outcome") not in ("error", "skipped")), None)
            verdict, reason, root_cause, override = evaluate(h, usable.get("result") if usable else None, row)
            # A rule may lower confidence for weak evidence; otherwise the hypothesis default applies.
            confidence = override if override is not None else h.confidence
            verdicts.append(_verdict_record(h, verdict, reason, records, confidence))

            if verdict == "confirmed":
                return {
                    **base,
                    "current_hypothesis": f"{h.id}: {h.label} — confirmed",
                    "hypotheses_ruled_out": [v["hypothesis_id"] for v in verdicts if v["verdict"] == "refuted"],
                    "hypothesis_verdicts": verdicts,
                    "graph_status": "confirmed",
                    "root_cause_category": h.category,
                    "graph_root_cause": root_cause,
                    "graph_confidence": confidence,
                    "tool_calls": [],
                    **({"review_reasons": ["graph_low_confidence"]} if confidence < REVIEW_THRESHOLD else {}),
                }

        prefix = plan[0].id.rstrip("0123456789abc") or "H"
        return {
            **base,
            "current_hypothesis": f"{prefix} exhausted — no hypothesis confirmed",
            "hypotheses_ruled_out": [v["hypothesis_id"] for v in verdicts if v["verdict"] == "refuted"],
            "hypothesis_verdicts": verdicts,
            "graph_status": "exhausted",
            "root_cause_category": None,
            "graph_root_cause": None,
            "graph_confidence": None,
            "tool_calls": [],
            "review_reasons": ["no_hypothesis_confirmed"],
        }
