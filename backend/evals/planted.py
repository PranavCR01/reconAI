"""Planted-claim set for measuring the critic.

For each analyzed incident whose graph confirmed a cause, build one clean draft and one
draft per defect type. A defective draft differs from the clean one only by the injected
defect. Drafts are written in alias space (E#/P#), exactly as the proposer writes them,
then resolved and reviewed by the real critic (deterministic stage, then the LLM).

Defects and which stage is expected to catch them:
  fabricated_evidence      cites E99, which does not exist                   deterministic
  fabricated_past_incident cites P9, which does not exist                    deterministic
  wrong_category           root cause names another category                 deterministic
  contradicts_refuted      root cause relies on a refuted hypothesis         deterministic
  placeholder_text         fix contains [DATE]/[NAME] template text          deterministic
  unsupported_mechanism    adds a plausible mechanism no evidence supports   LLM only
"""
from __future__ import annotations

import hashlib
import json
import re

from backend.agents.explanation import ProposedClaim, _resolve, aliases
from backend.graph.hypotheses import CATEGORIES

DEFECTS = ("fabricated_evidence", "fabricated_past_incident", "wrong_category", "contradicts_refuted",
           "placeholder_text", "unsupported_mechanism")
EXPECTED_STAGE = {d: "deterministic" for d in DEFECTS} | {"unsupported_mechanism": "llm"}

_FABRICATED_MECHANISM = {
    # A cause from a different family, stated as fact and citing the real supporting evidence.
    "DOWNSTREAM_OVERWRITE": "The integration user lost field-level read access to {field} in the last release.",
}
_DEFAULT_MECHANISM = "A nightly DB2 purge job truncated the target table at 02:00, which removed the {field} value."


def _clean(state: dict) -> list[dict]:
    evidence, _ = aliases(state)
    confirmed = next(v for v in state["hypothesis_verdicts"] if v["verdict"] == "confirmed")
    supporting = [a for a, e in evidence.items() if e.get("hypothesis_key") == confirmed["hypothesis_id"]
                  and e.get("outcome") == "supports"]
    row = state["recon_row"]
    return [
        {"claim_id": "C1", "kind": "root_cause", "status": "established", "category": state["root_cause_category"],
         "text": state.get("graph_root_cause") or confirmed["reason"], "evidence_ids": supporting,
         "similar_incident_ids": [], "hypothesis_ids": [confirmed["hypothesis_id"]]},
        {"claim_id": "C2", "kind": "fix", "status": "established", "category": None,
         "text": f"Correct the cause identified above and backfill {row['sf_object']}.{row['sf_field']} for "
                 f"record {row['sf_record_id']}.",
         "evidence_ids": [], "similar_incident_ids": [], "hypothesis_ids": []},
    ]


def applicable(state: dict) -> bool:
    return state.get("graph_status") == "confirmed"


def drafts(state: dict) -> dict[str, list[dict] | None]:
    """{'clean': claims, defect: claims or None when the defect can't apply to this incident}."""
    clean = _clean(state)
    row = state["recon_row"]
    field = f"{row['sf_object']}.{row['sf_field']}"
    out: dict[str, list[dict] | None] = {"clean": clean}

    def variant(change) -> list[dict]:
        claims = json.loads(json.dumps(clean))
        change(claims)
        return claims

    out["fabricated_evidence"] = variant(lambda c: c[0]["evidence_ids"].append("E99"))
    out["fabricated_past_incident"] = variant(lambda c: c[0]["similar_incident_ids"].append("P9"))
    others = [cat for cat in CATEGORIES if cat != state["root_cause_category"]]
    wrong = others[sum(map(ord, row["sf_record_id"])) % len(others)]
    out["wrong_category"] = variant(lambda c: c[0].update(category=wrong))
    refuted = [v["hypothesis_id"] for v in state["hypothesis_verdicts"] if v["verdict"] == "refuted"]
    out["contradicts_refuted"] = variant(lambda c: c[0]["hypothesis_ids"].append(refuted[0])) if refuted else None
    out["placeholder_text"] = variant(lambda c: c[1].update(text=c[1]["text"] + " Change deployed on [DATE] by [NAME]."))
    mechanism = _FABRICATED_MECHANISM.get(state["root_cause_category"], _DEFAULT_MECHANISM).format(field=field)
    out["unsupported_mechanism"] = variant(lambda c: c.append(
        {"claim_id": "C3", "kind": "mechanism", "status": "established", "category": None, "text": mechanism,
         "evidence_ids": list(c[0]["evidence_ids"]), "similar_incident_ids": [], "hypothesis_ids": []}))
    return out


def critic_state(state: dict, claims: list[dict]) -> dict:
    """The state the critic sees for a draft: the incident's real evidence plus the draft."""
    evidence, past = aliases(state)
    resolved = [_resolve(ProposedClaim(**c), evidence, past) for c in claims]
    proposal = {"claims": resolved, "suggested_fix": resolved[-1]["text"], "postmortem_draft": "",
                "jira_summary": "RCA", "confidence": 0.9}
    return {**state, "proposal": proposal, "synthesis_status": "ok", "critic_verdicts": [], "proposal_count": 1}


_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")


def draft_set_hash(per_incident: dict[str, dict]) -> str:
    """Hash of every generated draft, to show the set is reproducible. Simulator timestamps
    (relative to the time of the run) are masked; everything else is hashed as generated."""
    canonical = _TIMESTAMP.sub("<ts>", json.dumps(per_incident, sort_keys=True, separators=(",", ":")))
    return hashlib.sha256(canonical.encode()).hexdigest()
