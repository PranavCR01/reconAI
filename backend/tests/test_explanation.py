"""Issue #11: proposer / critic / judge."""
import asyncio
import itertools
import json

import pytest

from backend.agents.explanation import MAX_REVISIONS, decide, deterministic_checks
from backend.config import AgentConfig
from backend.graph.recon_graph import build_graph
from backend.models.entities import DiscrepancyType, ReconRow
from backend.models.state import initial_state, review_reasons
from backend.prompts import content_hash, recorded_versions
from backend.tests.fakes.fake_llm import api_status_error, critic_reply, proposal_reply
from backend.tests.helpers import CRITIC_PROMPT, SYNTHESIS_PROMPT as PROPOSER_PROMPT, run_sample

CONFIG = AgentConfig()


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _row(record_id, discrepancy, sf_object="Contact", sf_field="TaxId__c"):
    return ReconRow(sf_object=sf_object, sf_field=sf_field, sf_record_id=record_id, sf_value="x", db2_table="T",
                    db2_column="C", db2_value=None if discrepancy == "NULL_DOWNSTREAM" else "y",
                    discrepancy_type=DiscrepancyType(discrepancy))


def _run(graph, row):
    return graph.invoke(initial_state(row.model_dump(mode="json")))


def _agents(final, name):
    return [c for c in final["llm_calls"] if c["agent"] == name]


# ---------------------------------------------------------------------------
# Judge truth table (exhaustive)
# ---------------------------------------------------------------------------
CRITIC_RESULTS = {
    "all_supported": ("ok", ["supported", "supported"]),
    "some_unsupported": ("ok", ["supported", "unsupported"]),
    "some_contradicted": ("ok", ["contradicted", "supported"]),
    "critic_error": ("unavailable", []),
}


@pytest.mark.parametrize("graph_status,critic,revisions", list(itertools.product(
    ["confirmed", "exhausted"], CRITIC_RESULTS, [0, 1])))
def test_judge_truth_table(graph_status, critic, revisions):
    critic_status, verdicts = CRITIC_RESULTS[critic]
    state = {"synthesis_status": "ok", "graph_status": graph_status, "critic_status": critic_status,
             "proposal_count": revisions + 1,
             "critic_verdicts": [{"claim_id": f"C{i}", "verdict": v, "reason": "r"} for i, v in enumerate(verdicts)]}
    decision, reasons = decide(state)
    if critic == "critic_error":
        assert (decision, reasons) == ("escalate", ["critic_unavailable"])
    elif critic == "all_supported":
        assert (decision, reasons) == (("accept", []) if graph_status == "confirmed" else ("escalate", []))
    elif revisions < MAX_REVISIONS:
        assert (decision, reasons) == ("revise", [])
    else:
        assert (decision, reasons) == ("escalate", ["critic_rejected"])


@pytest.mark.parametrize("status", ["api_unavailable", "invalid_output"])
def test_judge_escalates_when_proposer_failed(status):
    assert decide({"synthesis_status": status, "graph_status": "confirmed"}) == ("escalate", [])


# ---------------------------------------------------------------------------
# Deterministic critic: one test per rule
# ---------------------------------------------------------------------------
STATE = {
    "graph_status": "confirmed", "root_cause_category": "FLS_STRIPPED",
    "hypothesis_verdicts": [{"hypothesis_id": "H1", "verdict": "refuted"}, {"hypothesis_id": "H3a", "verdict": "confirmed"}],
    "evidence_collected": [
        {"evidence_id": "ev-fls", "outcome": "supports", "source_reference": "sf-fls://x"},
        {"evidence_id": "ev-db2", "outcome": "refutes", "source_reference": "db2://x"},
        {"evidence_id": "ev-err", "outcome": "error", "source_reference": "tool://x"},
    ],
}


def _claim(**kw):
    base = {"claim_id": "C1", "kind": "root_cause", "status": "established", "category": "FLS_STRIPPED",
            "text": "FLS strips the field.", "evidence_ids": ["ev-fls"], "similar_incident_ids": [], "hypothesis_ids": ["H3a"]}
    return {**base, **kw}


