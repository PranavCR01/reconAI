"""Issue #8: node-owned state, append-only review reasons, persisted LLM call log."""
import asyncio
import itertools

import pytest

from backend.config import AgentConfig
from backend.graph.recon_graph import build_graph
from backend.models.state import (
    APPEND_ONLY, OWNERS, REVIEW_REASONS, StateOwnershipError, check_node_output, initial_state, review_reasons,
)
from backend.tests.fakes.fake_llm import api_status_error
from backend.tests.helpers import SYNTHESIS_PROMPT, ground_truth_row, synthesis_json

CONFIG = AgentConfig()


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _rows(ground_truth):
    return [ground_truth_row(i) for i in ground_truth]


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------
def test_every_node_writes_only_keys_it_owns(graph, ground_truth):
    """Diff every node's update on all 50 labeled incidents against the ownership map."""
    seen_nodes = set()
    for row in _rows(ground_truth):
        for step in graph.stream(initial_state(row.model_dump(mode="json")), stream_mode="updates"):
            for node, update in step.items():
                seen_nodes.add(node)
                foreign = set(update or {}) - OWNERS[node] - APPEND_ONLY
                assert not foreign, f"{row.sf_object}.{row.sf_field}: node {node} wrote {foreign}"
    assert seen_nodes == set(OWNERS), f"not every node ran: {seen_nodes}"


@pytest.mark.parametrize("node,update", [
    ("synthesis", {"current_hypothesis": "API_UNAVAILABLE"}),
    ("synthesis", {"requires_human_review": False}),
    ("ingestion", {"evidence_collected": []}),
    ("evidence", {"tool_calls": []}),
    ("rag_retrieval", {"rca_output": {}}),
])
def test_foreign_writes_are_rejected(node, update):
    with pytest.raises(StateOwnershipError):
        check_node_output(node, update)


def test_unknown_review_reason_rejected():
    with pytest.raises(StateOwnershipError):
        check_node_output("synthesis", {"review_reasons": ["looks_fine"]})


def test_append_only_keys_must_be_lists():
    with pytest.raises(StateOwnershipError):
        check_node_output("synthesis", {"llm_calls": {"agent": "synthesis"}})


# ---------------------------------------------------------------------------
# Review reasons: monotonic, and the only source of requires_human_review
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("confidence,outage", list(itertools.product([0.3, 0.74, 0.75, 0.95], [False, True])))
def test_review_reasons_never_shrink(graph, ground_truth, llm, confidence, outage):
    llm.synthesis_confidence = confidence
    if outage:
        llm.fail(SYNTHESIS_PROMPT, api_status_error())
    for row in _rows(ground_truth):
        previous: list[str] = []
        final = None
        for state in graph.stream(initial_state(row.model_dump(mode="json")), stream_mode="values"):
            current = state.get("review_reasons") or []
            assert current[: len(previous)] == previous, f"{row.sf_field}: reasons shrank {previous} -> {current}"
            assert set(current) <= REVIEW_REASONS
            previous = list(current)
            final = state

        reasons = review_reasons(final)
        hypothesis = final.get("current_hypothesis", "")
        if "exhausted" in hypothesis or hypothesis.startswith("H5"):
            assert "no_hypothesis_confirmed" in reasons, "graph flag must survive any LLM confidence"
        if outage:
            assert "llm_unavailable" in reasons and final["synthesis_status"] == "api_unavailable"
        elif confidence < 0.75:
            assert "low_confidence" in reasons  # non-negotiable #3
        else:
            assert "low_confidence" not in reasons


def test_incident_flag_is_derived_from_reasons(client, sample_csv_text, fake_db, llm):
    from backend.tests.helpers import run_sample

    for confidence in (0.6, 0.9):
        llm.synthesis_confidence = confidence
        run_id, _ = run_sample(client, sample_csv_text, params=f"?session_id=derive-{confidence}")
        for inc in client.get(f"/api/v1/recon/runs/{run_id}").json()["incidents"]:
            assert inc["requires_human_review"] == bool(inc["review_reasons"])
            assert (inc["status"] == "needs_review") == bool(inc["review_reasons"])
            if confidence < 0.75:
                assert "low_confidence" in inc["review_reasons"]


