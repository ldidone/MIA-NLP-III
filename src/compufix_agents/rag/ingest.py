"""CLI to ingest the knowledge base into a vector store.

Usage:
    python -m compufix_agents.rag.ingest

When embeddings / an API key are available, this builds and persists a Chroma
vector store under ``VECTORSTORE_PATH``. Otherwise it reports that the system
will use the keyword-based fallback retriever (no action needed).
"""

from __future__ import annotations

import sys

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger
from compufix_agents.rag.vectorstore import (
    build_vectorstore,
    chunk_documents,
    load_knowledge_base_documents,
)

logger = get_logger(__name__)


def main() -> int:
    """Run the ingestion pipeline. Returns a process exit code."""
    settings = get_settings()
    docs = load_knowledge_base_documents()
    chunks = chunk_documents(docs)

    print(f"Knowledge base: {settings.knowledge_base_path}")
    print(f"  documents: {len(docs)}")
    print(f"  chunks:    {len(chunks)}")

    if not docs:
        print("No knowledge base documents found. Nothing to ingest.")
        return 1

    if not settings.llm_enabled:
        print(
            "\nNo OPENAI_API_KEY configured -> skipping vector store build.\n"
            "The system will use the deterministic keyword-based retriever.\n"
            "Set OPENAI_API_KEY (and install langchain-openai) to enable embeddings."
        )
        return 0

    store = build_vectorstore()
    if store is None:
        print(
            "\nEmbeddings backend unavailable -> keyword fallback will be used.\n"
            "Install 'langchain-openai' to enable the Chroma vector store."
        )
        return 0

    print(f"\nVector store built and persisted at: {settings.vectorstore_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
