"""Issue #15: outages aren't cached, failures aren't silent, health is honest, CORS, seed dates, client IP."""
import asyncio
from datetime import datetime, timezone

import pytest

from backend.config import AgentConfig
from backend.graph.recon_graph import build_graph
from backend.tests.fakes.fake_llm import api_status_error
from backend.tests.helpers import CRITIC_PROMPT, SYNTHESIS_PROMPT, ground_truth_row

CONFIG = AgentConfig()


@pytest.fixture
def graph(storage):
    return build_graph(CONFIG, storage)


def _analyze(storage, graph, row, session="s"):
    from backend.main import _analyze_row

    return asyncio.run(_analyze_row(row, CONFIG, graph, storage, session_id=session))


def _cache_rows(fake_db):
    return fake_db.rows("rca_cache")


# ---------------------------------------------------------------------------
# Degraded results are not cached
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("outage", ["proposer", "critic", "tool", "retrieval"])
def test_outage_is_not_cached_and_recovery_reanalyzes(storage, graph, ground_truth, llm, fake_db, outage):
    row = ground_truth_row(ground_truth[0])
    with pytest.MonkeyPatch.context() as mp:
        if outage == "proposer":
            llm.fail(SYNTHESIS_PROMPT, api_status_error(529))
        elif outage == "critic":
            llm.fail(CRITIC_PROMPT, api_status_error(529))
        elif outage == "tool":
            import backend.agents.evidence as evidence

            def broken(**kwargs):
                raise TimeoutError("tool timed out")

            for name in list(evidence._REGISTRY):
                mp.setitem(evidence._REGISTRY, name, broken)
        else:
            mp.setattr("backend.tools.rag_tools.embed_text", lambda text: (_ for _ in ()).throw(RuntimeError("embed down")))

        first = _analyze(storage, graph, row, session="outage")
        assert first["degraded"], "the outage must be detected"
        assert not _cache_rows(fake_db), "a degraded result must not be cached"

    # Dependency recovers.
    llm.rules.clear()
    graph = build_graph(CONFIG, storage)
    calls_before = len(llm.calls)
    second = _analyze(storage, graph, row, session="outage")
    assert not second["cached"] and len(llm.calls) > calls_before, "recovery must re-analyze, not replay"
    assert not second.get("degraded")
    assert second["incident"].confidence and second["incident"].confidence > 0
    assert len(_cache_rows(fake_db)) == 1


def test_healthy_result_is_cached_and_replayed(storage, graph, ground_truth, llm, fake_db):
    row = ground_truth_row(ground_truth[1])
    first = _analyze(storage, graph, row, session="ok")
    assert not first.get("degraded") and len(_cache_rows(fake_db)) == 1
    calls = len(llm.calls)
    second = _analyze(storage, graph, row, session="ok")
    assert second["cached"] and len(llm.calls) == calls


def test_invalid_output_fixed_by_retry_is_not_an_outage(storage, graph, ground_truth, llm, fake_db):
    llm.respond(SYNTHESIS_PROMPT, "not json", times=1)
    result = _analyze(storage, graph, ground_truth_row(ground_truth[2]), session="retry")
    assert not result.get("degraded") and len(_cache_rows(fake_db)) == 1


# ---------------------------------------------------------------------------
# Retrieval error vs empty
# ---------------------------------------------------------------------------
def test_retrieval_error_is_recorded_distinct_from_empty(storage, graph, ground_truth, monkeypatch, fake_db):
    row = ground_truth_row(ground_truth[3])
    # No artifacts seeded: retrieval runs and finds nothing.
    empty = _analyze(storage, graph, row, session="empty")["incident"]
    assert empty.retrieval_error is None and empty.similar_incidents == []
    step = next(s for s in empty.trace if s["node"] == "rag_retrieval")
    assert step["detail"]["error"] is None and step["detail"]["candidates"] == 0

    monkeypatch.setattr(storage, "search_artifacts_sync", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("rpc 500")))
    failed = _analyze(storage, graph, row, session="broken")["incident"]
    assert failed.retrieval_error and "rpc 500" in failed.retrieval_error
    step = next(s for s in failed.trace if s["node"] == "rag_retrieval")
    assert "rpc 500" in step["detail"]["error"]
    assert fake_db.rows("rca_incidents")[-1]["retrieval_error"] == failed.retrieval_error


# ---------------------------------------------------------------------------
# Startup seeding and /health
# ---------------------------------------------------------------------------
def test_health_ok_with_seeded_kb(client):
    body = client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["db"] == "ok" and body["kb_artifacts"] > 0 and body["problems"] == []


