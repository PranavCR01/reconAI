"""Proposer / critic / judge: governs the LLM-written explanation of a diagnosis.

The hypothesis graph decides the root cause from evidence. These three steps only
control the *explanation* of it, which is where an LLM can overstate or contradict
the evidence:

- Proposer (LLM): drafts the explanation as structured claims, each citing evidence
  aliases (E#) and past incidents (P#) from its prompt.
- Critic: deterministic checks first (free, code), then an LLM review for meaning.
  Returns a verdict per claim: supported / unsupported / contradicted.
- Judge (code, not an LLM): accept, one revision, or escalate to human review. It
  never accepts text the critic could not verify.
"""
from __future__ import annotations

import json
import re
from typing import Literal

import sentry_sdk
from pydantic import BaseModel, Field, ValidationError, field_validator

from backend.agents.llm import call_llm as _call_llm, is_api_unavailable as _is_api_unavailable
from backend.config import AgentConfig
from backend.graph.hypotheses import CATEGORIES
from backend.prompts import template, versions

PROMPTS = ("proposer.md", "critic.md")
MAX_REVISIONS = 1
_ATTEMPTS_PER_CALL = 2  # one retry with error context on invalid output (non-negotiable #6)

ClaimKind = Literal["root_cause", "mechanism", "impact", "fix", "context"]
CriticVerdict = Literal["supported", "unsupported", "contradicted"]
_RANK = {"supported": 0, "unsupported": 1, "contradicted": 2}


# ---------------------------------------------------------------------------
# Schemas (validated at every boundary)
# ---------------------------------------------------------------------------
class ProposedClaim(BaseModel):
    claim_id: str
    kind: ClaimKind
    status: Literal["established", "hypothesis"] = "established"
    category: str | None = None
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)
    similar_incident_ids: list[str] = Field(default_factory=list)
    hypothesis_ids: list[str] = Field(default_factory=list)


class ProposalOutput(BaseModel):
    claims: list[ProposedClaim] = Field(min_length=1)
    suggested_fix: str = Field(min_length=1)
    postmortem_draft: str = ""
    jira_summary: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("claims")
    @classmethod
    def _one_root_cause(cls, claims):
        roots = [c for c in claims if c.kind == "root_cause"]
        if len(roots) != 1:
            raise ValueError(f"exactly one root_cause claim required, got {len(roots)}")
        if len({c.claim_id for c in claims}) != len(claims):
            raise ValueError("claim_id values must be unique")
        return claims


class CriticItem(BaseModel):
    claim_id: str
    verdict: CriticVerdict
    reason: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class CriticOutput(BaseModel):
    verdicts: list[CriticItem]


# ---------------------------------------------------------------------------
# Prompt context: short aliases so citations are checkable
# ---------------------------------------------------------------------------
def aliases(state: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    evidence = {f"E{i}": e for i, e in enumerate(
        [e for e in state.get("evidence_collected") or [] if e.get("evidence_id")], start=1)}
    past = {f"P{i}": c for i, c in enumerate((state.get("reranked_candidates") or [])[:5], start=1)}
    return evidence, past


def _verdict_lines(state: dict) -> str:
    lines = [f"  {v['hypothesis_id']} ({v['label']}): {v['verdict'].upper()} — {v['reason']}"
             for v in state.get("hypothesis_verdicts") or []]
    return "\n".join(lines) or "  none"


def _evidence_lines(evidence: dict[str, dict]) -> str:
    lines = [f"  {alias} [{e.get('hypothesis_key')}, {e.get('outcome')}] {e.get('source_reference')}: {e.get('content')}"
             for alias, e in evidence.items()]
    return "\n".join(lines) or "  none"


def _past_lines(past: dict[str, dict]) -> str:
    lines = [f"  {alias} ({c.get('source') or 'past incident'}): {(c.get('content') or '')[:350]}" for alias, c in past.items()]
    return "\n".join(lines) or "  none"


def _feedback(state: dict) -> str:
    rejected = [v for v in state.get("critic_verdicts") or [] if v["verdict"] != "supported"]
    if not rejected:
        return ""
    lines = "\n".join(f"  {v['claim_id']} was {v['verdict'].upper()}: {v['reason']}" for v in rejected)
    return ("\nREVISION REQUIRED. A reviewer rejected these claims in your previous draft. Remove or correct them; "
            f"do not repeat them:\n{lines}\n")


def proposer_prompt(state: dict, error_context: str = "") -> str:
    row = state["recon_row"]
    evidence, past = aliases(state)
    prompt = template("proposer.md").format(
        sf_object=row.get("sf_object"), sf_field=row.get("sf_field"), sf_record_id=row.get("sf_record_id"),
        discrepancy_type=row.get("discrepancy_type"), severity=row.get("severity"),
        integration_name=row.get("integration_name") or "unknown",
        graph_status=state.get("graph_status"), root_cause_category=state.get("root_cause_category") or "none",
        graph_root_cause=state.get("graph_root_cause") or "none (no hypothesis confirmed)",
        verdict_lines=_verdict_lines(state), evidence_lines=_evidence_lines(evidence), past_lines=_past_lines(past),
        feedback=_feedback(state), categories=", ".join(CATEGORIES),
    )
    if error_context:
        prompt += f"\n\nYour previous output was invalid: {error_context}\nReturn corrected JSON only."
    return prompt


def critic_prompt(state: dict, claims: list[dict], error_context: str = "") -> str:
    evidence, _ = aliases(state)
    claim_lines = "\n".join(
        f"  {c['claim_id']} [{c['kind']}, {c['status']}] cites {', '.join(c['cited_aliases']) or 'nothing'}: {c['text']}"
        for c in claims)
    prompt = template("critic.md").format(
        graph_status=state.get("graph_status"), root_cause_category=state.get("root_cause_category") or "none",
        verdict_lines=_verdict_lines(state), evidence_lines=_evidence_lines(evidence), claim_lines=claim_lines,
    )
    if error_context:
        prompt += f"\n\nYour previous output was invalid: {error_context}\nReturn corrected JSON only."
    return prompt


def _parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group())


