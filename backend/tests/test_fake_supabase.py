"""The fake must behave like PostgREST where SupabaseAdapter depends on it.

If these drift from real Supabase semantics, every other test becomes untrustworthy.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.models.entities import Resolution, FixType
from backend.tests.fakes.fake_supabase import APIError, FakeSupabase, cosine


def test_insert_returns_rows_with_generated_defaults():
    db = FakeSupabase()
    out = db.table("recon_runs").insert({"status": "pending"}).execute().data
    assert len(out) == 1
    assert out[0]["id"] and out[0]["created_at"] and out[0]["status"] == "pending"
    datetime.fromisoformat(out[0]["created_at"])  # valid ISO timestamp


def test_insert_keeps_explicit_id_and_timestamp():
    db = FakeSupabase()
    row = db.table("recon_runs").insert({"id": "abc", "created_at": "2026-01-01T00:00:00+00:00"}).execute().data[0]
    assert row["id"] == "abc" and row["created_at"] == "2026-01-01T00:00:00+00:00"


def test_bulk_insert():
    db = FakeSupabase()
    out = db.table("recon_rows").insert([{"n": 1}, {"n": 2}, {"n": 3}]).execute().data
    assert [r["n"] for r in out] == [1, 2, 3]
    assert len({r["id"] for r in out}) == 3


def test_single_raises_on_zero_and_multiple_rows():
    db = FakeSupabase()
    with pytest.raises(APIError):
        db.table("recon_runs").select("*").eq("id", "missing").single().execute()
    db.table("recon_runs").insert([{"k": "x"}, {"k": "x"}]).execute()
    with pytest.raises(APIError):
        db.table("recon_runs").select("*").eq("k", "x").single().execute()


def test_single_returns_dict():
    db = FakeSupabase()
    rid = db.table("recon_runs").insert({"k": 1}).execute().data[0]["id"]
    assert db.table("recon_runs").select("*").eq("id", rid).single().execute().data["k"] == 1


def test_upsert_on_conflict_updates_in_place_and_keeps_id():
    db = FakeSupabase()
    first = db.table("resolutions").upsert({"incident_id": "i1", "fix_type": "other"}, on_conflict="incident_id").execute().data[0]
    second = db.table("resolutions").upsert({"incident_id": "i1", "fix_type": "data_backfill"}, on_conflict="incident_id").execute().data[0]
    rows = db.rows("resolutions")
    assert len(rows) == 1
    assert rows[0]["fix_type"] == "data_backfill"
    assert first["id"] == second["id"] == rows[0]["id"]


def test_cache_upsert_keys_on_cache_key():
    db = FakeSupabase()
    db.table("rca_cache").upsert({"cache_key": "k", "rca_output": {"v": 1}}).execute()
    db.table("rca_cache").upsert({"cache_key": "k", "rca_output": {"v": 2}}).execute()
    rows = db.rows("rca_cache")
    assert len(rows) == 1 and rows[0]["rca_output"] == {"v": 2}


def test_gte_compares_timestamps_as_datetimes():
    db = FakeSupabase()
    now = datetime.now(timezone.utc)
    db.table("rca_incidents").insert([
        {"n": "old", "created_at": (now - timedelta(days=40)).isoformat()},
        {"n": "new", "created_at": (now - timedelta(days=2)).isoformat().replace("+00:00", "Z")},
    ]).execute()
    since = (now - timedelta(days=30)).isoformat()
    got = db.table("rca_incidents").select("*").gte("created_at", since).execute().data
    assert [r["n"] for r in got] == ["new"]


def test_in_eq_neq_filters():
    db = FakeSupabase()
    db.table("t").insert([{"k": "a", "v": 1}, {"k": "b", "v": 2}, {"k": "c", "v": 3}]).execute()
    assert {r["k"] for r in db.table("t").select("*").in_("k", ["a", "c"]).execute().data} == {"a", "c"}
    assert {r["k"] for r in db.table("t").select("*").neq("k", "a").execute().data} == {"b", "c"}
    assert db.table("t").select("*").eq("v", 2).execute().data[0]["k"] == "b"


def test_count_exact_ignores_limit():
    db = FakeSupabase()
    db.table("t").insert([{"i": i} for i in range(7)]).execute()
    resp = db.table("t").select("id", count="exact").limit(2).execute()
    assert resp.count == 7 and len(resp.data) == 2


def test_order_desc():
    db = FakeSupabase()
    db.table("t").insert([{"d": "2026-01-02T00:00:00+00:00"}, {"d": "2026-01-03T00:00:00+00:00"},
                          {"d": "2026-01-01T00:00:00+00:00"}]).execute()
    got = [r["d"][:10] for r in db.table("t").select("*").order("d", desc=True).execute().data]
    assert got == ["2026-01-03", "2026-01-02", "2026-01-01"]


def test_update_and_delete():
    db = FakeSupabase()
    rid = db.table("recon_runs").insert({"status": "pending"}).execute().data[0]["id"]
    db.table("recon_runs").update({"status": "complete"}).eq("id", rid).execute()
    assert db.rows("recon_runs")[0]["status"] == "complete"
    db.table("recon_runs").delete().eq("id", rid).execute()
    assert db.rows("recon_runs") == []


def test_match_artifacts_threshold_sort_and_limit():
    db = FakeSupabase()
    db.table("recon_artifacts").insert([
        {"name": "same", "embedding": [1.0, 0.0]},
        {"name": "close", "embedding": [0.8, 0.6]},
        {"name": "far", "embedding": [0.0, 1.0]},
        {"name": "no-emb"},
    ]).execute()
    got = db.rpc("match_artifacts", {"query_embedding": [1.0, 0.0], "match_threshold": 0.4, "match_count": 5}).execute().data
    assert [r["name"] for r in got] == ["same", "close"]
    assert got[0]["similarity"] == pytest.approx(1.0) and got[1]["similarity"] == pytest.approx(0.8)
    assert "embedding" not in got[0]
    limited = db.rpc("match_artifacts", {"query_embedding": [1.0, 0.0], "match_threshold": 0.0, "match_count": 1}).execute().data
    assert [r["name"] for r in limited] == ["same"]


def test_cosine():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([0, 0], [1, 1]) == 0.0


def test_injected_failure():
    db = FakeSupabase()
    db.fail_tables["rca_incidents"] = True
    with pytest.raises(APIError):
        db.table("rca_incidents").insert({"x": 1}).execute()


def test_real_adapter_round_trip_through_fake(storage, fake_db):
    """The real SupabaseAdapter works unmodified on top of the fake."""
    rid = asyncio.run(storage.save_resolution(Resolution(
        incident_id="00000000-0000-0000-0000-000000000001", confirmed_root_cause="x",
        fix_applied="y", fix_type=FixType.other, resolved_by="t")))
    got = asyncio.run(storage.get_resolution_for_incident("00000000-0000-0000-0000-000000000001"))
    assert got is not None and str(got.id) == rid
