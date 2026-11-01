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


def test_one_failing_row_does_not_stop_the_others(client, sample_csv_text, monkeypatch):
    import backend.main as main

    real = main._analyze_row

    async def flaky(row, *args, **kwargs):
        if row.sf_field == "Phone":
            raise RuntimeError("boom")
        return await real(row, *args, **kwargs)

    monkeypatch.setattr(main, "_analyze_row", flaky)
    events, _ = _run(client, sample_csv_text)
    errors = [e for e in events if e.get("event") == "error"]
    incidents = [e for e in events if e.get("event") == "incident"]
    assert len(errors) == 1 and "boom" in errors[0]["data"]["error"]
    assert len(incidents) == 9 and events[-1]["event"] == "done"
