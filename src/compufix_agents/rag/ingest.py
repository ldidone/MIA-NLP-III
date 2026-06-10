"""CLI to ingest the knowledge base into a vector store, plus auto-expansion.

Usage:
    python -m compufix_agents.rag.ingest

When embeddings / an API key are available, this builds and persists a Chroma
vector store under ``VECTORSTORE_PATH``. Otherwise it reports that the system
will use the keyword-based fallback retriever (no action needed).
"""

from __future__ import annotations

import re
import sys
from datetime import datetime

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger
from compufix_agents.rag.vectorstore import (
    build_vectorstore,
    chunk_documents,
    load_knowledge_base_documents,
)

logger = get_logger(__name__)


def save_solution_to_knowledge_base(
    problem: str,
    solution: str,
    problem_type: str = "unknown",
) -> str | None:
    """Save a successful problem+solution to the knowledge base for future retrieval.

    Args:
        problem: The original problem description.
        solution: What solved the problem (execution summary).
        problem_type: The triaged problem category.

    Returns:
        The path of the saved file, or ``None`` if it could not be written.
    """
    settings = get_settings()
    kb_dir = settings.knowledge_base_path
    if not kb_dir.exists():
        kb_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w]+", "_", problem[:40]).strip("_") or "solution"
    filename = f"auto_{problem_type}_{timestamp}_{safe_name}.md"
    filepath = kb_dir / filename

    content = (
        f"# {problem_type.replace('_', ' ').title()}: {problem.strip()[:80]}\n\n"
        f"- **Auto-guardado**: {datetime.now().isoformat()}\n"
        f"- **Tipo**: {problem_type}\n"
        f"- **Problema original**: {problem}\n\n"
        f"## Solución\n\n{solution}\n"
    )

    try:
        filepath.write_text(content, encoding="utf-8")
        logger.info("Saved solution to knowledge base: %s", filepath)
        return str(filepath)
    except OSError as exc:
        logger.warning("Could not save solution to KB: %s", exc)
        return None


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

    print(f"  embedding backend: {settings.embedding_backend}")

    if settings.embedding_backend == "none":
        print(
            "\nEMBEDDING_BACKEND=none -> using the deterministic keyword retriever.\n"
            "Set EMBEDDING_BACKEND=local (offline) or =openai to enable embeddings."
        )
        return 0

    store = build_vectorstore()
    if store is None:
        print(
            "\nNo embeddings backend available -> keyword fallback will be used.\n"
            "Options to enable semantic retrieval:\n"
            '  * local : pip install -e ".[local]"  (offline sentence-transformers)\n'
            "  * openai: set OPENAI_API_KEY and pip install langchain-openai"
        )
        return 0

    print(f"\nVector store built and persisted at: {settings.vectorstore_path}")
    print("Semantic retrieval is now active.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
