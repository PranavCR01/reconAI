"""Shared fixtures: every test runs the real backend against in-memory fakes.

Autouse fixtures install a fresh fake Supabase, fake LLM clients and fake embeddings,
reset module-level caches, and block real network access. Tests that genuinely need
a real model are marked `live_llm` and skip the fakes and the guard.
"""
from __future__ import annotations

import csv
import io
import json
import socket
from pathlib import Path

import pytest

from backend.tests.fakes.fake_embeddings import FakeEmbeddings
from backend.tests.fakes.fake_llm import FakeLLM
from backend.tests.fakes.fake_supabase import FakeSupabase

REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_CSV = REPO_ROOT / "data" / "sample_fsc_recon.csv"
GROUND_TRUTH = REPO_ROOT / "data" / "benchmark_ground_truth.json"


class NetworkBlocked(RuntimeError):
    pass


def _is_live(request) -> bool:
    return request.node.get_closest_marker("live_llm") is not None


# ---------------------------------------------------------------------------
# Guard: no real network outside live_llm tests
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def network_guard(request, monkeypatch):
    if _is_live(request):
        yield
        return
    real_connect = socket.socket.connect

    def guarded_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if sock.family == socket.AF_UNIX or host in ("127.0.0.1", "::1", "localhost"):
            return real_connect(sock, address)
        raise NetworkBlocked(f"test attempted a real network connection to {address!r}")

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host in ("127.0.0.1", "::1", "localhost", None):
            return real_getaddrinfo(host, *args, **kwargs)
        raise NetworkBlocked(f"test attempted DNS lookup for {host!r}")

    real_getaddrinfo = socket.getaddrinfo
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
    yield


# ---------------------------------------------------------------------------
# Environment + fakes
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def test_env(request, monkeypatch):
    if _is_live(request):
        yield
        return
    for key, value in {
        "SUPABASE_URL": "http://fake-supabase.local",
        "SUPABASE_SERVICE_KEY": "fake-service-key",
        "OPENAI_API_KEY": "fake-openai-key",
        "ANTHROPIC_API_KEY": "fake-anthropic-key",
        "GROQ_API_KEY": "fake-groq-key",
    }.items():
        monkeypatch.setenv(key, value)
    # A proxy on localhost would let real requests slip past the network guard.
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    for key in ("LLM_CONFIG", "SENTRY_DSN", "RESEND_API_KEY", "NOTIFY_EMAIL", "ANTHROPIC_BASE_URL",
                "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture(autouse=True)
def fake_db(request, monkeypatch):
    if _is_live(request):
        yield None
        return
    import supabase

    import backend.storage.supabase_adapter as adapter_module

    db = FakeSupabase()
    monkeypatch.setattr(adapter_module, "create_client", lambda url, key: db)
    monkeypatch.setattr(supabase, "create_client", lambda url, key: db)
    yield db


@pytest.fixture(autouse=True)
def llm(request, monkeypatch):
    if _is_live(request):
        yield None
        return
    import anthropic
    import groq
    import langchain_anthropic
    import langchain_groq

    fake = FakeLLM()
    monkeypatch.setattr(anthropic, "Anthropic", fake.anthropic_client)
    monkeypatch.setattr(groq, "Groq", fake.groq_client)
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", fake.chat_model_class("langchain_anthropic"))
    monkeypatch.setattr(langchain_groq, "ChatGroq", fake.chat_model_class("langchain_groq"))
    yield fake


@pytest.fixture(autouse=True)
def embeddings(request, monkeypatch):
    if _is_live(request):
        yield None
        return
    import openai

    fake = FakeEmbeddings()
    monkeypatch.setattr(openai, "OpenAI", fake.client)
    yield fake


@pytest.fixture(autouse=True)
def reset_app_state(request):
    """Module-level caches in main.py must not leak between tests."""
    if _is_live(request):
        yield
        return
    import backend.main as main

    def _reset():
        main._recall_cache.update({"data": None, "ts": 0})
        main._analytics_cache.clear()
        main._rate_events.clear()

    _reset()
    yield
    _reset()


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def storage(fake_db):
    from backend.storage.supabase_adapter import SupabaseAdapter

    return SupabaseAdapter(fake_db)


@pytest.fixture
def client(fake_db, llm, embeddings):
    """FastAPI TestClient with the real lifespan (seeds the RAG knowledge base)."""
    from fastapi.testclient import TestClient

    import backend.main as main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def sample_csv_text() -> str:
    return SAMPLE_CSV.read_text()


@pytest.fixture
def sample_rows(sample_csv_text) -> list[dict]:
    return list(csv.DictReader(io.StringIO(sample_csv_text)))


@pytest.fixture(scope="session")
def ground_truth() -> list[dict]:
    return json.loads(GROUND_TRUTH.read_text())["incidents"]


@pytest.fixture
def scenarios():
    """Declare scenarios for test-only records; the registry is restored afterwards.

    Usage: scenarios.add("REC-1", "NO_FAULT_FOUND", confounders=["unrelated_missed_event"])
    """
    from backend.tools import world

    original = dict(world.registry())

    class _Scenarios:
        def add(self, record_id: str, fault: str, confounders=(), source: str = "test"):
            current = dict(world.registry())
            current[record_id] = world.Scenario(record_id, fault, frozenset(confounders), source)
            world.set_registry(current)

    yield _Scenarios()
    world.set_registry(original)
