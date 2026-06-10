"""Schema for the Triage Agent output."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ProblemType(StrEnum):
    """Categories the triage agent can classify a problem into."""

    PYTHON_MISSING_LIBRARY = "python_missing_library"
    PYTHON_ERROR = "python_error"
    NETWORK_SLOW = "network_slow"
    HIGH_RESOURCE_USAGE = "high_resource_usage"
    UNKNOWN = "unknown"


class TriageResult(BaseModel):
    """Structured classification of a user-reported problem.

    Attributes:
        problem_type: The detected category of the problem.
        confidence: Confidence score in the range [0, 1].
        extracted_entities: Free-form entities extracted from the input, e.g.
            ``{"missing_module": "cv2", "package_name": "opencv-python"}``.
        requires_retrieval: Whether the diagnostic (RAG) agent should run.
        requires_system_tools: Whether system tools are likely needed.
    """

    problem_type: ProblemType = ProblemType.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    extracted_entities: dict[str, Any] = Field(default_factory=dict)
    requires_retrieval: bool = True
    requires_system_tools: bool = True
