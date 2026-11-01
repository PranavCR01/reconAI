"""Run the real FastAPI app on :8000 against an in-memory database, for browser testing.

    python -m backend.tests.e2e_server                 # scripted model, free, no keys needed
    E2E_REAL_LLM=1 python -m backend.tests.e2e_server  # real Anthropic/Groq calls from your .env

The database is ALWAYS the in-memory fake: nothing is read from or written to Supabase,
and restarting the server wipes all runs.

Options (environment variables):
  E2E_REAL_LLM=1           use real models. Keys come from .env / the environment
                           (ANTHROPIC_API_KEY or TPRM_ANTHROPIC_API_KEY; GROQ_API_KEY for the
                           groq/hybrid configs chosen with LLM_CONFIG). Embeddings are real when
                           OPENAI_API_KEY is set, otherwise faked. Every analyzed row costs money.
  E2E_REJECT_FIELD=<text>  scripted mode only: the critic rejects claim C2 whenever the prompt
                           mentions <text> (rejected again after revision, so it escalates)
  E2E_PORT=<port>          default 8000
"""
from __future__ import annotations

import os
import sys

FAKE_DB_ENV = {"SUPABASE_URL": "http://fake-supabase.local", "SUPABASE_SERVICE_KEY": "fake"}
QUIET_ENV = ("SENTRY_DSN", "RESEND_API_KEY", "NOTIFY_EMAIL")


class SetupError(RuntimeError):
    pass


def plan(env: dict) -> dict:
    """Decide what is real and what is faked, from the environment. Pure, so it can be tested."""
    real_llm = env.get("E2E_REAL_LLM", "").strip().lower() in ("1", "true", "yes")
    config = env.get("LLM_CONFIG", "claude")
    if not real_llm:
        return {"real_llm": False, "real_embeddings": False, "config": "claude",
                "set": {**FAKE_DB_ENV, "OPENAI_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake", "GROQ_API_KEY": "fake"},
                "unset": ("ANTHROPIC_BASE_URL", *QUIET_ENV)}

    to_set = dict(FAKE_DB_ENV)
    anthropic_key = env.get("ANTHROPIC_API_KEY") or env.get("TPRM_ANTHROPIC_API_KEY")
    if config in ("claude", "hybrid"):
        if not anthropic_key:
            raise SetupError("E2E_REAL_LLM needs ANTHROPIC_API_KEY (or TPRM_ANTHROPIC_API_KEY) in .env or the environment")
        to_set["ANTHROPIC_API_KEY"] = anthropic_key
    if config in ("groq", "hybrid") and not env.get("GROQ_API_KEY"):
        raise SetupError(f"LLM_CONFIG={config} needs GROQ_API_KEY")
    real_embeddings = bool(env.get("OPENAI_API_KEY"))
    if not real_embeddings:
        to_set["OPENAI_API_KEY"] = "fake"
    return {"real_llm": True, "real_embeddings": real_embeddings, "config": config, "set": to_set,
            "unset": QUIET_ENV}


def main() -> None:
    from dotenv import load_dotenv

    load_dotenv()  # .env values for real mode; existing environment variables win
    try:
        p = plan(dict(os.environ))
    except SetupError as exc:
        print(f"Cannot start: {exc}", file=sys.stderr)
        raise SystemExit(2)
    os.environ.update(p["set"])
    for key in p["unset"]:
        os.environ.pop(key, None)

    import openai
    import supabase
    import uvicorn

    import backend.storage.supabase_adapter as adapter_module
    from backend.tests.fakes.fake_embeddings import FakeEmbeddings
    from backend.tests.fakes.fake_supabase import FakeSupabase

    db = FakeSupabase()
    adapter_module.create_client = lambda url, key: db
    supabase.create_client = lambda url, key: db
    if not p["real_embeddings"]:
        openai.OpenAI = FakeEmbeddings().client

    if p["real_llm"]:
        from backend.config import CONFIGS

        cfg = CONFIGS[p["config"]]
        print(f"REAL MODELS ({p['config']}): proposer {cfg.synthesis_llm}, critic {cfg.critic_llm}, "
              f"reranker {cfg.reranker_llm}. Embeddings: {'real (OpenAI)' if p['real_embeddings'] else 'fake'}. "
              "Database: in-memory. Each analyzed row costs roughly $0.03-0.06.", flush=True)
    else:
        import anthropic
        import groq
        import langchain_anthropic
        import langchain_groq

        from backend.tests.fakes.fake_llm import FakeLLM, critic_reply

        llm = FakeLLM()
        reject = os.environ.get("E2E_REJECT_FIELD")
        if reject:
            llm.respond(lambda q: "strict reviewer checking an RCA explanation" in q and reject in q,
                        lambda q, m: critic_reply(q, {"C2": ("unsupported", "the fix names a step no evidence supports")}))
        anthropic.Anthropic = llm.anthropic_client
        groq.Groq = llm.groq_client
        langchain_anthropic.ChatAnthropic = llm.chat_model_class("langchain_anthropic")
        langchain_groq.ChatGroq = llm.chat_model_class("langchain_groq")
        print("SCRIPTED MODEL: free, deterministic. Database: in-memory.", flush=True)

    import backend.main as app_module

    port = int(os.environ.get("E2E_PORT", "8000"))
    print(f"Serving on http://127.0.0.1:{port} (frontend: cd frontend && npm run dev)", flush=True)
    uvicorn.run(app_module.app, host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
