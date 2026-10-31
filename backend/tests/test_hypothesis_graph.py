"""Issue #10: declarative hypothesis catalogue, per-hypothesis verdicts, fixed logic bugs."""
import asyncio

import pytest

import backend.agents.evidence as evidence_module
from backend.config import AgentConfig
from backend.graph.hypotheses import BY_ID, CATALOGUE, CATEGORIES, GRAPH_VERSION, LABEL_KIND, OUTCOME, Hypothesis, evaluate
from backend.graph.recon_graph import MAX_ITERATIONS, build_graph
from backend.models.entities import DiscrepancyType, ReconRow
from backend.models.state import initial_state, review_reasons
from backend.tests.helpers import ground_truth_row

CONFIG = AgentConfig()


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _row(record_id, discrepancy, sf_object="Contact", sf_field="Phone"):
    return ReconRow(sf_object=sf_object, sf_field=sf_field, sf_record_id=record_id, sf_value="x",
                    db2_table="T", db2_column="C", db2_value=None if discrepancy == "NULL_DOWNSTREAM" else "y",
                    discrepancy_type=DiscrepancyType(discrepancy))


def _run(graph, row):
    return graph.invoke(initial_state(row.model_dump(mode="json")))


# ---------------------------------------------------------------------------
# Catalogue integrity and rule unit tests
# ---------------------------------------------------------------------------
CONFIRM = {
    "db2_history": {"was_populated": True, "last_value": "IL", "last_updated_at": "2026-10-01"},
    "fls": {"has_read_access": False, "integration_user": "svc", "permission_sets": []},
    "cdc": {"is_tracked": False, "reason_excluded": "formula_field", "cdc_channel": "ch"},
    "apex": {"has_conditional_publish": True, "suppressed_for_record": True, "trigger_name": "T"},
    "delivery": {"missed_events": True, "missed_count": 2, "last_event_ts": "t"},
    "dataweave": {"transform_errors": 2},
    "retries": {"retry_count": 3},
    "duplicate_rows": {"duplicate_rows": 3},
}
REFUTE = {
    "db2_history": {"was_populated": False, "time_window_days": 30},
    "fls": {"has_read_access": True, "integration_user": "svc"},
    "cdc": {"is_tracked": True, "cdc_channel": "ch"},
    "apex": {"has_conditional_publish": True, "suppressed_for_record": False, "trigger_name": "T"},
    "delivery": {"missed_events": False, "missed_count": 0},
    "dataweave": {"transform_errors": 0},
    "retries": {"retry_count": 1},
    "duplicate_rows": {"duplicate_rows": 1},
}
ROW = {"sf_object": "Contact", "sf_field": "Phone", "sf_record_id": "R1"}


def test_catalogue_integrity():
    assert set(CATALOGUE) == {t.value for t in DiscrepancyType}
    for plan in CATALOGUE.values():
        assert plan and len({h.id for h in plan}) == len(plan)
        for h in plan:
            assert h.category in CATEGORIES and 0 < h.confidence <= 1
            assert h.kind in CONFIRM, f"{h.id} has no rule test fixture"


@pytest.mark.parametrize("h", list(BY_ID.values()), ids=lambda h: h.id)
def test_rule_confirms_refutes_and_is_inconclusive(h: Hypothesis):
    verdict, reason, root_cause, _ = evaluate(h, CONFIRM[h.kind], ROW)
    assert verdict == "confirmed" and reason and root_cause
    verdict, reason, root_cause, _ = evaluate(h, REFUTE[h.kind], ROW)
    assert verdict == "refuted" and reason and root_cause is None
    for missing in (None, {}, {"status": "not_implemented"}, {"status": "skipped"}):
        assert evaluate(h, missing, ROW)[0] == "inconclusive"


def test_dormant_apex_logic_is_not_a_cause():
    apex = BY_ID["H3c"]
    assert evaluate(apex, {"has_conditional_publish": True, "suppressed_for_record": False}, ROW)[0] == "refuted"


# ---------------------------------------------------------------------------
# Named regressions: each was a bug in the previous graph (all would fail there)
# ---------------------------------------------------------------------------
REGRESSIONS = [
    # (name, discrepancy, fault, confounders, expected category)
    ("fls_beats_unrelated_missed_event", "NULL_DOWNSTREAM", "FLS_STRIPPED", ["unrelated_missed_event"], "FLS_STRIPPED"),
    ("cdc_exclusion_confirmed_not_fallback", "NULL_DOWNSTREAM", "CDC_FIELD_EXCLUDED", ["unrelated_missed_event"], "CDC_FIELD_EXCLUDED"),
    ("dataweave_result_is_evaluated", "VALUE_MISMATCH", "DATAWAVE_TRANSFORM_ERROR", [], "DATAWAVE_TRANSFORM_ERROR"),
    ("dataweave_not_mistaken_for_dormant_apex", "VALUE_MISMATCH", "DATAWAVE_TRANSFORM_ERROR", ["apex_conditional_dormant"], "DATAWAVE_TRANSFORM_ERROR"),
    ("stale_delivery_gap_confirmed", "STALE_VALUE", "DELIVERY_GAP", [], "DELIVERY_GAP"),
    ("missing_record_delivery_gap_confirmed", "MISSING_RECORD", "DELIVERY_GAP", ["apex_conditional_dormant"], "DELIVERY_GAP"),
    ("delivery_gap_not_mistaken_for_dormant_apex", "NULL_DOWNSTREAM", "DELIVERY_GAP", ["apex_conditional_dormant"], "DELIVERY_GAP"),
    ("duplicates_from_retries", "DUPLICATE_DOWNSTREAM", "DUPLICATE_DOWNSTREAM", [], "DUPLICATE_DOWNSTREAM"),
    ("apex_suppression_confirmed", "MISSING_RECORD", "APEX_SUPPRESSION", [], "APEX_SUPPRESSION"),
]


