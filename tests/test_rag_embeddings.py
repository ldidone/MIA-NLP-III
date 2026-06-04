"""Tests for embedding backend selection and retrieval fallback."""

from __future__ import annotations

import pytest

from compufix_agents import config
from compufix_agents.config import VALID_EMBEDDING_BACKENDS, get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """Ensure each test re-reads settings from the (patched) environment."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_default_backend_is_auto(monkeypatch):
    monkeypatch.delenv("EMBEDDING_BACKEND", raising=False)
    assert get_settings().embedding_backend == "auto"


def test_invalid_backend_falls_back_to_auto(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "banana")
    assert get_settings().embedding_backend == "auto"


@pytest.mark.parametrize("backend", sorted(VALID_EMBEDDING_BACKENDS))
def test_valid_backends_parsed(monkeypatch, backend):
    monkeypatch.setenv("EMBEDDING_BACKEND", backend.upper())  # case-insensitive
    assert get_settings().embedding_backend == backend


def test_backend_none_disables_embeddings(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "none")
    get_settings.cache_clear()
    from compufix_agents.rag import vectorstore

    assert vectorstore._get_embeddings() is None
    assert vectorstore.load_vectorstore() is None


def test_local_embedding_model_configurable(monkeypatch):
    monkeypatch.setenv("LOCAL_EMBEDDING_MODEL", "some/custom-model")
    assert get_settings().local_embedding_model == "some/custom-model"


def test_retriever_falls_back_to_keyword(monkeypatch):
    # With embeddings disabled, retrieval must still work via keywords.
    monkeypatch.setenv("EMBEDDING_BACKEND", "none")
    get_settings.cache_clear()
    from compufix_agents.rag.retriever import retrieve_relevant_docs

    hits = retrieve_relevant_docs("No module named 'cv2'", k=2)
    assert hits
    assert any("python/" in h["source"] for h in hits)


def test_openai_embeddings_none_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("EMBEDDING_BACKEND", "openai")
    get_settings.cache_clear()
    from compufix_agents.rag import vectorstore

    assert vectorstore._openai_embeddings() is None
    # And via the dispatcher.
    assert config.get_settings().embedding_backend == "openai"
    assert vectorstore._get_embeddings() is None
