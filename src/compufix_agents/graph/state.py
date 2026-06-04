"""Shared state passed between agents in the workflow.

This module defines the full agent state as a Pydantic model. The LangGraph
workflow uses a ``TypedDict`` view of the same fields (see ``workflow.py``),
but the Pydantic model is the source of truth and is convenient for the
Streamlit UI and tests.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from compufix_agents.schemas.diagnosis import DiagnosisResult
from compufix_agents.schemas.execution import ExecutionResult
from compufix_agents.schemas.plan import ActionPlan
from compufix_agents.schemas.triage import TriageResult


class AgentState(BaseModel):
    """End-to-end state for a single user request.

    Fields are populated progressively as the request flows through the
    triage -> diagnostic -> planner -> (approval) -> executor pipeline.
    """

    user_input: str = Field(description="The raw problem description from the user.")

    triage: TriageResult | None = None
    diagnosis: DiagnosisResult | None = None
    plan: ActionPlan | None = None
    execution: ExecutionResult | None = None

    final_response: str = ""
    errors: list[str] = Field(default_factory=list)