def test_seed_failure_is_surfaced(fake_db, llm, embeddings, monkeypatch):
    from fastapi.testclient import TestClient

    import backend.main as main

    captured = []
    monkeypatch.setattr("sentry_sdk.capture_exception", lambda exc=None, *a, **k: captured.append(("exc", exc)))
    monkeypatch.setattr("sentry_sdk.capture_message", lambda msg, *a, **k: captured.append(("msg", msg)))
    embeddings.error = RuntimeError("openai key expired")
    with TestClient(main.app) as c:
        body = c.get("/api/v1/health").json()
    assert body["status"] == "degraded" and body["kb_artifacts"] == 0
    assert "knowledge base empty" in body["problems"]
    assert any(kind == "exc" and "openai key expired" in str(e) for kind, e in captured)
    assert any(kind == "msg" and "knowledge base is empty" in m for kind, m in captured if kind == "msg")


def test_health_degraded_when_db_unreachable(client, monkeypatch):
    import backend.main as main

    async def boom():
        raise RuntimeError("connection refused")

    monkeypatch.setattr(main._storage, "count_artifacts", boom)
    body = client.get("/api/v1/health").json()
    assert body["status"] == "degraded" and body["db"] == "unreachable"


# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("origin,allowed", [
    ("https://recon-ai-git-foo-pranav.vercel.app", True),
    ("https://recon-ai-iota.vercel.app", True),
    ("http://localhost:5173", True),
    ("https://evil.example.com", False),
    ("https://evil.vercel.app.attacker.com", False),
])
def test_cors_preflight(client, origin, allowed):
    r = client.options("/api/v1/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})
    assert (r.headers.get("access-control-allow-origin") == origin) is allowed


# ---------------------------------------------------------------------------
# Analytics seed dates
# ---------------------------------------------------------------------------
def test_analytics_seed_dates_are_relative_and_idempotent(fake_db):
    from backend.seed import analytics_seed

    now = datetime(2027, 3, 15, 12, 0, tzinfo=timezone.utc)
    analytics_seed.main(client=fake_db, now=now)
    created = [datetime.fromisoformat(r["created_at"]) for r in fake_db.rows("rca_incidents")]
    runs = [datetime.fromisoformat(r["created_at"]) for r in fake_db.rows("recon_runs")]
    deploys = [datetime.fromisoformat(r["deployed_at"]) for r in fake_db.rows("deployment_events")]
    resolved = [datetime.fromisoformat(r["resolved_at"]) for r in fake_db.rows("resolutions")]
    end = datetime(2027, 3, 12, 23, 59, 59, tzinfo=timezone.utc)
    for series in (created, runs, deploys, resolved):
        assert series and max(series) <= end and min(series) >= now.replace(hour=0, minute=0) - (now - end) - \
            __import__("datetime").timedelta(days=30)
    assert (now - min(runs)).days <= 31, "window must sit inside the Analytics 30-day range"
    counts = {t: len(fake_db.rows(t)) for t in ("recon_runs", "rca_incidents", "deployment_events")}
    analytics_seed.main(client=fake_db, now=now)
    assert {t: len(fake_db.rows(t)) for t in counts} == counts, "second run must be skipped"


# ---------------------------------------------------------------------------
# Client IP
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("headers,env,expected", [
    ({"x-forwarded-for": "6.6.6.6, 203.0.113.9"}, {}, "203.0.113.9"),          # spoofed leftmost ignored
    ({"x-forwarded-for": "203.0.113.9"}, {}, "203.0.113.9"),
    ({"x-forwarded-for": "6.6.6.6, 203.0.113.9, 10.0.0.2"}, {"TRUSTED_PROXY_HOPS": "2"}, "203.0.113.9"),
    ({"x-forwarded-for": "203.0.113.9"}, {"TRUSTED_PROXY_HOPS": "3"}, "203.0.113.9"),
    ({"true-client-ip": "198.51.100.4", "x-forwarded-for": "6.6.6.6"}, {"TRUSTED_IP_HEADER": "True-Client-IP"}, "198.51.100.4"),
    ({"x-forwarded-for": "6.6.6.6"}, {"TRUSTED_IP_HEADER": "true-client-ip"}, "6.6.6.6"),  # header missing -> fallback
    ({}, {}, "peer"),
])
def test_client_ip(monkeypatch, headers, env, expected):
    from backend.main import client_ip

    for k in ("TRUSTED_IP_HEADER", "TRUSTED_PROXY_HOPS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert client_ip(headers, "peer") == expected
