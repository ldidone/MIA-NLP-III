"""Knowledge-base loading, chunking, and (optional) Chroma vector store.

This module is intentionally split so the *loading + chunking* logic has no
heavy dependencies and can be reused by the keyword-based fallback retriever.
The Chroma / embeddings code uses **lazy imports** so the package still works
when those optional dependencies (or an API key) are unavailable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger

logger = get_logger(__name__)

# Approximate target size (characters) per chunk and overlap between chunks.
_CHUNK_SIZE = 800
_CHUNK_OVERLAP = 120


def load_knowledge_base_documents(kb_path: Path | None = None) -> list[dict[str, str]]:
    """Load all Markdown files from the knowledge base.

    Args:
        kb_path: Optional override for the knowledge base directory.

    Returns:
        A list of ``{"source": <relative path>, "content": <text>}`` dicts.
    """
    settings = get_settings()
    base = kb_path or settings.knowledge_base_path
    base = Path(base)

    if not base.exists():
        logger.warning("Knowledge base path does not exist: %s", base)
        return []

    docs: list[dict[str, str]] = []
    for md_file in sorted(base.rglob("*.md")):
        try:
            text = md_file.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - unlikely IO error
            logger.warning("Could not read %s: %s", md_file, exc)
            continue
        try:
            source = str(md_file.relative_to(base.parent))
        except ValueError:
            source = str(md_file)
        docs.append({"source": source, "content": text})

    logger.info("Loaded %d knowledge base documents from %s", len(docs), base)
    return docs


def chunk_documents(
    documents: list[dict[str, str]],
    chunk_size: int = _CHUNK_SIZE,
    overlap: int = _CHUNK_OVERLAP,
) -> list[dict[str, str]]:
    """Split documents into overlapping, paragraph-aware chunks.

    The splitter accumulates paragraphs until ``chunk_size`` is reached, then
    starts a new chunk carrying a small character overlap for context.

    Args:
        documents: Output of :func:`load_knowledge_base_documents`.
        chunk_size: Approximate maximum characters per chunk.
        overlap: Characters of overlap carried into the next chunk.

    Returns:
        A list of ``{"source", "content"}`` chunk dicts.
    """
    chunks: list[dict[str, str]] = []
    for doc in documents:
        paragraphs = [p.strip() for p in doc["content"].split("\n\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > chunk_size:
                chunks.append({"source": doc["source"], "content": current.strip()})
                current = (current[-overlap:] + "\n\n" + para) if overlap else para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current.strip():
            chunks.append({"source": doc["source"], "content": current.strip()})

    logger.info("Split %d documents into %d chunks", len(documents), len(chunks))
    return chunks


def _openai_embeddings() -> Any | None:
    """Return OpenAI embeddings if a key + ``langchain_openai`` are available."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        logger.info("langchain_openai not installed; OpenAI embeddings unavailable.")
        return None
    return OpenAIEmbeddings(api_key=settings.openai_api_key)


def _local_embeddings() -> Any | None:
    """Return local (offline) sentence-transformers embeddings if installed.

    Requires the ``sentence-transformers`` runtime plus a LangChain wrapper.
    Prefers the maintained ``langchain_huggingface`` package and falls back to
    the deprecated ``langchain_community`` location. Returns ``None`` (so the
    caller uses the keyword fallback) when the local stack is not installed.
    """
    import importlib.util

    # Short-circuit cleanly when the heavy runtime is absent. This avoids a
    # failed construction attempt (and its deprecation warning) on the default
    # install where the ``[local]`` extra is not present.
    if importlib.util.find_spec("sentence_transformers") is None:
        logger.info("Local embeddings unavailable; install extras: pip install -e '.[local]'")
        return None

    embeddings_cls = None
    try:
        from langchain_huggingface import HuggingFaceEmbeddings as embeddings_cls
    except ImportError:
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings as embeddings_cls
        except ImportError:
            embeddings_cls = None
    if embeddings_cls is None:
        logger.info("No HuggingFace embeddings wrapper installed; using keyword fallback.")
        return None

    model_name = get_settings().local_embedding_model
    try:
        logger.info("Loading local embedding model: %s", model_name)
        return embeddings_cls(model_name=model_name)
    except Exception as exc:  # pragma: no cover - model load/download failure
        logger.warning("Failed to load local embedding model %s: %s", model_name, exc)
        return None


def _get_embeddings() -> Any | None:
    """Return an embeddings object based on the configured backend, else ``None``.

    Backend selection (``EMBEDDING_BACKEND``):
        * ``none``   -> always ``None`` (keyword fallback).
        * ``openai`` -> OpenAI embeddings only.
        * ``local``  -> local sentence-transformers embeddings only.
        * ``auto``   -> OpenAI if available, otherwise local, otherwise ``None``.
    """
    backend = get_settings().embedding_backend

    if backend == "none":
        logger.info("EMBEDDING_BACKEND=none; using keyword fallback.")
        return None
    if backend == "openai":
        return _openai_embeddings()
    if backend == "local":
        return _local_embeddings()

    # auto: prefer OpenAI (if key), then local, then None.
    return _openai_embeddings() or _local_embeddings()


def _import_chroma() -> Any | None:
    """Import the Chroma class from whichever package is available."""
    try:
        from langchain_chroma import Chroma

        return Chroma
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma

            return Chroma
        except ImportError:
            logger.warning("Chroma vector store backend unavailable.")
            return None


def build_vectorstore(kb_path: Path | None = None) -> Any | None:
    """Build and persist a Chroma vector store from the knowledge base.

    Returns the Chroma store on success, or ``None`` if embeddings / Chroma are
    unavailable (in which case the keyword fallback retriever should be used).
    """
    embeddings = _get_embeddings()
    if embeddings is None:
        return None

    Chroma = _import_chroma()
    if Chroma is None:
        return None
    try:
        from langchain_core.documents import Document
    except ImportError:
        logger.warning("langchain_core not available; cannot build vector store.")
        return None

    settings = get_settings()
    raw_docs = load_knowledge_base_documents(kb_path)
    chunks = chunk_documents(raw_docs)
    if not chunks:
        logger.warning("No documents to index.")
        return None

    documents = [
        Document(page_content=c["content"], metadata={"source": c["source"]}) for c in chunks
    ]
    persist_dir = str(settings.vectorstore_path)
    logger.info("Building Chroma vector store at %s (%d chunks)", persist_dir, len(documents))
    try:
        store = _chroma_from_documents(Chroma, documents, embeddings, persist_dir)
    except Exception as exc:  # pragma: no cover - backend/runtime issues
        logger.warning("Failed to build vector store (%s); keyword fallback will be used.", exc)
        return None
    return store


def _chroma_from_documents(Chroma, documents, embeddings, persist_dir):  # noqa: ANN001
    """Thin wrapper around ``Chroma.from_documents`` for easier error handling."""
    return Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name="compufix_kb",
    )


def load_vectorstore() -> Any | None:
    """Load a previously persisted Chroma store, or ``None`` if unavailable."""
    embeddings = _get_embeddings()
    if embeddings is None:
        return None

    settings = get_settings()
    persist_dir = Path(settings.vectorstore_path)
    # Chroma persists a 'chroma.sqlite3' file; a bare directory (or one holding
    # only a .gitkeep) does not count as a built store.
    if not (persist_dir / "chroma.sqlite3").exists():
        logger.info("No persisted vector store found at %s", persist_dir)
        return None

    Chroma = _import_chroma()
    if Chroma is None:
        return None

    return Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name="compufix_kb",
    )
