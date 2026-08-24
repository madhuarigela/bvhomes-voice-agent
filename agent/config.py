"""Environment-variable configuration, validated at startup.

Fails loudly and clearly if required values are missing, instead of letting
the agent start and crash confusingly on the first STT/LLM/TTS call.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

# Vars that MUST be present for the agent to function at all.
_REQUIRED_VARS = [
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SARVAM_API_KEY",
]

# Vars that are optional but change behavior if present.
_OPTIONAL_VARS = {
    "GOOGLE_API_KEY": None,  # only needed if NOT routing Gemini via LiveKit Inference
    "BVHOMES_DB_PATH": "data/leads.db",
    "DATABASE_URL": None,  # PostgreSQL in production; SQLite remains the local default
    "BVHOMES_LOG_LEVEL": "INFO",
    "BVHOMES_TTS_SPEAKER": "anushka",
    "BVHOMES_LLM_PROVIDER": "gemini",  # "gemini" (default, recommended) | "ollama" (opt-in, local, cost-zero)
    "BVHOMES_OLLAMA_BASE_URL": "http://localhost:11434/v1",
    "BVHOMES_OLLAMA_MODEL": "llama3.3:8b",
}


@dataclass(frozen=True)
class AgentConfig:
    livekit_url: str
    livekit_api_key: str
    livekit_api_secret: str
    sarvam_api_key: str
    google_api_key: str | None
    db_path: str
    database_url: str | None
    log_level: str
    tts_speaker: str
    llm_provider: str
    ollama_base_url: str
    ollama_model: str


def load_config() -> AgentConfig:
    missing = [v for v in _REQUIRED_VARS if not os.environ.get(v)]
    if missing:
        raise RuntimeError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and fill these in. See README.md."
        )

    llm_provider = os.environ.get(
        "BVHOMES_LLM_PROVIDER", _OPTIONAL_VARS["BVHOMES_LLM_PROVIDER"]
    ).lower()
    if llm_provider not in ("gemini", "ollama"):
        raise RuntimeError(
            f"BVHOMES_LLM_PROVIDER must be 'gemini' or 'ollama', got {llm_provider!r}."
        )

    database_url = os.environ.get("DATABASE_URL") or None
    if database_url and not database_url.startswith(("postgresql://", "postgres://")):
        raise RuntimeError("DATABASE_URL must start with postgresql:// or postgres://.")

    return AgentConfig(
        livekit_url=os.environ["LIVEKIT_URL"],
        livekit_api_key=os.environ["LIVEKIT_API_KEY"],
        livekit_api_secret=os.environ["LIVEKIT_API_SECRET"],
        sarvam_api_key=os.environ["SARVAM_API_KEY"],
        google_api_key=os.environ.get("GOOGLE_API_KEY"),
        db_path=os.environ.get("BVHOMES_DB_PATH", _OPTIONAL_VARS["BVHOMES_DB_PATH"]),
        database_url=database_url,
        log_level=os.environ.get("BVHOMES_LOG_LEVEL", _OPTIONAL_VARS["BVHOMES_LOG_LEVEL"]),
        tts_speaker=os.environ.get("BVHOMES_TTS_SPEAKER", _OPTIONAL_VARS["BVHOMES_TTS_SPEAKER"]),
        llm_provider=llm_provider,
        ollama_base_url=os.environ.get(
            "BVHOMES_OLLAMA_BASE_URL", _OPTIONAL_VARS["BVHOMES_OLLAMA_BASE_URL"]
        ),
        ollama_model=os.environ.get(
            "BVHOMES_OLLAMA_MODEL", _OPTIONAL_VARS["BVHOMES_OLLAMA_MODEL"]
        ),
    )
