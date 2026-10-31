"""Run the real FastAPI app on :8000 against the in-memory fakes, for browser tests.

    python -m backend.tests.e2e_server

No network: fake Supabase, fake LLM, fake embeddings. Optional scripting via env:
  E2E_REJECT_FIELD=<text>  the critic rejects claim C2 whenever the prompt mentions <text>
                           (rejected again after revision, so the incident escalates)
"""
from __future__ import annotations

import os


def main() -> None:
    import anthropic
    import groq
    import langchain_anthropic
    import langchain_groq
    import openai
    import supabase
    import uvicorn

    import backend.storage.supabase_adapter as adapter_module
    from backend.tests.fakes.fake_embeddings import FakeEmbeddings
    from backend.tests.fakes.fake_llm import FakeLLM, critic_reply
    from backend.tests.fakes.fake_supabase import FakeSupabase

    for key, value in {"SUPABASE_URL": "http://fake-supabase.local", "SUPABASE_SERVICE_KEY": "fake",
                       "OPENAI_API_KEY": "fake", "ANTHROPIC_API_KEY": "fake", "GROQ_API_KEY": "fake"}.items():
        os.environ[key] = value
    for key in ("ANTHROPIC_BASE_URL", "SENTRY_DSN", "RESEND_API_KEY", "NOTIFY_EMAIL"):
        os.environ.pop(key, None)

    db = FakeSupabase()
    adapter_module.create_client = lambda url, key: db
    supabase.create_client = lambda url, key: db

    llm = FakeLLM()
    reject = os.environ.get("E2E_REJECT_FIELD")
    if reject:
        llm.respond(lambda p: "strict reviewer checking an RCA explanation" in p and reject in p,
                    lambda p, m: critic_reply(p, {"C2": ("unsupported", "the fix names a step no evidence supports")}))
    anthropic.Anthropic = llm.anthropic_client
    groq.Groq = llm.groq_client
    langchain_anthropic.ChatAnthropic = llm.chat_model_class("langchain_anthropic")
    langchain_groq.ChatGroq = llm.chat_model_class("langchain_groq")
    openai.OpenAI = FakeEmbeddings().client

    import backend.main as app_module

    uvicorn.run(app_module.app, host="127.0.0.1", port=int(os.environ.get("E2E_PORT", "8000")), log_level="warning")


if __name__ == "__main__":
    main()
