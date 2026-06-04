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


def _get_embeddings() -> Any | None:
    """Return an embeddings object if possible, else ``None``.

    Requires both ``langchain_openai`` to be installed and an API key to be
    configured. Returns ``None`` otherwise so callers can fall back.
    """
    settings = get_settings()
    if not settings.llm_enabled:
        logger.info("No API key configured; embeddings unavailable.")
        return None
    try:
        from langchain_openai import OpenAIEmbeddings
    except ImportError:
        logger.info("langchain_openai not installed; embeddings unavailable.")
        return None
    return OpenAIEmbeddings(api_key=settings.openai_api_key)


def build_vectorstore(kb_path: Path | None = None) -> Any | None:
    """Build and persist a Chroma vector store from the knowledge base.

    Returns the Chroma store on success, or ``None`` if embeddings / Chroma are
    unavailable (in which case the keyword fallback retriever should be used).
    """
    embeddings = _get_embeddings()
    if embeddings is None:
        return None

    try:
        from langchain_chroma import Chroma
        from langchain_core.documents import Document
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma
            from langchain_core.documents import Document
        except ImportError:
            logger.warning("Chroma vector store backend unavailable.")
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
    store = Chroma.from_documents(
        documents=documents,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name="compufix_kb",
    )
    return store


def load_vectorstore() -> Any | None:
    """Load a previously persisted Chroma store, or ``None`` if unavailable."""
    embeddings = _get_embeddings()
    if embeddings is None:
        return None

    settings = get_settings()
    persist_dir = Path(settings.vectorstore_path)
    if not persist_dir.exists() or not any(persist_dir.iterdir()):
        logger.info("No persisted vector store found at %s", persist_dir)
        return None

    try:
        from langchain_chroma import Chroma
    except ImportError:
        try:
            from langchain_community.vectorstores import Chroma
        except ImportError:
            return None

    return Chroma(
        persist_directory=str(persist_dir),
        embedding_function=embeddings,
        collection_name="compufix_kb",
    )
