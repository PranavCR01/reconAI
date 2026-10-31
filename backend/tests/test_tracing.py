"""Issue #12: per-incident trace, cost and wall-clock latency."""
import asyncio
import sys
import time

import pytest

from backend.config import CONFIGS, PRICING_PER_MTOK, AgentConfig, call_cost_usd, incident_cost
from backend.graph.recon_graph import build_graph
from backend.models.state import initial_state
from backend.tests.fakes.fake_llm import api_status_error, critic_reply
from backend.tests.helpers import CRITIC_PROMPT, SYNTHESIS_PROMPT, ground_truth_row, run_sample

CONFIG = AgentConfig()
LLM_KEYS = ("agent", "model", "attempt", "input_tokens", "output_tokens", "latency_ms", "error")


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _run(graph, row):
    return graph.invoke(initial_state(row.model_dump(mode="json")))


def _analyze(storage, graph, row, session="s", config=CONFIG):
    from backend.main import _analyze_row

    return asyncio.run(_analyze_row(row, config, graph, storage, session_id=session))


def _one_per_type(ground_truth):
    seen = {}
    for inc in ground_truth:
        seen.setdefault(inc["discrepancy_type"], inc)
    return [ground_truth_row(i) for i in seen.values()]


def _project(call):
    return {k: call[k] for k in LLM_KEYS if call.get(k) is not None}


# ---------------------------------------------------------------------------
# Trace shape
# ---------------------------------------------------------------------------
def test_trace_covers_every_node_in_order(graph, ground_truth):
    rows = _one_per_type(ground_truth)
    assert len(rows) == 5
    for row in rows:
        final = _run(graph, row)
        nodes = [s["node"] for s in final["trace"]]
        tested = final["hypotheses_tested"]
        # ingestion, then (hypothesis, evidence) per tested hypothesis, a final hypothesis evaluation,
        # then retrieval and one explanation round (the default fake critic supports every claim).
        expected = ["ingestion"] + ["hypothesis", "evidence"] * len(tested) + \
                   ["hypothesis", "rag_retrieval", "proposer", "critic", "judge"]
        assert nodes == expected, f"{row.discrepancy_type}: {nodes}"

        hyp_steps = [s for s in final["trace"] if s["node"] == "hypothesis"]
        assert [s["detail"]["queued"] for s in hyp_steps[:-1]] == [[h] for h in tested]
        assert hyp_steps[-1]["detail"]["status"] == final["graph_status"]
        assert final["trace"][-1]["detail"] == {"decision": final["judge_decision"]}

        starts = [s["started_at"] for s in final["trace"]]
        assert starts == sorted(starts)
        assert all(s["duration_ms"] >= 0 and set(s) == {"node", "started_at", "duration_ms", "detail", "llm_calls"}
                   for s in final["trace"])


def test_trace_llm_steps_match_llm_calls_one_to_one(storage, graph, ground_truth, llm):
    from backend.seed.fsc_incidents import seed_artifacts

    asyncio.run(seed_artifacts(storage))
    # A failed proposer attempt followed by a valid one: both must appear, in order.
    llm.respond(SYNTHESIS_PROMPT, "not json", times=1)
    final = _run(graph, _one_per_type(ground_truth)[0])
    traced = [c for s in final["trace"] for c in s["llm_calls"]]
    assert traced == [_project(c) for c in final["llm_calls"]]
    assert len(traced) == len(llm.calls)
    proposer = next(s for s in final["trace"] if s["node"] == "proposer")
    assert [c["attempt"] for c in proposer["llm_calls"]] == [1, 2]
    assert "invalid output" in proposer["llm_calls"][0]["error"]
    by_node = {s["node"]: [c["agent"] for c in s["llm_calls"]] for s in final["trace"]}
    assert by_node["rag_retrieval"] == ["reranker"] and by_node["critic"] == ["critic"]


def test_api_error_appears_in_trace(graph, ground_truth, llm):
    llm.fail(SYNTHESIS_PROMPT, api_status_error(529))
    final = _run(graph, _one_per_type(ground_truth)[0])
    proposer = next(s for s in final["trace"] if s["node"] == "proposer")
    assert proposer["detail"]["status"] == "api_unavailable"
    assert "APIStatusError" in proposer["llm_calls"][0]["error"]


def test_revision_round_is_traced(graph, ground_truth, llm):
    llm.respond(CRITIC_PROMPT, lambda p, m: critic_reply(p, {"C1": ("unsupported", "no cited evidence")}), times=1)
    final = _run(graph, _one_per_type(ground_truth)[0])
    tail = [s["node"] for s in final["trace"]][-6:]
    assert tail == ["proposer", "critic", "judge", "proposer", "critic", "judge"]
    rounds = [s["detail"]["round"] for s in final["trace"] if s["node"] == "proposer"]
    assert rounds == [1, 2]
    decisions = [s["detail"]["decision"] for s in final["trace"] if s["node"] == "judge"]
    assert decisions[0] == "revise" and decisions[1] == final["judge_decision"]


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("model,tin,tout,expected", [
    ("claude-sonnet-4-6", 1_000_000, 0, 3.00),
    ("claude-sonnet-4-6", 0, 1_000_000, 15.00),
    ("claude-sonnet-4-6", 1500, 400, 0.0105),
    ("claude-haiku-4-5-20251001", 300, 8, 0.00034),
    ("llama-3.3-70b-versatile", 1_000_000, 1_000_000, 1.38),
    ("claude-sonnet-4-6", 0, 0, 0.0),
])
def test_call_cost(model, tin, tout, expected):
    assert call_cost_usd({"model": model, "input_tokens": tin, "output_tokens": tout}) == pytest.approx(expected)