def _call(agent: str, model: str, prompt: str, attempt: int) -> tuple[str | None, dict, Exception | None]:
    """One LLM call; returns (raw text, log entry, exception)."""
    try:
        raw, in_tok, out_tok, latency = _call_llm(prompt, model)
        return raw, {"agent": agent, "model": model, "attempt": attempt,
                     "input_tokens": in_tok, "output_tokens": out_tok, "latency_ms": latency}, None
    except Exception as exc:  # logged, never swallowed: the caller decides what it means
        return None, {"agent": agent, "model": model, "attempt": attempt, "input_tokens": 0, "output_tokens": 0,
                      "latency_ms": 0, "error": f"{type(exc).__name__}: {exc}"[:300]}, exc


# ---------------------------------------------------------------------------
# Proposer
# ---------------------------------------------------------------------------
def _resolve(claim: ProposedClaim, evidence: dict, past: dict) -> dict:
    """Map aliases to real IDs; unknown aliases are kept visibly so the critic flags them."""
    return {
        **claim.model_dump(),
        "cited_aliases": claim.evidence_ids + claim.similar_incident_ids,
        "evidence_ids": [evidence[a]["evidence_id"] if a in evidence else f"UNKNOWN:{a}" for a in claim.evidence_ids],
        "similar_incident_ids": [str(past[a].get("id")) if a in past else f"UNKNOWN:{a}" for a in claim.similar_incident_ids],
    }


def _degraded_proposal(text: str) -> dict:
    return {"claims": [{"claim_id": "C1", "kind": "root_cause", "status": "hypothesis", "category": None, "text": text,
                        "evidence_ids": [], "similar_incident_ids": [], "hypothesis_ids": [], "cited_aliases": []}],
            "suggested_fix": "Manual investigation required.", "postmortem_draft": "",
            "jira_summary": "RCA: manual review required", "confidence": 0.0}


def run_proposer(state: dict, config: AgentConfig) -> dict:
    model = config.synthesis_llm
    evidence, past = aliases(state)
    calls: list[dict] = []
    error_context = ""
    for attempt in range(1, _ATTEMPTS_PER_CALL + 1):
        raw, call, exc = _call("proposer", model, proposer_prompt(state, error_context), attempt)
        calls.append(call)
        if exc is not None:
            if _is_api_unavailable(exc):
                sentry_sdk.capture_exception(exc)
                return _proposer_out(state, _degraded_proposal("Analysis temporarily unavailable. Please try again shortly."),
                                     "api_unavailable", calls, ["llm_unavailable"])
            error_context = str(exc)
            continue
        try:
            parsed = ProposalOutput.model_validate(_parse_json(raw))
        except (ValueError, ValidationError) as err:
            error_context = str(err)[:500]
            call["error"] = f"invalid output: {error_context}"[:300]
            continue
        proposal = {**parsed.model_dump(), "claims": [_resolve(c, evidence, past) for c in parsed.claims]}
        return _proposer_out(state, proposal, "ok", calls, [])
    return _proposer_out(state, _degraded_proposal("Root cause undetermined: the model produced no valid explanation."),
                         "invalid_output", calls, ["proposer_invalid_output"])


