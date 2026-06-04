"""Schema for the Executor Agent output."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    """Outcome of executing (or not executing) a single plan step."""

    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED_NOT_APPROVED = "skipped_not_approved"
    SKIPPED_UNKNOWN_TOOL = "skipped_unknown_tool"


class StepExecutionResult(BaseModel):
    """Result of executing a single plan step."""

    step: int
    tool: str
    status: StepStatus
    output: dict[str, Any] = Field(default_factory=dict)
    message: str = ""


class ExecutionResult(BaseModel):
    """Aggregated result of executing an action plan."""

    results: list[StepExecutionResult] = Field(default_factory=list)
    final_response: str = ""

    @property
    def all_succeeded(self) -> bool:
        """True if every executed (non-skipped) step succeeded."""
        executed = [
            r
            for r in self.results
            if r.status in (StepStatus.SUCCESS, StepStatus.FAILED)
        ]
        return bool(executed) and all(r.status == StepStatus.SUCCESS for r in executed)