@pytest.mark.parametrize("name,discrepancy,fault,confounders,expected", REGRESSIONS, ids=[r[0] for r in REGRESSIONS])
def test_known_failure_regressions(graph, scenarios, name, discrepancy, fault, confounders, expected):
    scenarios.add(f"REG-{name}", fault, confounders)
    final = _run(graph, _row(f"REG-{name}", discrepancy))
    assert final["graph_status"] == "confirmed", final["hypothesis_verdicts"]
    assert final["root_cause_category"] == expected


def test_no_fault_escalates_instead_of_guessing(graph, scenarios):
    scenarios.add("REG-clean", "NO_FAULT_FOUND", ["apex_conditional_dormant"])
    for discrepancy in ("NULL_DOWNSTREAM", "VALUE_MISMATCH", "STALE_VALUE", "MISSING_RECORD", "DUPLICATE_DOWNSTREAM"):
        final = _run(graph, _row("REG-clean", discrepancy))
        assert final["graph_status"] == "exhausted" and final["root_cause_category"] is None, discrepancy
        assert "no_hypothesis_confirmed" in review_reasons(final)
        assert all(v["verdict"] == "refuted" for v in final["hypothesis_verdicts"])


@pytest.mark.parametrize("discrepancy", ["NULL_DOWNSTREAM", "STALE_VALUE", "MISSING_RECORD"])
def test_single_missed_event_is_weak_evidence(graph, scenarios, discrepancy):
    """Where delivery is the last check, one unrelated missed event looks exactly like a
    delivery gap. The graph may name DELIVERY_GAP but must not auto-clear it."""
    scenarios.add("REG-weak", "NO_FAULT_FOUND", ["unrelated_missed_event"])
    final = _run(graph, _row("REG-weak", discrepancy))
    assert final["root_cause_category"] == "DELIVERY_GAP"
    assert final["graph_confidence"] < 0.75 and "graph_low_confidence" in review_reasons(final)


def test_multiple_missed_events_are_strong_evidence(graph, scenarios):
    for i in range(20):  # the simulator draws 1-3 missed events; find a record with >= 2
        scenarios.add(f"REG-strong-{i}", "DELIVERY_GAP")
        final = _run(graph, _row(f"REG-strong-{i}", "STALE_VALUE"))
        reason = final["hypothesis_verdicts"][-1]["reason"]
        if "weak" not in reason:
            assert final["graph_confidence"] == 0.84 and "graph_low_confidence" not in review_reasons(final)
            return
    pytest.fail("no record drew >= 2 missed events")


# ---------------------------------------------------------------------------
# Verdicts and evidence
# ---------------------------------------------------------------------------
def test_verdicts_cover_every_tested_hypothesis(graph, ground_truth):
    for inc in ground_truth:
        final = _run(graph, ground_truth_row(inc))
        verdicts = final["hypothesis_verdicts"]
        assert [v["hypothesis_id"] for v in verdicts] == final["hypotheses_tested"], inc["id"]
        confirmed = [v for v in verdicts if v["verdict"] == "confirmed"]
        assert len(confirmed) == (1 if final["graph_status"] == "confirmed" else 0)
        if confirmed:
            assert confirmed[0]["hypothesis_id"] == final["hypotheses_tested"][-1], "stops at the first confirmation"
            assert final["root_cause_category"] == BY_ID[confirmed[0]["hypothesis_id"]].category
        for v in verdicts:
            assert v["evidence_ids"], f"{inc['id']} {v['hypothesis_id']} has no evidence"
        assert set(final["hypotheses_ruled_out"]) == {v["hypothesis_id"] for v in verdicts if v["verdict"] == "refuted"}


def test_evidence_outcome_matches_verdict(graph, ground_truth):
    for inc in ground_truth:
        final = _run(graph, ground_truth_row(inc))
        by_id = {e["evidence_id"]: e for e in final["evidence_collected"]}
        for v in final["hypothesis_verdicts"]:
            for eid in v["evidence_ids"]:
                assert by_id[eid]["outcome"] == OUTCOME[v["verdict"]], (inc["id"], v["hypothesis_id"])