def _proposer_out(state, proposal, status, calls, reasons) -> dict:
    return {
        "proposal": {**proposal, "prompt_versions": versions(*PROMPTS)},
        "proposal_count": (state.get("proposal_count") or 0) + 1,
        "synthesis_status": status,
        "llm_calls": calls,
        "total_latency_ms": sum(c["latency_ms"] for c in calls),
        "review_reasons": reasons,
    }


# ---------------------------------------------------------------------------
# Critic: deterministic stage
# ---------------------------------------------------------------------------
_PLACEHOLDER = re.compile(r"\[(?:DATE|NAME|TIME|ID|RECORD|VALUE|TBD)[^\]]*\]|\bTBD\b|\bTODO\b|\bXXX\b", re.IGNORECASE)


def deterministic_checks(claim: dict, state: dict) -> tuple[str, str] | None:
    """First failing rule for a claim as (verdict, reason), or None if it passes."""
    evidence_by_id = {e["evidence_id"]: e for e in state.get("evidence_collected") or [] if e.get("evidence_id")}
    verdicts = {v["hypothesis_id"]: v["verdict"] for v in state.get("hypothesis_verdicts") or []}
    status = state.get("graph_status")
    is_cause = claim["kind"] in ("root_cause", "mechanism")

    unknown = [c for c in claim["evidence_ids"] + claim["similar_incident_ids"] if str(c).startswith("UNKNOWN:")]
    if unknown:
        return "unsupported", f"cites {', '.join(u.split(':', 1)[1] for u in unknown)}, which does not exist"
    if _PLACEHOLDER.search(claim["text"]):
        return "unsupported", "contains a template placeholder instead of a fact"
    refuted = [h for h in claim.get("hypothesis_ids") or [] if verdicts.get(h) == "refuted"]
    if refuted:
        return "contradicted", f"relies on {', '.join(refuted)}, which the evidence refuted"
    if claim["kind"] == "root_cause":
        if status == "exhausted" and claim["status"] != "hypothesis":
            return "contradicted", "no hypothesis was confirmed, so the root cause can only be stated as a hypothesis"
        if status == "confirmed" and claim.get("category") != state.get("root_cause_category"):
            return "contradicted", (f"root-cause category {claim.get('category')} conflicts with the confirmed "
                                    f"{state.get('root_cause_category')}")
        if status == "confirmed" and not claim["evidence_ids"]:
            return "unsupported", "the root cause cites no evidence"
    if is_cause and claim["status"] == "established":
        for eid in claim["evidence_ids"]:
            outcome = (evidence_by_id.get(eid) or {}).get("outcome")
            if outcome == "refutes":
                return "contradicted", f"cites evidence that refutes it ({evidence_by_id[eid].get('source_reference')})"
            if outcome in ("error", "skipped"):
                return "unsupported", "cites a check that did not run as support"
    return None