def test_unknown_model_cost_is_none_never_zero():
    assert call_cost_usd({"model": "mystery-model", "input_tokens": 10, "output_tokens": 10}) is None
    calls = [{"model": "claude-sonnet-4-6", "input_tokens": 1000, "output_tokens": 100},
             {"model": "mystery-model", "input_tokens": 1, "output_tokens": 1}, {"input_tokens": 1}]
    assert incident_cost(calls) == (None, ["no price for model <missing>", "no price for model mystery-model"])
    assert incident_cost([]) == (0.0, [])


def test_every_configured_model_is_priced():
    for name, cfg in CONFIGS.items():
        for field in ("ingestion_llm", "reranker_llm", "synthesis_llm", "critic_llm"):
            assert getattr(cfg, field) in PRICING_PER_MTOK, f"{name}.{field} has no price"


@pytest.mark.parametrize("config_key", ["claude", "groq"])
def test_incident_cost_matches_its_calls(storage, ground_truth, llm, config_key):
    config = CONFIGS[config_key]
    graph = build_graph(config, storage)
    inc = _analyze(storage, graph, _one_per_type(ground_truth)[0], config=config)["incident"]
    assert inc.llm_calls and inc.cost_warnings == []
    expected = sum(PRICING_PER_MTOK[c["model"]][0] * c["input_tokens"] + PRICING_PER_MTOK[c["model"]][1] *
                   c["output_tokens"] for c in inc.llm_calls) / 1e6
    assert inc.cost_usd == pytest.approx(expected, abs=1e-6) and inc.cost_usd > 0


def test_unpriced_model_gives_warning_on_incident(storage, ground_truth, llm):
    config = AgentConfig(synthesis_llm="some-new-model")
    graph = build_graph(config, storage)
    inc = _analyze(storage, graph, _one_per_type(ground_truth)[0], config=config)["incident"]
    assert inc.cost_usd is None and inc.cost_warnings == ["no price for model some-new-model"]


# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
def test_e2e_latency_includes_non_llm_work(storage, graph, ground_truth, monkeypatch):
    import backend.agents.evidence as evidence

    original = evidence.run_evidence

    def slow(state):
        time.sleep(0.12)
        return original(state)

    monkeypatch.setattr("backend.graph.recon_graph.run_evidence", slow)
    graph = build_graph(CONFIG, storage)
    inc = _analyze(storage, graph, _one_per_type(ground_truth)[0])["incident"]
    evidence_steps = [s for s in inc.trace if s["node"] == "evidence"]
    assert evidence_steps and all(s["duration_ms"] >= 120 for s in evidence_steps)
    assert inc.e2e_latency_ms >= inc.latency_ms + 120 * len(evidence_steps)
    assert inc.e2e_latency_ms >= sum(s["duration_ms"] for s in inc.trace)


def test_slow_llm_shows_in_its_step(graph, ground_truth, llm):
    from backend.tests.fakes.fake_llm import critic_reply as reply

    def slow_critic(prompt, model):
        time.sleep(0.08)
        return reply(prompt)

    llm.respond(CRITIC_PROMPT, slow_critic)
    final = _run(graph, _one_per_type(ground_truth)[0])
    critic = next(s for s in final["trace"] if s["node"] == "critic")
    assert critic["llm_calls"][0]["latency_ms"] >= 80 and critic["duration_ms"] >= critic["llm_calls"][0]["latency_ms"]


# ---------------------------------------------------------------------------
# Persistence, cache and API
# ---------------------------------------------------------------------------
def test_trace_and_cost_persisted_and_restored_from_cache(storage, graph, ground_truth, llm, fake_db):
    row = _one_per_type(ground_truth)[2]
    fresh = _analyze(storage, graph, row, session="c")
    saved = fake_db.rows("rca_incidents")[-1]
    assert saved["trace"] == fresh["incident"].trace and saved["cost_usd"] == fresh["incident"].cost_usd
    assert saved["e2e_latency_ms"] == fresh["incident"].e2e_latency_ms

    calls = len(llm.calls)
    cached = _analyze(storage, graph, row, session="c")
    assert cached["cached"] and len(llm.calls) == calls
    a, b = fresh["incident"], cached["incident"]
    assert (b.trace, b.cost_usd, b.cost_warnings) == (a.trace, a.cost_usd, a.cost_warnings)


def test_incident_api_returns_trace_and_cost(client, sample_csv_text):
    run_id, _ = run_sample(client, sample_csv_text)
    incidents = client.get(f"/api/v1/recon/runs/{run_id}").json()["incidents"]
    for summary in incidents:
        body = client.get(f"/api/v1/incidents/{summary['id']}").json()
        assert body["trace"] and body["trace"][0]["node"] == "ingestion" and body["trace"][-1]["node"] == "judge"
        assert body["cost_usd"] is not None and body["cost_usd"] > 0 and body["cost_warnings"] == []
        assert body["e2e_latency_ms"] >= 0


def test_tracing_makes_no_external_calls():
    # Tracing is local; nothing is exported (the network guard would also fail any attempt).
    assert "langfuse" not in sys.modules