def test_overwrite_has_its_own_evidence_and_no_missing_evidence_flag(graph, scenarios):
    scenarios.add("REG-ovr", "DOWNSTREAM_OVERWRITE")
    final = _run(graph, _row("REG-ovr", "NULL_DOWNSTREAM"))
    assert final["root_cause_category"] == "DOWNSTREAM_OVERWRITE" and final["hypotheses_tested"] == ["H1"]
    assert final["hypothesis_verdicts"][0]["evidence_ids"]
    assert "missing_evidence" not in review_reasons(final)


def test_tool_error_is_inconclusive_not_refuted(graph, scenarios, monkeypatch):
    def broken(**kwargs):
        raise ConnectionError("Salesforce API unavailable")

    monkeypatch.setitem(evidence_module._REGISTRY, "get_field_permissions", broken)
    scenarios.add("REG-err", "FLS_STRIPPED")
    final = _run(graph, _row("REG-err", "NULL_DOWNSTREAM"))
    fls = next(v for v in final["hypothesis_verdicts"] if v["hypothesis_id"] == "H3a")
    assert fls["verdict"] == "inconclusive" and "H3a" not in final["hypotheses_ruled_out"]
    assert final["graph_status"] == "exhausted", "it can't confirm FLS without the FLS check"
    assert {"missing_evidence", "no_hypothesis_confirmed"} <= set(review_reasons(final))


def test_iteration_cap_flags_review(graph, scenarios, monkeypatch):
    from backend.graph.hypotheses import _fls_args, _fls_rule

    long_plan = [Hypothesis(f"LOOP{i}", "never confirms", "fls", "FLS_STRIPPED", "get_field_permissions",
                            _fls_args, _fls_rule, 0.9) for i in range(MAX_ITERATIONS + 2)]
    monkeypatch.setitem(CATALOGUE, "VALUE_MISMATCH", long_plan)
    scenarios.add("REG-cap", "NO_FAULT_FOUND")
    final = _run(graph, _row("REG-cap", "VALUE_MISMATCH"))
    assert final["graph_status"] == "running"
    assert "iteration_limit" in review_reasons(final)


def test_unknown_type_flags_review(graph):
    row = _row("REG-unknown", "VALUE_MISMATCH").model_dump(mode="json")
    row["discrepancy_type"] = "SOMETHING_NEW"
    from backend.agents.hypothesis import HypothesisAgent

    out = HypothesisAgent(CONFIG).run({**initial_state(row), "recon_row": row})
    assert out["graph_status"] == "unknown_type" and out["review_reasons"] == ["unknown_type"]


# ---------------------------------------------------------------------------
# Against the benchmark labels
# ---------------------------------------------------------------------------
# The labels name the deciding check with an older scheme (LABEL_KIND). Known, explained
# differences are listed here; anything else fails.
KNOWN_KIND_DIFFERENCES = {
    # Labels decide duplicates on DB2 duplicate rows (HDD2); the graph confirms on the earlier
    # retry check (HDD1). Both establish DUPLICATE_DOWNSTREAM; the graph needs one fewer check.
    ("duplicate_rows", "retries"),
}


def test_paths_against_labels(graph, ground_truth):
    category_misses, efficiency_misses, kind_mismatches = [], [], []
    for inc in ground_truth:
        gt = inc["ground_truth"]
        final = _run(graph, ground_truth_row(inc))
        if final["root_cause_category"] != gt["root_cause"]:
            category_misses.append((inc["id"], gt["root_cause"], final["root_cause_category"]))
        if len(final["hypotheses_tested"]) > gt["min_hypotheses_needed"]:
            efficiency_misses.append((inc["id"], final["hypotheses_tested"], gt["min_hypotheses_needed"]))
        deciding = BY_ID[final["hypotheses_tested"][-1]].kind
        expected = LABEL_KIND[gt["early_termination_at"]]
        if deciding != expected and (expected, deciding) not in KNOWN_KIND_DIFFERENCES:
            kind_mismatches.append((inc["id"], expected, deciding))
    assert not category_misses, category_misses
    assert not efficiency_misses, efficiency_misses
    assert not kind_mismatches, kind_mismatches


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def test_incident_persists_graph_outcome(storage, graph, ground_truth, fake_db):
    from backend.main import _analyze_row

    row = ground_truth_row(ground_truth[0])
    result = asyncio.run(_analyze_row(row, CONFIG, graph, storage, session_id="persist-graph"))
    inc = result["incident"]
    assert inc.graph_version == GRAPH_VERSION and inc.graph_status == "confirmed"
    assert inc.root_cause_category == ground_truth[0]["ground_truth"]["root_cause"]
    saved = fake_db.rows("rca_incidents")[-1]
    for key in ("hypothesis_verdicts", "graph_status", "root_cause_category", "contributing_factors", "graph_version"):
        assert saved[key] == getattr(inc, key), key
    cached = asyncio.run(_analyze_row(row, CONFIG, graph, storage, session_id="persist-graph"))
    assert cached["cached"] and cached["incident"].hypothesis_verdicts == inc.hypothesis_verdicts