@pytest.mark.parametrize("claim,state_override,expected", [
    (_claim(), {}, None),
    (_claim(evidence_ids=["UNKNOWN:E9"]), {}, "unsupported"),
    (_claim(similar_incident_ids=["UNKNOWN:P7"]), {}, "unsupported"),
    (_claim(text="On [DATE] the field was cleared."), {}, "unsupported"),
    (_claim(text="Fix TBD."), {}, "unsupported"),
    (_claim(hypothesis_ids=["H1"]), {}, "contradicted"),
    (_claim(category="DELIVERY_GAP"), {}, "contradicted"),
    (_claim(evidence_ids=[]), {}, "unsupported"),
    (_claim(kind="mechanism", category=None, evidence_ids=["ev-db2"], hypothesis_ids=[]), {}, "unsupported"),
    (_claim(kind="mechanism", category=None, evidence_ids=["ev-fls", "ev-db2"], hypothesis_ids=[]), {}, None),
    (_claim(kind="mechanism", category=None, evidence_ids=["ev-err"], hypothesis_ids=[]), {}, "unsupported"),
    (_claim(kind="context", category=None, evidence_ids=["ev-db2"], hypothesis_ids=[],
            text="DB2 never held a value, ruling out an overwrite."), {}, None),
    (_claim(status="established", category=None, hypothesis_ids=[]), {"graph_status": "exhausted"}, "contradicted"),
    (_claim(status="hypothesis", category=None, hypothesis_ids=[], evidence_ids=[]), {"graph_status": "exhausted"}, None),
], ids=["clean", "fake_evidence", "fake_past_incident", "placeholder_date", "placeholder_tbd", "refuted_hypothesis",
        "category_mismatch", "root_cites_nothing", "cites_only_refuting_evidence", "excludes_alternative_with_refutation",
        "cites_failed_check",
        "context_may_cite_refuting", "exhausted_stated_as_fact", "exhausted_as_hypothesis"])
def test_deterministic_rules(claim, state_override, expected):
    result = deterministic_checks(claim, {**STATE, **state_override})
    assert (result[0] if result else None) == expected, result


# ---------------------------------------------------------------------------
# Integration with the scripted model
# ---------------------------------------------------------------------------
def _cdc_claim_proposal(tag_hypothesis: bool):
    def respond(prompt, model):
        claims = json.loads(proposal_reply(prompt))["claims"]
        claims.append({"claim_id": "C3", "kind": "mechanism", "status": "established", "category": None,
                       "text": "Two CDC events were dropped by the pipeline.", "evidence_ids": [],
                       "similar_incident_ids": [], "hypothesis_ids": ["HVM3"] if tag_hypothesis else []})
        return json.dumps({**json.loads(proposal_reply(prompt)), "claims": claims})
    return respond


def test_taxid_replay_caught_deterministically(graph, scenarios, llm):
    """Production incident 15a187b6: every hypothesis refuted (incl. CDC), yet the text blamed dropped CDC events."""
    scenarios.add("PJ-taxid", "NO_FAULT_FOUND")
    llm.respond(PROPOSER_PROMPT, _cdc_claim_proposal(tag_hypothesis=True))
    final = _run(graph, _row("PJ-taxid", "VALUE_MISMATCH"))
    assert final["graph_status"] == "exhausted"
    bad = [v for v in final["critic_verdicts"] if v["claim_id"] == "C3"][0]
    assert bad["verdict"] == "contradicted" and bad["stage"] == "deterministic" and "HVM3" in bad["reason"]
    assert final["judge_decision"] == "escalate" and len(_agents(final, "proposer")) == 2
    assert {"critic_rejected", "no_hypothesis_confirmed"} <= set(review_reasons(final))


