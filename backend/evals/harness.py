"""Execution environments for eval runs.

Both modes use the in-memory fake Supabase running the real SupabaseAdapter, so an eval
can never write to the production database.

- offline: scripted fake LLM and fake embeddings. Deterministic, free, runs in CI.
  Measures the graph and the deterministic critic; model-dependent numbers come from a
  scripted model and are labeled as such.
- live: real Anthropic/Groq models. Embeddings are real only when OPENAI_API_KEY is
  set; otherwise they are faked and retrieval is reported as not measured.
"""
from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field


class LiveRunRefused(RuntimeError):
    pass


@dataclass
class Env:
    mode: str
    storage: object
    db: object
    real_embeddings: bool
    fake_llm: object | None = None
    notes: list[str] = field(default_factory=list)


@contextlib.contextmanager
def _patched(patches: list[tuple[object, str, object]]):
    saved = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]
    try:
        for obj, name, value in patches:
            setattr(obj, name, value)
        yield
    finally:
        for obj, name, value in reversed(saved):
            setattr(obj, name, value)


@contextlib.contextmanager
def _env_vars(set_vars: dict[str, str], unset: tuple[str, ...]):
    saved = {k: os.environ.get(k) for k in [*set_vars, *unset]}
    try:
        for k in unset:
            os.environ.pop(k, None)
        os.environ.update(set_vars)
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _fake_storage():
    from backend.storage.supabase_adapter import SupabaseAdapter
    from backend.tests.fakes.fake_supabase import FakeSupabase

    db = FakeSupabase()
    return SupabaseAdapter(db), db


def check_live_allowed(config_key: str, yes: bool, storage) -> None:
    """Refuse a live run unless storage is the in-memory fake, spending is confirmed and keys exist."""
    from backend.tests.fakes.fake_supabase import FakeSupabase

    if not isinstance(getattr(storage, "_client", None), FakeSupabase):
        raise LiveRunRefused("live evals must use the in-memory fake database, never a real Supabase client")
    if not yes:
        raise LiveRunRefused("live evals spend money on API calls; re-run with --yes to confirm")
    if config_key in ("claude", "hybrid") and not (os.environ.get("ANTHROPIC_API_KEY") or
                                                    os.environ.get("TPRM_ANTHROPIC_API_KEY")):
        raise LiveRunRefused("no Anthropic API key (set TPRM_ANTHROPIC_API_KEY or ANTHROPIC_API_KEY)")
    if config_key in ("groq", "hybrid") and not os.environ.get("GROQ_API_KEY"):
        raise LiveRunRefused("no GROQ_API_KEY for a config that uses Groq")


@contextlib.contextmanager
def environment(mode: str, config_key: str = "claude", yes: bool = False):
    import anthropic
    import groq
    import langchain_anthropic
    import langchain_groq
    import openai

    from backend.tests.fakes.fake_embeddings import FakeEmbeddings
    from backend.tests.fakes.fake_llm import FakeLLM

    storage, db = _fake_storage()
    if mode == "offline":
        fake = FakeLLM()
        patches = [(anthropic, "Anthropic", fake.anthropic_client), (groq, "Groq", fake.groq_client),
                   (langchain_anthropic, "ChatAnthropic", fake.chat_model_class("langchain_anthropic")),
                   (langchain_groq, "ChatGroq", fake.chat_model_class("langchain_groq")),
                   (openai, "OpenAI", FakeEmbeddings().client)]
        env_set = {"OPENAI_API_KEY": "offline", "ANTHROPIC_API_KEY": "offline", "GROQ_API_KEY": "offline"}
        with _env_vars(env_set, ("ANTHROPIC_BASE_URL",)), _patched(patches):
            yield Env("offline", storage, db, real_embeddings=False, fake_llm=fake,
                      notes=["offline: scripted fake LLM and fake embeddings"])
        return

    if mode != "live":
        raise ValueError(f"unknown mode {mode}")
    check_live_allowed(config_key, yes, storage)
    env_set = {}
    if not os.environ.get("ANTHROPIC_API_KEY") and os.environ.get("TPRM_ANTHROPIC_API_KEY"):
        env_set["ANTHROPIC_API_KEY"] = os.environ["TPRM_ANTHROPIC_API_KEY"]
    real_embeddings = bool(os.environ.get("OPENAI_API_KEY"))
    patches = [] if real_embeddings else [(openai, "OpenAI", FakeEmbeddings().client)]
    if not real_embeddings:
        env_set["OPENAI_API_KEY"] = "fake-embeddings"
    notes = ["live: real LLM calls"] + ([] if real_embeddings else
                                       ["no OPENAI_API_KEY: embeddings faked, retrieval not measured"])
    with _env_vars(env_set, ("ANTHROPIC_BASE_URL",)), _patched(patches):
        yield Env("live", storage, db, real_embeddings=real_embeddings, notes=notes)
