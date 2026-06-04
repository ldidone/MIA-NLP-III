"""Schema for the Planner & Safety Agent output."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    """Coarse risk classification for a planned step."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PlanStep(BaseModel):
    """A single step in an action plan.

    Each step maps to exactly one controlled tool. Sensitive steps must set
    ``requires_approval=True`` so the executor will skip them until a human
    approves.
    """

    step: int = Field(ge=1, description="1-based step ordering.")
    tool: str = Field(description="Name of the controlled tool to invoke.")
    args: dict[str, Any] = Field(default_factory=dict, description="Keyword args for the tool.")
    risk: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False
    approved: bool = Field(
        default=False,
        description="Set by the human-in-the-loop approval step before execution.",
    )
    rationale: str = Field(default="", description="Why this step is part of the plan.")


class ActionPlan(BaseModel):
    """An ordered, safe plan composed only of known controlled tools."""

    plan: list[PlanStep] = Field(default_factory=list)

    def requires_any_approval(self) -> bool:
        """Return True if any step in the plan needs approval."""
        return any(step.requires_approval for step in self.plan)