# ---------------------------------------------------------------------------
# Regression matrix from #4: graph flag x LLM confidence x outage
# ---------------------------------------------------------------------------
def _analyze(storage, graph, row, session="s"):
    from backend.main import _analyze_row

    return asyncio.run(_analyze_row(row, CONFIG, graph, storage, session_id=session))


def _rows_by_outcome(graph, ground_truth):
    exhausted = confirmed_high = None
    for row in _rows(ground_truth):
        final = graph.invoke(initial_state(row.model_dump(mode="json")))
        h = final.get("current_hypothesis", "")
        if exhausted is None and "exhausted" in h:
            exhausted = row
        # A confirmed row whose graph raises no review reason (so only the LLM can add one).
        if confirmed_high is None and "confirmed" in h and not set(review_reasons(final)) - {"low_confidence"}:
            confirmed_high = row
    assert exhausted and confirmed_high
    return exhausted, confirmed_high


@pytest.mark.parametrize("llm_confidence", [0.6, 0.9])
@pytest.mark.parametrize("outage", [False, True])
def test_review_matrix(storage, graph, ground_truth, llm, llm_confidence, outage):
    exhausted, confirmed = _rows_by_outcome(graph, ground_truth)
    llm.synthesis_confidence = llm_confidence
    if outage:
        llm.fail(SYNTHESIS_PROMPT, api_status_error())

    inc = _analyze(storage, graph, exhausted, session=f"ex-{llm_confidence}-{outage}")["incident"]
    assert inc.requires_human_review and "no_hypothesis_confirmed" in inc.review_reasons

    inc = _analyze(storage, graph, confirmed, session=f"ok-{llm_confidence}-{outage}")["incident"]
    expected_review = outage or llm_confidence < 0.75
    assert inc.requires_human_review == expected_review, inc.review_reasons
    if outage:
        assert inc.final_hypothesis == "API_UNAVAILABLE"


# ---------------------------------------------------------------------------
# LLM call log completeness and persistence
# ---------------------------------------------------------------------------
def test_every_attempt_is_logged_and_persisted(storage, graph, ground_truth, llm, fake_db):
    # Rules registered later take priority: the invalid reply answers attempt 1.
    llm.respond(SYNTHESIS_PROMPT, synthesis_json(0.9), times=1, input_tokens=222, output_tokens=33)
    llm.respond(SYNTHESIS_PROMPT, "this is not json", times=1, input_tokens=111, output_tokens=7)
    row = _rows(ground_truth)[0]
    inc = _analyze(storage, graph, row)["incident"]

    synth = [c for c in inc.llm_calls if c["agent"] == "synthesis"]
    assert [c["attempt"] for c in synth] == [1, 2]
    assert "invalid output" in synth[0]["error"] and "error" not in synth[1]
    assert (synth[0]["input_tokens"], synth[1]["input_tokens"]) == (111, 222)
    assert inc.total_tokens_used == sum(c["input_tokens"] + c["output_tokens"] for c in inc.llm_calls)

    saved = fake_db.rows("rca_incidents")[-1]
    assert saved["llm_calls"] == inc.llm_calls
    assert saved["review_reasons"] == inc.review_reasons


def test_failed_call_is_logged(storage, graph, ground_truth, llm):
    llm.fail(SYNTHESIS_PROMPT, api_status_error(529))
    inc = _analyze(storage, graph, _rows(ground_truth)[0])["incident"]
    synth = [c for c in inc.llm_calls if c["agent"] == "synthesis"]
    assert len(synth) == 1 and "APIStatusError" in synth[0]["error"]
    assert "llm_unavailable" in inc.review_reasons


