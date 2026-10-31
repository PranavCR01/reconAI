"""Issue #13: eval suite: metrics, planted-claim set, golden offline results, live-run safety."""
import asyncio
import json
import os

import pytest

from backend.evals import metrics as M
from backend.evals import planted as P
from backend.evals.harness import LiveRunRefused, check_live_allowed, environment
from backend.evals.labels import ARTIFACT_FAMILY, relevant_sources
from backend.evals.run import RESULTS_DIR, estimate_cost, main, run_eval
from backend.evals.schema import EvalResults

GOLDEN = RESULTS_DIR / "offline_claude.json"
VOLATILE = ("created_at", "git_sha")


# ---------------------------------------------------------------------------
# Metrics (hand-computed fixtures)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("k,n,expected", [
    (0, 50, (0.0, 0.0713)), (50, 50, (0.9287, 1.0)), (5, 10, (0.2366, 0.7634)), (47, 50, (0.8378, 0.9794)),
])
def test_wilson(k, n, expected):
    assert M.wilson(k, n) == expected


def test_rate_and_empty():
    assert M.rate(3, 4)["rate"] == 0.75
    assert M.rate(0, 0) == {"k": 0, "n": 0, "rate": None, "ci95": None}
    assert M.proportion([]) == M.rate(0, 0)
    assert M.proportion([True, False, True])["k"] == 2


def test_confusion():
    pairs = [("A", "A"), ("A", "B"), ("B", None), ("A", "A")]
    assert M.confusion(pairs) == {"A": {"A": 2, "B": 1}, "B": {"NONE": 1}}
    assert M.confusion([]) == {}


def test_precision_recall():
    out = M.precision_recall([True, True, False, False, True], [True, False, True, False, True])
    assert (out["tp"], out["fp"], out["fn"], out["tn"]) == (2, 1, 1, 1)
    assert out["precision"]["rate"] == round(2 / 3, 4) and out["recall"]["rate"] == round(2 / 3, 4)
    none = M.precision_recall([False, False], [False, False])
    assert none["precision"]["rate"] is None and none["recall"]["rate"] is None


def test_ece_hand_computed():
    # Bucket [0.9, 1.0]: mean 0.95, accuracy 0.5 -> 0.45 * 2/4; bucket [0.5, 0.6): mean 0.55, accuracy 1.0 -> 0.45 * 2/4.
    out = M.ece([0.95, 0.95, 0.55, 0.55], [True, False, True, True])
    assert out["ece"] == 0.45 and [b["n"] for b in out["buckets"]] == [2, 2]
    assert M.ece([1.0, 1.0], [True, True])["ece"] == 0.0, "1.0 belongs to the last bucket"
    assert M.ece([0.8], [False])["ece"] == 0.8
    empty = M.ece([None, None], [True, False])
    assert empty["ece"] is None and empty["excluded_no_confidence"] == 2


def test_retrieval_metrics():
    ranked = ["a", "b", "c", "d"]
    assert M.recall_at_k(ranked, {"b", "z"}, 1) == 0.0
    assert M.recall_at_k(ranked, {"b", "z"}, 3) == 0.5
    assert M.hit_at_k(ranked, {"c"}, 3) is True and M.hit_at_k(ranked, {"c"}, 2) is False
    assert M.reciprocal_rank(ranked, {"c", "d"}) == pytest.approx(1 / 3)
    assert M.reciprocal_rank(ranked, {"z"}) == 0.0
    assert M.recall_at_k(ranked, set(), 3) is None and M.reciprocal_rank(ranked, set()) is None


def test_agreement_percentile_mean():
    assert M.agreement([["A", "A", "A"], ["A", "B", "A"], [None, None]])["k"] == 2
    assert M.agreement([[["x"], ["x"]], [{"a": 1}, {"a": 1}]])["rate"] == 1.0
    assert M.percentile([5, 1, 3, 2, 4], 50) == 3 and M.percentile([5, 1, 3, 2, 4], 95) == 5
    assert M.percentile([None, None], 50) is None and M.mean([]) is None and M.mean([1, None, 2]) == 1.5


# ---------------------------------------------------------------------------
# Retrieval labels
# ---------------------------------------------------------------------------
def test_every_seeded_artifact_has_a_family():
    from backend.seed.fsc_incidents import _INCIDENTS

    assert {a.root_cause_category for a in _INCIDENTS} <= set(ARTIFACT_FAMILY)
    assert len({a.source for a in _INCIDENTS}) == len(_INCIDENTS), "sources must be unique ids"