# ---------------------------------------------------------------------------
# Critic: deterministic + LLM
# ---------------------------------------------------------------------------
def run_critic(state: dict, config: AgentConfig) -> dict:
    proposal = state.get("proposal") or {}
    claims = proposal.get("claims") or []
    if state.get("synthesis_status") != "ok":
        return {"critic_verdicts": [], "critic_status": "skipped"}

    verdicts: dict[str, dict] = {}
    for claim in claims:
        failed = deterministic_checks(claim, state)
        if failed:
            verdicts[claim["claim_id"]] = {"claim_id": claim["claim_id"], "verdict": failed[0], "reason": failed[1],
                                           "stage": "deterministic", "evidence_ids": []}

    remaining = [c for c in claims if c["claim_id"] not in verdicts]
    calls: list[dict] = []
    status = "ok"
    if remaining:
        status = "unavailable"
        error_context = ""
        for attempt in range(1, _ATTEMPTS_PER_CALL + 1):
            raw, call, exc = _call("critic", config.critic_llm, critic_prompt(state, remaining, error_context), attempt)
            calls.append(call)
            if exc is not None:
                if _is_api_unavailable(exc):
                    sentry_sdk.capture_exception(exc)
                error_context = str(exc)[:300]
                continue
            try:
                parsed = CriticOutput.model_validate(_parse_json(raw))
                expected = {c["claim_id"] for c in remaining}
                got = [v.claim_id for v in parsed.verdicts]
                if sorted(got) != sorted(expected):
                    raise ValueError(f"verdicts must cover exactly claims {sorted(expected)}, got {got}")
            except (ValueError, ValidationError) as err:
                error_context = str(err)[:500]
                call["error"] = f"invalid output: {error_context}"[:300]
                continue
            evidence, _ = aliases(state)
            for v in parsed.verdicts:
                verdicts[v.claim_id] = {"claim_id": v.claim_id, "verdict": v.verdict, "reason": v.reason, "stage": "llm",
                                        "evidence_ids": [evidence[a]["evidence_id"] for a in v.evidence_ids if a in evidence]}
            status = "ok"
            break

    ordered = [verdicts[c["claim_id"]] for c in claims if c["claim_id"] in verdicts]
    return {"critic_verdicts": ordered, "critic_status": status, "llm_calls": calls,
            "total_latency_ms": sum(c["latency_ms"] for c in calls)}


# ---------------------------------------------------------------------------
# Judge: deterministic rules only
# ---------------------------------------------------------------------------
def decide(state: dict) -> tuple[str, list[str]]:
    """(accept | revise | escalate, review reasons the judge adds)."""
    if state.get("synthesis_status") != "ok":
        return "escalate", []  # proposer already added llm_unavailable / proposer_invalid_output
    if state.get("critic_status") != "ok":
        return "escalate", ["critic_unavailable"]
    rejected = [v for v in state.get("critic_verdicts") or [] if v["verdict"] != "supported"]
    if rejected:
        revisions = (state.get("proposal_count") or 1) - 1
        return ("revise", []) if revisions < MAX_REVISIONS else ("escalate", ["critic_rejected"])
    if state.get("graph_status") != "confirmed":
        # A faithful explanation of an unconfirmed diagnosis is still unconfirmed; the
        # graph already added its review reason (no_hypothesis_confirmed / iteration_limit).
        return "escalate", []
    return "accept", []


def run_judge(state: dict) -> dict:
    decision, reasons = decide(state)
    if decision == "revise":
        return {"judge_decision": "revise"}

    proposal = state.get("proposal") or _degraded_proposal("No explanation was produced.")
    verdict_by_claim = {v["claim_id"]: v for v in state.get("critic_verdicts") or []}
    claims = [{**c, "critic": verdict_by_claim.get(c["claim_id"])} for c in proposal["claims"]]
    root = next(c for c in claims if c["kind"] == "root_cause")
    confidence = float(proposal.get("confidence") or 0.0)
    if confidence < 0.75:
        reasons.append("low_confidence")  # non-negotiable #3

    # Non-negotiable #1 and the graph's own completion are re-checked here, at the end.
    tested = set(state.get("hypotheses_tested") or [])
    covered = {e.get("hypothesis_key") for e in state.get("evidence_collected") or []}
    if tested and not tested.issubset(covered):
        reasons.append("missing_evidence")
    if state.get("graph_status") not in ("confirmed", "exhausted", "unknown_type"):
        reasons.append("iteration_limit")

    cited_evidence = list(dict.fromkeys(e for c in claims for e in c["evidence_ids"] if not str(e).startswith("UNKNOWN:")))
    cited_past = list(dict.fromkeys(p for c in claims for p in c["similar_incident_ids"] if not str(p).startswith("UNKNOWN:")))
    rca_output = {
        "root_cause": root["text"],
        "confidence": confidence,
        "evidence_ids": cited_evidence,
        "similar_past_incidents": cited_past,
        "suggested_fix": proposal.get("suggested_fix") or "",
        "postmortem_draft": proposal.get("postmortem_draft") or "",
        "jira_summary": proposal.get("jira_summary") or "",
        "requires_human_review": bool(reasons) or decision == "escalate",
        "claims": claims,
        "judge_decision": decision,
        "revision_count": (state.get("proposal_count") or 1) - 1,
        "prompt_versions": proposal.get("prompt_versions") or {},
    }
    return {
        "judge_decision": decision,
        "rca_output": rca_output,
        "root_cause": root["text"],
        "confidence": confidence,
        "review_reasons": reasons,
    }