def test_reranker_and_classifier_calls_logged(storage, graph, ground_truth, llm):
    from backend.seed.fsc_incidents import seed_artifacts
    from backend.models.entities import ReconRow

    asyncio.run(seed_artifacts(storage))
    row = _rows(ground_truth)[0]
    # Identical SF and DB2 values are ambiguous to the rules, which forces LLM classification.
    untyped = ReconRow(**{**row.model_dump(), "discrepancy_type": None, "sf_value": "same", "db2_value": "same"})
    inc = _analyze(storage, graph, untyped)["incident"]
    agents = [c["agent"] for c in inc.llm_calls]
    assert agents[0] == "ingestion" and "reranker" in agents and agents[-1] == "synthesis"
    assert len(inc.llm_calls) == len(llm.calls), "every fake LLM call must appear in the incident log"


# ---------------------------------------------------------------------------
# Cache round trip and legacy entries
# ---------------------------------------------------------------------------
COMPARED = ["hypotheses_tested", "hypotheses_ruled_out", "final_hypothesis", "confidence", "root_cause_summary",
            "suggested_fix", "postmortem_draft", "jira_summary", "requires_human_review", "review_reasons",
            "status", "total_tool_calls", "total_tokens_used", "latency_ms", "llm_calls"]


@pytest.mark.parametrize("index", [0, 5, 20, 35, 49])
def test_cache_round_trip_restores_the_same_incident(storage, graph, ground_truth, llm, index):
    row = _rows(ground_truth)[index]
    fresh = _analyze(storage, graph, row, session="rt")
    calls_after_fresh = len(llm.calls)
    cached = _analyze(storage, graph, row, session="rt")
    assert cached["cached"] and len(llm.calls) == calls_after_fresh, "second run must not call the LLM"
    a, b = fresh["incident"], cached["incident"]
    for field in COMPARED:
        assert getattr(a, field) == getattr(b, field), f"{field}: {getattr(a, field)!r} != {getattr(b, field)!r}"


def test_legacy_cache_entry_is_flagged(storage, graph, ground_truth, fake_db):
    from backend.cache.rca_cache import make_cache_key

    row = _rows(ground_truth)[0]
    legacy = {
        "root_cause": "x", "suggested_fix": "y", "postmortem_draft": "", "jira_summary": "j",
        "confidence": 0.9, "requires_human_review": False,
        "_hypotheses_tested": ["HVM1", "HVM2", "HVM3"], "_hypotheses_ruled_out": ["HVM1", "HVM2", "HVM3"],
        "_total_tool_calls": 3, "_total_tokens_used": 100, "_evidence": [],
    }
    fake_db.table("rca_cache").upsert({"cache_key": make_cache_key(row, "legacy"), "rca_output": legacy}).execute()
    inc = _analyze(storage, graph, row, session="legacy")["incident"]
    assert inc.requires_human_review and inc.review_reasons == ["no_hypothesis_confirmed"]


def test_legacy_cache_flag_without_other_reason(storage, graph, ground_truth, fake_db):
    from backend.cache.rca_cache import make_cache_key

    row = _rows(ground_truth)[1]
    legacy = {"root_cause": "x", "suggested_fix": "y", "jira_summary": "j", "confidence": 0.9,
              "requires_human_review": True, "_hypotheses_tested": ["H1"], "_hypotheses_ruled_out": []}
    fake_db.table("rca_cache").upsert({"cache_key": make_cache_key(row, "legacy2"), "rca_output": legacy}).execute()
    inc = _analyze(storage, graph, row, session="legacy2")["incident"]
    assert inc.review_reasons == ["legacy_cache_flag"]


# ---------------------------------------------------------------------------
# Schema check
# ---------------------------------------------------------------------------
def test_missing_columns_reported(storage, fake_db, monkeypatch):
    real_table = fake_db.table

    class _Rejecting:
        def __init__(self, q): self.q = q
        def select(self, column, **kw):
            if column == "llm_calls":
                raise RuntimeError("column rca_incidents.llm_calls does not exist")
            return self.q.select(column, **kw)

    monkeypatch.setattr(fake_db, "table", lambda name: _Rejecting(real_table(name)) if name == "rca_incidents" else real_table(name))
    missing = asyncio.run(storage.missing_columns({"rca_incidents": ["review_reasons", "llm_calls"]}))
    assert missing == ["rca_incidents.llm_calls"]