def test_taxid_replay_caught_by_llm_critic(graph, scenarios, llm):
    """Same contradiction without a hypothesis tag: only the LLM critic can catch it."""
    scenarios.add("PJ-taxid2", "NO_FAULT_FOUND")
    llm.respond(PROPOSER_PROMPT, _cdc_claim_proposal(tag_hypothesis=False))
    llm.respond(CRITIC_PROMPT, lambda p, m: critic_reply(p, {"C3": ("contradicted", "HVM3 refuted CDC as a cause")}))
    final = _run(graph, _row("PJ-taxid2", "VALUE_MISMATCH"))
    bad = [v for v in final["critic_verdicts"] if v["claim_id"] == "C3"][0]
    assert bad["verdict"] == "contradicted" and bad["stage"] == "llm"
    assert final["judge_decision"] == "escalate" and "critic_rejected" in review_reasons(final)


def test_hmr1_replay_category_mismatch(graph, scenarios, llm):
    """Production incident 88d64fee: the diagnosis said one cause, the summary another."""
    scenarios.add("PJ-hmr", "DELIVERY_GAP")
    llm.respond(PROPOSER_PROMPT, lambda p, m: proposal_reply(p).replace('"category": "DELIVERY_GAP"', '"category": "FLS_STRIPPED"'))
    final = _run(graph, _row("PJ-hmr", "MISSING_RECORD", sf_object="FinancialAccount__c", sf_field="BalanceAmt__c"))
    root = [v for v in final["critic_verdicts"] if v["claim_id"] == "C1"][0]
    assert root["verdict"] == "contradicted" and "FLS_STRIPPED" in root["reason"]
    assert final["judge_decision"] == "escalate"


def test_revision_fixes_the_draft(graph, scenarios, llm):
    scenarios.add("PJ-fix", "FLS_STRIPPED")
    # First draft cites evidence that doesn't exist; the revision (fake default) is clean.
    llm.respond(PROPOSER_PROMPT, lambda p, m: proposal_reply(p).replace('"evidence_ids": ["E', '"evidence_ids": ["E99", "E', 1), times=1)
    final = _run(graph, _row("PJ-fix", "NULL_DOWNSTREAM", sf_field="Phone"))
    assert final["judge_decision"] == "accept" and final["rca_output"]["revision_count"] == 1
    assert len(_agents(final, "proposer")) == 2
    assert "REVISION REQUIRED" in llm.calls_matching(PROPOSER_PROMPT)[-1]["prompt"], "critic findings fed back"
    assert not set(review_reasons(final)) & {"critic_rejected", "critic_unavailable"}


def test_revision_limit_and_call_budget(graph, scenarios, llm):
    scenarios.add("PJ-limit", "FLS_STRIPPED")
    llm.respond(CRITIC_PROMPT, lambda p, m: critic_reply(p, {"C2": ("unsupported", "the fix is not backed by evidence")}))
    final = _run(graph, _row("PJ-limit", "NULL_DOWNSTREAM", sf_field="Phone"))
    assert final["judge_decision"] == "escalate" and "critic_rejected" in review_reasons(final)
    assert final["rca_output"]["revision_count"] == MAX_REVISIONS
    explanation_calls = _agents(final, "proposer") + _agents(final, "critic")
    assert len(explanation_calls) == 4, "proposer x2 + critic x2 when outputs are valid"


def test_critic_outage_never_auto_accepts(graph, scenarios, llm):
    scenarios.add("PJ-outage", "FLS_STRIPPED")
    llm.fail(CRITIC_PROMPT, api_status_error(529))
    final = _run(graph, _row("PJ-outage", "NULL_DOWNSTREAM", sf_field="Phone"))
    assert final["critic_status"] == "unavailable" and final["judge_decision"] == "escalate"
    assert "critic_unavailable" in review_reasons(final)
    assert all("error" in c for c in _agents(final, "critic"))


def test_critic_outage_does_not_break_the_stream(client, sample_csv_text, llm):
    llm.fail(CRITIC_PROMPT, api_status_error(529))
    run_id, events = run_sample(client, sample_csv_text)
    assert events[-1]["event"] == "done" and not [e for e in events if e["event"] == "error"]
    for inc in client.get(f"/api/v1/recon/runs/{run_id}").json()["incidents"]:
        assert inc["requires_human_review"] and "critic_unavailable" in inc["review_reasons"]