def test_every_benchmark_root_cause_has_relevant_artifacts(ground_truth):
    for inc in ground_truth:
        assert relevant_sources(inc["ground_truth"]["root_cause"]), inc["id"]


# ---------------------------------------------------------------------------
# Planted-claim set
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def finals():
    from backend.evals.run import _analyze_all
    from backend.evals.labels import load_incidents
    from backend.config import CONFIGS
    from backend.seed.fsc_incidents import seed_artifacts

    with environment("offline") as env:
        asyncio.run(seed_artifacts(env.storage))
        _, out = _analyze_all(load_incidents()[:12], CONFIGS["claude"], env, 1, lambda m: None)
    return out


def _diff(clean, draft):
    """Changed (claim index, field) pairs plus any added claims."""
    changed = {(i, f) for i, (a, b) in enumerate(zip(clean, draft)) for f in a if a[f] != b[f]}
    return changed, draft[len(clean):]


EXPECTED_CHANGE = {
    "fabricated_evidence": ({(0, "evidence_ids")}, 0),
    "fabricated_past_incident": ({(0, "similar_incident_ids")}, 0),
    "wrong_category": ({(0, "category")}, 0),
    "contradicts_refuted": ({(0, "hypothesis_ids")}, 0),
    "placeholder_text": ({(1, "text")}, 0),
    "unsupported_mechanism": (set(), 1),
}


def test_each_defect_changes_only_its_injection(finals):
    for incident_id, state in finals.items():
        drafts = P.drafts(state)
        clean = drafts["clean"]
        assert set(drafts) == {"clean", *P.DEFECTS}
        for defect in P.DEFECTS:
            if drafts[defect] is None:
                assert defect == "contradicts_refuted" and not any(
                    v["verdict"] == "refuted" for v in state["hypothesis_verdicts"])
                continue
            changed, added = _diff(clean, drafts[defect])
            want_changed, want_added = EXPECTED_CHANGE[defect]
            assert changed == want_changed and len(added) == want_added, (incident_id, defect, changed, added)


def test_clean_draft_passes_and_defects_fail_the_deterministic_checks(finals):
    from backend.agents.explanation import deterministic_checks

    for state in finals.values():
        drafts = P.drafts(state)
        for kind, claims in drafts.items():
            if claims is None:
                continue
            cstate = P.critic_state(state, claims)
            failed = [deterministic_checks(c, cstate) for c in cstate["proposal"]["claims"]]
            if kind == "clean" or P.EXPECTED_STAGE[kind] == "llm":
                assert not any(failed), (kind, failed)
            else:
                assert any(failed), kind


def test_draft_set_is_reproducible(finals):
    a = P.draft_set_hash({k: P.drafts(s) for k, s in finals.items()})
    b = P.draft_set_hash({k: P.drafts(s) for k, s in finals.items()})
    assert a == b and len(a) == 64


# ---------------------------------------------------------------------------
# Golden offline results
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def offline_results():
    return run_eval("offline", "claude")


def _stable(results: dict) -> dict:
    return {k: v for k, v in results.items() if k not in VOLATILE}


def test_offline_results_match_committed_golden(offline_results):
    committed = json.loads(GOLDEN.read_text())
    # Round-trip through JSON so tuples compare equal to the lists they are stored as.
    produced = json.loads(json.dumps(offline_results))
    assert _stable(produced) == _stable(committed), (
        "offline eval results changed: re-run `python -m backend.evals.run --mode offline --config claude` "
        "and commit evals/results/ in the same change")


def test_committed_report_matches_results():
    from backend.evals.report import render

    committed = json.loads(GOLDEN.read_text())
    assert (RESULTS_DIR / "offline_claude.md").read_text() == render(committed)


def test_committed_results_validate_against_schema():
    for path in RESULTS_DIR.glob("*.json"):
        EvalResults.model_validate(json.loads(path.read_text()))


def test_schema_rejects_missing_and_unknown_fields(offline_results):
    from pydantic import ValidationError

    broken = json.loads(json.dumps(offline_results))
    broken.pop("metrics")
    with pytest.raises(ValidationError):
        EvalResults.model_validate(broken)
    extra = {**json.loads(json.dumps(offline_results)), "headline_accuracy": 0.99}
    with pytest.raises(ValidationError):
        EvalResults.model_validate(extra)


