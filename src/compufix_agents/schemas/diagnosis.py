"""Schema for the RAG Diagnostic Agent output."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RetrievedDoc(BaseModel):
    """A single chunk retrieved from the knowledge base."""

    source: str = Field(description="Relative path / identifier of the source document.")
    content: str = Field(description="The retrieved text chunk.")
    score: float | None = Field(
        default=None, description="Optional similarity/relevance score (higher is better)."
    )


class DiagnosisResult(BaseModel):
    """Diagnosis grounded in retrieved documentation.

    The diagnostic agent must not invent procedures that are not supported by
    the retrieved context.
    """

    diagnosis: str = Field(description="Human-readable diagnosis of the problem.")
    evidence: list[str] = Field(
        default_factory=list,
        description="Snippets / sources supporting the diagnosis.",
    )
    recommended_next_step: str = Field(
        default="", description="The single most useful next action to take."
    )
    retrieved_docs: list[RetrievedDoc] = Field(
        default_factory=list, description="Raw documents used to build the diagnosis."
    )
