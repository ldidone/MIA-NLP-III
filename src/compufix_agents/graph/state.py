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


class ConversationTurn(BaseModel):
    """A single exchange in a multi-turn conversation."""

    role: str = Field(description="'user' or 'assistant'")
    content: str = Field(description="The message text.")


class AgentState(BaseModel):
    """End-to-end state for a single (possibly multi-turn) user request.

    Fields are populated progressively as the request flows through the
    triage -> diagnostic -> planner -> (approval) -> executor pipeline.
    """

    user_input: str = Field(description="The raw problem description from the user.")

    conversation_history: list[ConversationTurn] = Field(
        default_factory=list,
        description="Accumulated conversation turns for multi-turn support.",
    )

    triage: TriageResult | None = None
    diagnosis: DiagnosisResult | None = None
    plan: ActionPlan | None = None
    execution: ExecutionResult | None = None

    needs_clarification: bool = False
    clarification_question: str = ""
    clarification_count: int = Field(
        default=0, description="How many clarification rounds have been used."
    )

    retry_count: int = Field(
        default=0,
        description="How many re-diagnosis + re-execution retries have been attempted.",
    )
    max_retries: int = Field(
        default=2,
        description="Maximum number of re-diagnosis attempts after execution failure.",
    )

    execution_error: str = Field(
        default="",
        description="Error context from a failed execution, fed back to the diagnostic agent.",
    )

    final_response: str = ""
    errors: list[str] = Field(default_factory=list)

    solution_saved: bool = Field(
        default=False,
        description="Whether a successful solution was auto-saved to the knowledge base.",
    )

    def add_user_turn(self, message: str) -> None:
        self.conversation_history.append(ConversationTurn(role="user", content=message))

    def add_assistant_turn(self, message: str) -> None:
        self.conversation_history.append(ConversationTurn(role="assistant", content=message))

    def build_conversation_context(self) -> str:
        """Build a condensed context string from conversation history."""
        if not self.conversation_history:
            return ""
        lines = []
        for turn in self.conversation_history:
            prefix = "User" if turn.role == "user" else "Assistant"
            lines.append(f"{prefix}: {turn.content}")
        return "\n".join(lines)
