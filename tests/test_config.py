import pytest

from agent.config import load_config


def _set_required_env(monkeypatch):
    monkeypatch.setenv("LIVEKIT_URL", "wss://test.livekit.cloud")
    monkeypatch.setenv("LIVEKIT_API_KEY", "testkey")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "testsecret")
    monkeypatch.setenv("SARVAM_API_KEY", "testsarvamkey")


def test_missing_required_var_raises(monkeypatch):
    monkeypatch.delenv("LIVEKIT_URL", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    monkeypatch.delenv("SARVAM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="Missing required environment variable"):
        load_config()


def test_defaults_to_gemini(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("BVHOMES_LLM_PROVIDER", raising=False)
    cfg = load_config()
    assert cfg.llm_provider == "gemini"


def test_ollama_provider_accepted(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BVHOMES_LLM_PROVIDER", "ollama")
    cfg = load_config()
    assert cfg.llm_provider == "ollama"
    assert cfg.ollama_base_url  # has a sensible default
    assert cfg.ollama_model


def test_database_url_is_optional_and_preserved(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db.example/bvhomes")
    assert load_config().database_url == "postgresql://user:pass@db.example/bvhomes"


def test_invalid_database_url_rejected(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("DATABASE_URL", "mysql://db.example/bvhomes")
    with pytest.raises(RuntimeError, match="DATABASE_URL must start"):
        load_config()


def test_invalid_llm_provider_rejected(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.setenv("BVHOMES_LLM_PROVIDER", "chatgpt")
    with pytest.raises(RuntimeError, match="must be 'gemini' or 'ollama'"):
        load_config()
