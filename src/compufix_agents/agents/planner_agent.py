"""Planner & Safety Agent: build a safe action plan from the diagnosis.

The planner is **deterministic** by design. It maps the triaged problem type to
a fixed sequence of controlled tools and enforces the safety policy so that the
plan can never include unsafe behavior:

    * Installing packages, switching networks, killing processes -> approval.
    * Read-only diagnostics -> no approval.
    * Only tools in the registry allowlist may appear in a plan.
    * If a tool's risk is unclear, approval is required (fail-safe).

There is intentionally no path for an LLM to introduce arbitrary tools.
"""

from __future__ import annotations

from typing import Any

from compufix_agents.logging_config import get_logger
from compufix_agents.schemas.plan import ActionPlan, PlanStep
from compufix_agents.schemas.triage import ProblemType, TriageResult
from compufix_agents.tools.network_tools import recommend_better_network
from compufix_agents.tools.python_env_tools import map_import_to_package
from compufix_agents.tools.registry import is_known_tool, is_sensitive_tool, risk_for

logger = get_logger(__name__)


def _make_step(step: int, tool: str, args: dict[str, Any], rationale: str) -> PlanStep:
    """Construct a PlanStep with safety attributes derived from the registry."""
    requires_approval = is_sensitive_tool(tool)
    return PlanStep(
        step=step,
        tool=tool,
        args=args,
        risk=risk_for(tool),
        requires_approval=requires_approval,
        rationale=rationale,
    )


def _plan_python_missing_library(triage: TriageResult) -> list[PlanStep]:
    """Plan: check -> install (approval) -> verify import."""
    entities = triage.extracted_entities
    module = entities.get("missing_module")
    package = entities.get("package_name") or (map_import_to_package(module) if module else None)
    if not package:
        return []

    steps = [
        _make_step(
            1,
            "check_python_package",
            {"package_name": package},
            "Check whether the package is already installed (read-only).",
        ),
        _make_step(
            2,
            "install_python_package",
            {"package_name": package},
            "Install the missing package (mutates environment; needs approval).",
        ),
    ]
    if module:
        steps.append(
            _make_step(
                3,
                "verify_python_import",
                {"module_name": module},
                "Verify the import works after installation (read-only).",
            )
        )
    return steps


def _plan_network_slow(triage: TriageResult) -> list[PlanStep]:
    """Plan: get current -> list available -> switch if better exists (approval)."""
    steps = [
        _make_step(
            1,
            "get_current_network",
            {},
            "Inspect the current network (read-only).",
        ),
        _make_step(
            2,
            "list_available_networks",
            {},
            "List available networks to compare speeds (read-only).",
        ),
    ]
    recommendation = recommend_better_network()
    better = recommendation.get("recommended")
    if better:
        steps.append(
            _make_step(
                3,
                "switch_network",
                {"ssid": better["ssid"]},
                f"Switch to a faster network: {recommendation.get('reason', '')}".strip(),
            )
        )
    return steps


def _plan_high_resource_usage(triage: TriageResult) -> list[PlanStep]:
    """Plan: list top processes -> optional kill (approval, dry-run by default)."""
    steps = [
        _make_step(
            1,
            "list_top_processes",
            {"limit": 5},
            "List the top CPU/RAM consuming processes (read-only).",
        )
    ]
    suspected_pid = triage.extracted_entities.get("suspected_pid")
    if suspected_pid is not None:
        steps.append(
            _make_step(
                2,
                "kill_process",
                {"pid": int(suspected_pid), "dry_run": True},
                "Optionally terminate the offending process (needs approval).",
            )
        )
    return steps


_PLANNERS = {
    ProblemType.PYTHON_MISSING_LIBRARY: _plan_python_missing_library,
    ProblemType.NETWORK_SLOW: _plan_network_slow,
    ProblemType.HIGH_RESOURCE_USAGE: _plan_high_resource_usage,
}


def _enforce_safety(plan: ActionPlan) -> ActionPlan:
    """Final safety pass: drop unknown tools, force approval on sensitive ones."""
    safe_steps: list[PlanStep] = []
    for step in plan.plan:
        if not is_known_tool(step.tool):
            logger.warning("Dropping unknown tool from plan: %s", step.tool)
            continue
        # Enforce approval flag from the registry regardless of how it was set.
        step.requires_approval = is_sensitive_tool(step.tool)
        step.risk = risk_for(step.tool)
        safe_steps.append(step)

    # Renumber to keep steps contiguous after any drops.
    for idx, step in enumerate(safe_steps, start=1):
        step.step = idx
    return ActionPlan(plan=safe_steps)


def plan_actions(triage: TriageResult, diagnosis: Any | None = None) -> ActionPlan:
    """Build a safe :class:`ActionPlan` for the triaged problem.

    Args:
        triage: The triage result (drives the plan template + entities).
        diagnosis: Optional diagnosis (not required by the deterministic planner;
            accepted for interface completeness / future use).

    Returns:
        A safety-enforced :class:`ActionPlan`.
    """
    builder = _PLANNERS.get(triage.problem_type)
    steps = builder(triage) if builder else []
    plan = _enforce_safety(ActionPlan(plan=steps))
    logger.info(
        "Planned %d step(s) for %s (approval needed: %s)",
        len(plan.plan),
        triage.problem_type.value,
        plan.requires_any_approval(),
    )
    return plan
