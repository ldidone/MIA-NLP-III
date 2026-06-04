"""Central configuration loaded from environment variables.

Configuration is intentionally simple and read once at import time. Values come
from a ``.env`` file (via ``python-dotenv``) or the process environment.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

try:  # python-dotenv is optional at runtime; degrade gracefully if missing.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a dev convenience only.
    pass


# Project root = three levels up from this file:
# src/compufix_agents/config.py -> src/compufix_agents -> src -> <root>
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Parse a truthy environment string into a bool."""
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


# Valid values for the embedding backend selector.
VALID_EMBEDDING_BACKENDS = frozenset({"auto", "openai", "local", "none"})

# Default local (offline) embedding model. Small, fast, CPU-friendly.
DEFAULT_LOCAL_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class Settings(BaseModel):
    """Runtime settings for CompuFix Agents."""

    openai_api_key: str | None = None
    llm_provider: str = "openai"
    vectorstore_path: Path = PROJECT_ROOT / "data" / "vectorstore"
    knowledge_base_path: Path = PROJECT_ROOT / "data" / "raw" / "knowledge_base"
    allow_real_process_kill: bool = False

    # Embedding configuration for semantic retrieval.
    #   "auto"   -> OpenAI when a key is set, else local if available, else none
    #   "openai" -> OpenAI embeddings (requires API key + langchain-openai)
    #   "local"  -> local sentence-transformers embeddings (offline)
    #   "none"   -> disable embeddings; use the keyword fallback retriever
    embedding_backend: str = "auto"
    local_embedding_model: str = DEFAULT_LOCAL_EMBEDDING_MODEL

    @property
    def llm_enabled(self) -> bool:
        """True when an API key is configured and an LLM path can be used."""
        return bool(self.openai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings parsed from the environment."""
    vectorstore = os.getenv("VECTORSTORE_PATH")
    backend = (os.getenv("EMBEDDING_BACKEND") or "auto").strip().lower()
    if backend not in VALID_EMBEDDING_BACKENDS:
        backend = "auto"
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        vectorstore_path=(
            Path(vectorstore) if vectorstore else PROJECT_ROOT / "data" / "vectorstore"
        ),
        allow_real_process_kill=_as_bool(os.getenv("ALLOW_REAL_PROCESS_KILL"), default=False),
        embedding_backend=backend,
        local_embedding_model=(os.getenv("LOCAL_EMBEDDING_MODEL") or DEFAULT_LOCAL_EMBEDDING_MODEL),
    )
