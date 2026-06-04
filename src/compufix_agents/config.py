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


class Settings(BaseModel):
    """Runtime settings for CompuFix Agents."""

    openai_api_key: str | None = None
    llm_provider: str = "openai"
    vectorstore_path: Path = PROJECT_ROOT / "data" / "vectorstore"
    knowledge_base_path: Path = PROJECT_ROOT / "data" / "raw" / "knowledge_base"
    allow_real_process_kill: bool = False

    @property
    def llm_enabled(self) -> bool:
        """True when an API key is configured and an LLM path can be used."""
        return bool(self.openai_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings parsed from the environment."""
    vectorstore = os.getenv("VECTORSTORE_PATH")
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        vectorstore_path=(
            Path(vectorstore) if vectorstore else PROJECT_ROOT / "data" / "vectorstore"
        ),
        allow_real_process_kill=_as_bool(os.getenv("ALLOW_REAL_PROCESS_KILL"), default=False),
    )