def test_invalid_critic_output_is_retried_then_escalated(graph, scenarios, llm):
    scenarios.add("PJ-badcritic", "FLS_STRIPPED")
    llm.respond(CRITIC_PROMPT, '{"verdicts": [{"claim_id": "C1", "verdict": "fine"}]}')
    final = _run(graph, _row("PJ-badcritic", "NULL_DOWNSTREAM", sf_field="Phone"))
    critic_calls = _agents(final, "critic")
    assert len(critic_calls) == 2 and all("invalid output" in c["error"] for c in critic_calls)
    assert "critic_unavailable" in review_reasons(final)


def test_two_root_causes_is_a_schema_violation(graph, scenarios, llm):
    scenarios.add("PJ-schema", "FLS_STRIPPED")
    def two_roots(prompt, model):
        body = json.loads(proposal_reply(prompt))
        body["claims"][1]["kind"] = "root_cause"
        return json.dumps(body)
    llm.respond(PROPOSER_PROMPT, two_roots, times=1)
    final = _run(graph, _row("PJ-schema", "NULL_DOWNSTREAM", sf_field="Phone"))
    calls = _agents(final, "proposer")
    assert "exactly one root_cause" in calls[0]["error"] and "error" not in calls[1]
    assert "exactly one root_cause" in llm.calls_matching(PROPOSER_PROMPT)[1]["prompt"], "error context fed back"
    assert final["judge_decision"] == "accept"


def test_proposer_invalid_twice_escalates(graph, scenarios, llm):
    scenarios.add("PJ-nojson", "FLS_STRIPPED")
    llm.respond(PROPOSER_PROMPT, "no json here")
    final = _run(graph, _row("PJ-nojson", "NULL_DOWNSTREAM", sf_field="Phone"))
    assert final["synthesis_status"] == "invalid_output" and final["judge_decision"] == "escalate"
    assert "proposer_invalid_output" in review_reasons(final) and final["critic_status"] == "skipped"


# ---------------------------------------------------------------------------
# Whole-benchmark properties
# ---------------------------------------------------------------------------
def test_nothing_is_complete_unless_the_judge_accepted(storage, graph, ground_truth, scenarios):
    from backend.main import _analyze_row
    from backend.tests.helpers import ground_truth_row

    for inc in ground_truth:
        result = asyncio.run(_analyze_row(ground_truth_row(inc), CONFIG, graph, storage, session_id="judge-prop"))
        i = result["incident"]
        if not i.requires_human_review:
            assert i.judge_decision == "accept", inc["id"]
            root = next(c for c in i.claims if c["kind"] == "root_cause")
            assert root["critic"]["verdict"] == "supported" and root["category"] == i.root_cause_category
        if i.judge_decision == "escalate":
            assert i.requires_human_review, inc["id"]


def test_accepted_claims_cite_real_evidence(storage, graph, ground_truth, fake_db):
    from backend.main import _analyze_row
    from backend.tests.helpers import ground_truth_row

    result = asyncio.run(_analyze_row(ground_truth_row(ground_truth[0]), CONFIG, graph, storage, session_id="cite"))
    saved_ids = {r["id"] for r in fake_db.rows("rca_evidence") if r["incident_id"] == result["incident_id"]}
    for claim in result["incident"].claims:
        assert set(claim["evidence_ids"]) <= saved_ids, "every cited evidence id is a persisted evidence row"


# ---------------------------------------------------------------------------
# Prompt versioning
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("name", ["proposer.md", "critic.md"])
def test_prompt_changes_require_a_version_update(name):
    assert content_hash(name) == recorded_versions()[name], (
        f"{name} changed: run the hash update and commit backend/prompts/VERSIONS.json with the prompt change")


def test_incident_records_prompt_versions(storage, graph, ground_truth):
    from backend.main import _analyze_row
    from backend.tests.helpers import ground_truth_row

    inc = asyncio.run(_analyze_row(ground_truth_row(ground_truth[1]), CONFIG, graph, storage, session_id="pv"))["incident"]
    assert inc.prompt_versions == recorded_versions()
