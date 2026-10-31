"""Issue #9: evidence IDs, hypothesis linkage, persistence, similar past incidents."""
import asyncio

import pytest

import backend.agents.evidence as evidence_module
from backend.agents.evidence import OUTCOMES
from backend.config import AgentConfig
from backend.graph.recon_graph import build_graph
from backend.models.state import initial_state, review_reasons
from backend.tests.helpers import ground_truth_row, run_sample

CONFIG = AgentConfig()


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _analyze(storage, graph, row, session="s"):
    from backend.main import _analyze_row

    return asyncio.run(_analyze_row(row, CONFIG, graph, storage, session_id=session))


def _final_states(graph, ground_truth):
    for incident in ground_truth:
        row = ground_truth_row(incident)
        yield row, graph.invoke(initial_state(row.model_dump(mode="json")))


# ---------------------------------------------------------------------------
# Every record is complete and linked
# ---------------------------------------------------------------------------
def test_every_record_has_id_hypothesis_and_outcome(graph, ground_truth):
    ids = set()
    for row, final in _final_states(graph, ground_truth):
        for ev in final["evidence_collected"]:
            assert ev["evidence_id"] and ev["evidence_id"] not in ids, "evidence IDs must be unique"
            ids.add(ev["evidence_id"])
            assert ev["hypothesis_key"] in final["hypotheses_tested"], (row.sf_field, ev["hypothesis_key"])
            assert ev["outcome"] in OUTCOMES
            assert ev["tool"] and ev["source_reference"] and ev["content"] and ev["relevance_explanation"]
            assert isinstance(ev["tool_args"], dict)


def _uncovered(final):
    covered = {e["hypothesis_key"] for e in final["evidence_collected"]}
    return set(final["hypotheses_tested"]) - covered


def test_coverage_invariant_except_known_h4_gap(graph, ground_truth):
    """Non-negotiable #1: every tested hypothesis has evidence (H4 is tracked separately below)."""
    for row, final in _final_states(graph, ground_truth):
        assert _uncovered(final) - {"H4"} == set(), (row.sf_object, row.sf_field, _uncovered(final))


@pytest.mark.xfail(strict=True, reason="H4 has no evidence of its own until issue #10 attributes the DB2 lookup to it")
def test_h4_path_has_its_own_evidence(graph, ground_truth):
    h4 = [(row, final) for row, final in _final_states(graph, ground_truth) if "H4" in final["hypotheses_tested"]]
    assert h4, "benchmark must contain an H4 path"
    for row, final in h4:
        assert "H4" not in _uncovered(final), row.sf_field


def test_uncovered_hypothesis_always_flags_review(graph, ground_truth):
    for row, final in _final_states(graph, ground_truth):
        if _uncovered(final):
            # The coverage check lives in the synthesis node and must add the reason.
            assert "missing_evidence" in review_reasons(final), row.sf_field


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def test_evidence_persisted_with_linkage(storage, graph, ground_truth, fake_db):
    row = ground_truth_row(ground_truth[0])
    final = graph.invoke(initial_state(row.model_dump(mode="json")))
    result = _analyze(storage, graph, row, session="persist")
    saved = {r["id"]: r for r in fake_db.rows("rca_evidence") if r["incident_id"] == result["incident_id"]}

    # Same analysis, so the same tools ran: compare everything except generated IDs.
    expected = sorted((e["hypothesis_key"], e["tool"], e["outcome"], e["source_reference"]) for e in final["evidence_collected"])
    got = sorted((r["hypothesis_key"], r["tool"], r["outcome"], r["source_reference"]) for r in saved.values())
    assert got == expected
    for r in saved.values():
        assert r["raw_result"] is not None and isinstance(r["tool_args"], dict)


