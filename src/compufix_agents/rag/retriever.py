"""Document retrieval with a vector-store path and a keyword fallback.

The public entry point is :func:`retrieve_relevant_docs`. It prefers a Chroma
vector store when embeddings / an API key are available, and otherwise falls
back to a dependency-free keyword scorer over the knowledge base chunks. This
guarantees the MVP works fully offline and deterministically.
"""

from __future__ import annotations

import re
from collections import Counter
from functools import lru_cache

from compufix_agents.logging_config import get_logger
from compufix_agents.rag.vectorstore import (
    chunk_documents,
    load_knowledge_base_documents,
    load_vectorstore,
)

logger = get_logger(__name__)

# Words ignored when scoring keyword overlap (English + Spanish stopwords).
_STOPWORDS: frozenset[str] = frozenset(
    """
    a an the and or of to in on for with is are be no not my mi me
    el la los las un una unos unas de del y o en con es esta este muy
    que se su sus por para al lo como more than i it this that error
    """.split()
)

_TOKEN_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase tokenization keeping identifier-like tokens of length >= 2."""
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 2]


@lru_cache(maxsize=1)
def _cached_chunks() -> tuple[dict[str, str], ...]:
    """Load and chunk the knowledge base once (cached)."""
    docs = load_knowledge_base_documents()
    chunks = chunk_documents(docs)
    return tuple(chunks)


def _keyword_retrieve(query: str, k: int) -> list[dict]:
    """Score knowledge-base chunks by keyword overlap with the query."""
    query_tokens = [t for t in _tokenize(query) if t not in _STOPWORDS]
    if not query_tokens:
        return []
    query_counts = Counter(query_tokens)

    scored: list[tuple[float, dict[str, str]]] = []
    for chunk in _cached_chunks():
        chunk_tokens = _tokenize(chunk["content"])
        if not chunk_tokens:
            continue
        chunk_set = set(chunk_tokens)
        # Score = number of (weighted) query tokens that appear in the chunk.
        score = sum(weight for tok, weight in query_counts.items() if tok in chunk_set)
        if score > 0:
            # Light normalization by chunk length to avoid favoring huge chunks.
            norm = score / (1 + len(chunk_set) / 200)
            scored.append((norm, chunk))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = [
        {"source": c["source"], "content": c["content"], "score": round(s, 4)}
        for s, c in scored[:k]
    ]
    logger.info("Keyword retrieval for %r -> %d hits", query, len(results))
    return results


def _vector_retrieve(query: str, k: int) -> list[dict] | None:
    """Retrieve via Chroma if available; return ``None`` to signal fallback."""
    store = load_vectorstore()
    if store is None:
        return None
    try:
        docs_and_scores = store.similarity_search_with_relevance_scores(query, k=k)
    except Exception as exc:  # pragma: no cover - backend/runtime issues
        logger.warning("Vector retrieval failed (%s); falling back to keywords.", exc)
        return None

    results = [
        {
            "source": doc.metadata.get("source", "unknown"),
            "content": doc.page_content,
            "score": round(float(score), 4),
        }
        for doc, score in docs_and_scores
    ]
    logger.info("Vector retrieval for %r -> %d hits", query, len(results))
    return results


def retrieve_relevant_docs(query: str, k: int = 4) -> list[dict]:
    """Return up to ``k`` relevant knowledge-base chunks for ``query``.

    Tries the vector store first and transparently falls back to keyword
    matching when embeddings / an API key / a persisted store are unavailable.

    Args:
        query: The search query (e.g. the user's problem description).
        k: Maximum number of chunks to return.

    Returns:
        A list of ``{"source", "content", "score"}`` dicts, best first.
    """
    vector_results = _vector_retrieve(query, k)
    if vector_results is not None:
        return vector_results
    return _keyword_retrieve(query, k)
