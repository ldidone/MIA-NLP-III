"""Executor Agent: run only safe, approved, allowlisted tools.

Guarantees:
    * Only tools present in :data:`TOOL_REGISTRY` are ever invoked. Unknown tool
      names are skipped (never executed).
    * Sensitive steps are executed only when explicitly approved; otherwise they
      are skipped.
    * The executor never constructs or runs arbitrary commands; it only calls
      registered Python callables with the planned keyword arguments.
"""

from __future__ import annotations

from compufix_agents.logging_config import get_logger
from compufix_agents.schemas.execution import (
    ExecutionResult,
    StepExecutionResult,
    StepStatus,
)
from compufix_agents.schemas.plan import ActionPlan, PlanStep
from compufix_agents.tools.registry import (
    TOOL_REGISTRY,
    is_known_tool,
    is_sensitive_tool,
)

logger = get_logger(__name__)


def _execute_step(step: PlanStep) -> StepExecutionResult:
    """Execute a single plan step, enforcing allowlist + approval rules."""
    # 1. Allowlist check: never call an unknown tool.
    if not is_known_tool(step.tool):
        logger.warning("Executor refused unknown tool: %s", step.tool)
        return StepExecutionResult(
            step=step.step,
            tool=step.tool,
            status=StepStatus.SKIPPED_UNKNOWN_TOOL,
            message=f"Tool '{step.tool}' is not in the allowlist; skipped.",
        )

    # 2. Approval check: sensitive steps need explicit approval.
    if is_sensitive_tool(step.tool) and not step.approved:
        logger.info("Executor skipped unapproved sensitive step: %s", step.tool)
        return StepExecutionResult(
            step=step.step,
            tool=step.tool,
            status=StepStatus.SKIPPED_NOT_APPROVED,
            message=f"Step '{step.tool}' requires approval and was not approved.",
        )

    # 3. Execute the registered callable with the planned args.
    func = TOOL_REGISTRY[step.tool]
    try:
        output = func(**step.args)
        logger.info("Executed %s -> ok", step.tool)
        return StepExecutionResult(
            step=step.step,
            tool=step.tool,
            status=StepStatus.SUCCESS,
            output=output if isinstance(output, dict) else {"result": output},
            message=f"Executed '{step.tool}'.",
        )
    except Exception as exc:  # pragma: no cover - tool-level failures
        logger.exception("Tool %s raised an error", step.tool)
        return StepExecutionResult(
            step=step.step,
            tool=step.tool,
            status=StepStatus.FAILED,
            message=f"Tool '{step.tool}' failed: {exc}",
        )


def _summarize(results: list[StepExecutionResult]) -> str:
    """Build a short human-readable summary of the execution."""
    succeeded = [r for r in results if r.status == StepStatus.SUCCESS]
    skipped = [
        r
        for r in results
        if r.status
        in (StepStatus.SKIPPED_NOT_APPROVED, StepStatus.SKIPPED_UNKNOWN_TOOL)
    ]
    failed = [r for r in results if r.status == StepStatus.FAILED]
    parts = [
        f"{len(succeeded)} executed",
        f"{len(skipped)} skipped",
        f"{len(failed)} failed",
    ]
    return "Execution complete: " + ", ".join(parts) + "."


def execute_plan(plan: ActionPlan) -> ExecutionResult:
    """Execute an action plan, honoring the allowlist and approval flags.

    Args:
        plan: The (possibly approved) action plan.

    Returns:
        An :class:`ExecutionResult` with per-step outcomes and a summary.
    """
    results = [_execute_step(step) for step in plan.plan]
    final = _summarize(results)
    logger.info(final)
    return ExecutionResult(results=results, final_response=final)