def test_tool_failure_is_recorded_not_dropped(storage, graph, ground_truth, fake_db, monkeypatch):
    def broken(**kwargs):
        raise TimeoutError("splunk search timed out")

    monkeypatch.setitem(evidence_module._REGISTRY, "splunk_stub", broken)
    hit = None
    for incident in ground_truth:
        row = ground_truth_row(incident)
        result = _analyze(storage, graph, row, session=f"fail-{incident['id']}")
        assert result["error"] is None, result["error"]  # the incident still completes
        rows = [r for r in fake_db.rows("rca_evidence") if r["incident_id"] == result["incident_id"]]
        errors = [r for r in rows if r["outcome"] == "error"]
        if errors:
            hit = (result, errors)
            break
    assert hit, "no benchmark row exercised the splunk tool"
    result, errors = hit
    assert all("timed out" in e["content"] and e["tool"] == "splunk_stub" for e in errors)
    assert "missing_evidence" in result["incident"].review_reasons and result["incident"].requires_human_review


def test_cache_replay_gets_fresh_evidence_ids(storage, graph, ground_truth, fake_db, llm):
    row = ground_truth_row(ground_truth[3])
    first = _analyze(storage, graph, row, session="replay")
    second = _analyze(storage, graph, row, session="replay")
    assert second["cached"]
    ids = [r["id"] for r in fake_db.rows("rca_evidence")]
    assert len(ids) == len(set(ids)), "replayed evidence must not reuse primary keys"
    by_incident = lambda iid: sorted((r["hypothesis_key"], r["outcome"]) for r in fake_db.rows("rca_evidence") if r["incident_id"] == iid)
    assert by_incident(first["incident_id"]) == by_incident(second["incident_id"])


# ---------------------------------------------------------------------------
# Similar past incidents
# ---------------------------------------------------------------------------
def test_similar_incidents_are_the_reranked_top_five(storage, graph, ground_truth, llm):
    from backend.seed.fsc_incidents import seed_artifacts

    asyncio.run(seed_artifacts(storage))
    # Reverse the reranker's order so we can tell reranked order from retrieval order.
    llm.respond("Rank these past incidents", lambda prompt, model: str(list(range(prompt.count("\n[")))[::-1]))
    row = ground_truth_row(ground_truth[0])
    final = graph.invoke(initial_state(row.model_dump(mode="json")))
    assert final["rag_candidates"], "seeded knowledge base should return candidates"
    expected = [str(c["id"]) for c in final["reranked_candidates"][:5]]

    inc = _analyze(storage, graph, row, session="similar")["incident"]
    assert [str(i) for i in inc.similar_incidents] == expected
    assert len(inc.similarity_scores) == len(expected) and all(0 < s <= 1 for s in inc.similarity_scores)


def test_no_candidates_means_no_similar_and_no_rerank_call(storage, graph, ground_truth, llm):
    row = ground_truth_row(ground_truth[0])  # knowledge base not seeded
    inc = _analyze(storage, graph, row, session="empty")["incident"]
    assert inc.similar_incidents == [] and inc.similarity_scores == []
    assert not llm.calls_matching("Rank these past incidents")


# ---------------------------------------------------------------------------
# API shape
# ---------------------------------------------------------------------------
def test_incident_api_groups_evidence_and_lists_similar(client, sample_csv_text):
    run_id, _ = run_sample(client, sample_csv_text)
    incidents = client.get(f"/api/v1/recon/runs/{run_id}").json()["incidents"]
    checked = 0
    for summary in incidents:
        body = client.get(f"/api/v1/incidents/{summary['id']}").json()
        groups = body["evidence_by_hypothesis"]
        assert list(groups) == [h for h in body["hypotheses_tested"] if h in groups], "groups follow test order"
        assert sum(len(v) for v in groups.values()) == len(body["evidence"])
        for key, evs in groups.items():
            assert all(e["hypothesis_key"] == key for e in evs)
        for s in body["similar_incidents_detail"]:
            assert set(s) >= {"id", "similarity", "source", "root_cause_category", "discrepancy_type", "summary"}
        assert [s["id"] for s in body["similar_incidents_detail"]] == [str(i) for i in body["similar_incidents"]]
        checked += bool(body["similar_incidents_detail"])
    assert checked, "at least one sample incident should cite similar past incidents"
