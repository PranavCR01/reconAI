"""Rows in a run are analyzed concurrently, bounded by ROW_CONCURRENCY, and each is streamed once."""
import threading
import time

import pytest

from backend.tests.fakes.fake_llm import proposal_reply
from backend.tests.helpers import SYNTHESIS_PROMPT, stream_events, upload_csv

DELAY = 0.25


@pytest.fixture
def slow_proposer(llm):
    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def reply(prompt, model):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(DELAY)
        with lock:
            state["active"] -= 1
        return proposal_reply(prompt, 0.9)

    llm.respond(SYNTHESIS_PROMPT, reply)
    return state


def _run(client, csv_text):
    run_id = upload_csv(client, csv_text).json()["run_id"]
    t0 = time.monotonic()
    events = stream_events(client, run_id)
    return events, time.monotonic() - t0


@pytest.mark.parametrize("limit", [1, 4])
def test_rows_run_concurrently_up_to_the_limit(client, sample_csv_text, slow_proposer, monkeypatch, limit):
    import backend.main as main

    monkeypatch.setattr(main, "ROW_CONCURRENCY", limit)
    events, elapsed = _run(client, sample_csv_text)
    incidents = [e for e in events if e.get("event") == "incident"]
    assert sorted(e["data"]["row_index"] for e in incidents) == list(range(10)), "each row exactly once"
    assert events[-1]["event"] == "done"
    assert slow_proposer["peak"] == limit, f"peak concurrency {slow_proposer['peak']}, limit {limit}"
    if limit == 1:
        assert elapsed >= 10 * DELAY
    else:
        assert elapsed < 10 * DELAY * 0.6, f"{elapsed:.2f}s is not faster than sequential"


def test_one_failing_row_does_not_stop_the_others(client, sample_csv_text, monkeypatch, capsys):
    import backend.main as main

    real = main._analyze_row

    async def flaky(row, *args, **kwargs):
        if row.sf_field == "Phone":
            raise RuntimeError("boom")
        return await real(row, *args, **kwargs)

    monkeypatch.setattr(main, "_analyze_row", flaky)
    events, _ = _run(client, sample_csv_text)
    assert not [e for e in events if e.get("event") == "error"], "a row failure must not look like a stream failure"
    row_errors = [e for e in events if e.get("event") == "row_error"]
    incidents = [e for e in events if e.get("event") == "incident"]
    assert len(row_errors) == 1 and "boom" in row_errors[0]["data"]["error"]
    assert len(incidents) == 9 and events[-1]["event"] == "done"
    assert "row" in capsys.readouterr().out and "boom" in "".join(e["data"]["error"] for e in row_errors), \
        "row failures are logged, not silent"


def test_keepalive_while_rows_are_slow(client, sample_csv_text, slow_proposer, monkeypatch):
    import backend.main as main

    monkeypatch.setattr(main, "SSE_KEEPALIVE_S", 0.05)
    run_id = upload_csv(client, sample_csv_text).json()["run_id"]
    with client.stream("GET", f"/api/v1/recon/runs/{run_id}/stream") as response:
        lines = list(response.iter_lines())
    assert ": keep-alive" in lines, "silent gaps must carry keep-alive comments"
    assert lines.count("event: incident") == 10 and "event: done" in lines


def test_database_calls_never_overlap():
    """The postgrest client shares one HTTP/2 connection, so the adapter serializes calls."""
    import asyncio
    from types import SimpleNamespace as NS

    from backend.storage.supabase_adapter import SupabaseAdapter

    state = {"active": 0, "peak": 0}
    lock = threading.Lock()

    def execute():
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.02)
        with lock:
            state["active"] -= 1
        return NS(data=[], count=0)

    query = NS(execute=execute)
    query.select = lambda *a, **k: query
    query.limit = lambda *a, **k: query
    client = NS(table=lambda name: query, rpc=lambda *a, **k: query)
    adapter = SupabaseAdapter(client)

    async def burst():
        await asyncio.gather(*(adapter.count_artifacts() for _ in range(8)),
                             *(asyncio.to_thread(adapter.search_artifacts_sync, [0.0]) for _ in range(4)))

    asyncio.run(burst())
    assert state["peak"] == 1
