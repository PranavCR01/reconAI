"""The browser-test server: real-model mode must never point at a real database."""
import pytest

from backend.tests.e2e_server import FAKE_DB_ENV, SetupError, plan


def test_scripted_mode_fakes_everything():
    p = plan({"ANTHROPIC_API_KEY": "real-key", "SUPABASE_URL": "https://prod.supabase.co"})
    assert not p["real_llm"] and not p["real_embeddings"]
    assert p["set"]["ANTHROPIC_API_KEY"] == "fake" and p["set"]["SUPABASE_URL"] == FAKE_DB_ENV["SUPABASE_URL"]


def test_real_mode_uses_your_keys_but_never_your_database():
    p = plan({"E2E_REAL_LLM": "1", "ANTHROPIC_API_KEY": "sk-real", "OPENAI_API_KEY": "sk-oai",
              "SUPABASE_URL": "https://prod.supabase.co", "SUPABASE_SERVICE_KEY": "prod-secret"})
    assert p["real_llm"] and p["real_embeddings"]
    assert p["set"]["ANTHROPIC_API_KEY"] == "sk-real"
    assert p["set"]["SUPABASE_URL"] == FAKE_DB_ENV["SUPABASE_URL"] and p["set"]["SUPABASE_SERVICE_KEY"] == "fake"
    assert "OPENAI_API_KEY" not in p["set"], "a real OpenAI key is left as is"


def test_real_mode_maps_the_tprm_key_and_fakes_missing_embeddings():
    p = plan({"E2E_REAL_LLM": "true", "TPRM_ANTHROPIC_API_KEY": "sk-tprm"})
    assert p["set"]["ANTHROPIC_API_KEY"] == "sk-tprm"
    assert not p["real_embeddings"] and p["set"]["OPENAI_API_KEY"] == "fake"


@pytest.mark.parametrize("env,message", [
    ({"E2E_REAL_LLM": "1"}, "ANTHROPIC_API_KEY"),
    ({"E2E_REAL_LLM": "1", "LLM_CONFIG": "groq"}, "GROQ_API_KEY"),
    ({"E2E_REAL_LLM": "1", "LLM_CONFIG": "hybrid", "ANTHROPIC_API_KEY": "k"}, "GROQ_API_KEY"),
])
def test_real_mode_refuses_without_keys(env, message):
    with pytest.raises(SetupError, match=message):
        plan(env)


def test_groq_config_needs_no_anthropic_key():
    p = plan({"E2E_REAL_LLM": "1", "LLM_CONFIG": "groq", "GROQ_API_KEY": "gsk"})
    assert p["config"] == "groq" and "ANTHROPIC_API_KEY" not in p["set"]