def test_offline_results_are_internally_consistent(offline_results):
    r = offline_results
    first = [i for i in r["incidents"] if i["run"] == 1]
    assert len(first) == r["dataset"]["incidents"] == 50
    assert r["metrics"]["accuracy"]["overall"]["k"] == sum(i["correct"] for i in first)
    assert r["ablations"]["as_built"]["accuracy"] == r["metrics"]["accuracy"]["overall"]
    unsafe = sum(1 for i in first if not i["correct"] and not i["requires_review"])
    assert r["metrics"]["routing"]["unsafe_auto_clear"]["k"] == unsafe
    assert r["metrics"]["retrieval"]["status"] == "not_measured"
    assert r["metrics"]["cost_latency"]["e2e_latency_ms_median"] is None, "no wall-clock numbers offline"
    assert any("scripted" in c for c in r["caveats"])


def test_ablation_shows_why_check_order_matters(offline_results):
    ab = offline_results["ablations"]
    assert ab["delivery_first_all_confounders"]["accuracy"]["k"] < ab["all_confounders"]["accuracy"]["k"]


def test_ablations_restore_catalogue_and_world(offline_results):
    from backend.graph.hypotheses import CATALOGUE
    from backend.tools import world

    assert CATALOGUE["NULL_DOWNSTREAM"][0].kind != "delivery"
    assert any(s.confounders for s in world.registry().values())


# ---------------------------------------------------------------------------
# Live-run safety
# ---------------------------------------------------------------------------
def test_live_refuses_real_database():
    class RealLooking:
        _client = object()

    with pytest.raises(LiveRunRefused, match="in-memory fake"):
        check_live_allowed("claude", True, RealLooking())


def test_live_refuses_without_yes(monkeypatch):
    monkeypatch.setenv("TPRM_ANTHROPIC_API_KEY", "x")
    with pytest.raises(LiveRunRefused, match="--yes"):
        with environment("live", "claude", yes=False):
            pass


def test_live_refuses_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("TPRM_ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LiveRunRefused, match="Anthropic API key"):
        with environment("live", "claude", yes=True):
            pass
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("TPRM_ANTHROPIC_API_KEY", "x")
    with pytest.raises(LiveRunRefused, match="GROQ_API_KEY"):
        with environment("live", "hybrid", yes=True):
            pass


def test_cli_refusal_exit_code(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("TPRM_ANTHROPIC_API_KEY", "x")
    assert main(["--mode", "live", "--limit", "1", "--out", str(tmp_path)]) == 2
    err = capsys.readouterr().err
    assert "Estimated cost: $" in err and "Refused" in err
    assert not list(tmp_path.iterdir()), "a refused run writes nothing"


def test_environment_restores_process_state(monkeypatch):
    import anthropic

    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://proxy.local")
    before = (anthropic.Anthropic, os.environ.get("ANTHROPIC_API_KEY"))
    with environment("offline"):
        assert "ANTHROPIC_BASE_URL" not in os.environ
    assert (anthropic.Anthropic, os.environ.get("ANTHROPIC_API_KEY")) == before
    assert os.environ["ANTHROPIC_BASE_URL"] == "http://proxy.local"


def test_cost_estimate():
    one = estimate_cost("claude", 1, 1, 0)
    assert one and one > 0
    assert estimate_cost("claude", 50, 3, 50) > estimate_cost("claude", 50, 1, 50)
    assert estimate_cost("groq", 50, 1, 50) < estimate_cost("claude", 50, 1, 50)


# ---------------------------------------------------------------------------
# Live smoke (manual): pytest -m live_llm backend/tests/test_evals.py
# ---------------------------------------------------------------------------
@pytest.mark.live_llm
def test_live_smoke_five_incidents():
    results = run_eval("live", "claude", runs=1, limit=5, planted_limit=1, yes=True)
    EvalResults.model_validate(results)
    assert results["metrics"]["errors"]["count"] == 0
    assert results["metrics"]["cost_latency"]["cost_usd_total"] > 0
    assert results["metrics"]["cost_latency"]["e2e_latency_ms_median"] > 0


def test_published_frontend_results_are_current():
    from backend.evals.publish import PUBLISHED, render

    assert PUBLISHED.read_text() == render(), "run `python -m backend.evals.publish` and commit the result"
