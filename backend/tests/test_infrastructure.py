"""Guard, smoke E2E and determinism tests for the test harness itself."""
import httpx
import pytest

from backend.tests.conftest import NetworkBlocked
from backend.tests.helpers import run_sample

SEVERITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, None: 3}


def test_network_guard_blocks_real_calls():
    with pytest.raises(Exception) as exc:
        httpx.get("https://example.com", timeout=2)
    chain = [exc.value, exc.value.__cause__, exc.value.__context__]
    assert any(isinstance(e, NetworkBlocked) for e in chain), f"expected NetworkBlocked, got {exc.value!r}"


def test_fake_llm_is_installed(llm):
    import anthropic

    reply = anthropic.Anthropic().messages.create(model="m", max_tokens=5, messages=[{"role": "user", "content": "Reply with exactly one of A | B"}])
    assert reply.content[0].text == llm.classification
    assert llm.calls[-1]["model"] == "m"


def test_smoke_upload_stream_and_fetch(client, sample_csv_text, llm, embeddings):
    run_id, events = run_sample(client, sample_csv_text)
    kinds = [e["event"] for e in events]
    assert kinds.count("incident") == 10, kinds
    assert kinds[-1] == "done"
    assert "error" not in kinds

    body = client.get(f"/api/v1/recon/runs/{run_id}").json()
    assert body["run"]["status"] == "complete"
    assert body["rows_scanned"] == 10 and body["total_incidents"] == 10
    severities = [i["severity"] for i in body["incidents"]]
    assert severities == sorted(severities, key=SEVERITY_ORDER.get), "P1 incidents must come first (NN#5)"
    # Every LLM call went through the fake (the network guard would have raised otherwise).
    assert llm.calls and all("error" not in c for c in llm.calls)
    assert embeddings.calls, "knowledge base seeding and retrieval should embed through the fake"


def _signature(client, csv_text, session):
    run_id, _ = run_sample(client, csv_text, params=f"?session_id={session}")
    incidents = client.get(f"/api/v1/recon/runs/{run_id}").json()["incidents"]
    return sorted(
        (i["severity"], i["final_hypothesis"], tuple(i["hypotheses_tested"]), tuple(i["hypotheses_ruled_out"]))
        for i in incidents
    )


def test_pipeline_is_deterministic(client, sample_csv_text):
    """Tool simulators are seeded by input, so graph outcomes must repeat exactly."""
    # Different sessions -> different cache keys -> both runs are fresh analyses.
    first = _signature(client, sample_csv_text, "determinism-a")
    second = _signature(client, sample_csv_text, "determinism-b")
    assert first == second
