"""Tests for the Executor Agent (allowlist + approval enforcement)."""

from __future__ import annotations

from compufix_agents.agents.executor_agent import execute_plan
from compufix_agents.schemas.execution import StepStatus
from compufix_agents.schemas.plan import ActionPlan, PlanStep, RiskLevel


def test_unknown_tool_is_skipped_not_executed():
    plan = ActionPlan(
        plan=[
            PlanStep(step=1, tool="rm_rf_everything", args={}, risk=RiskLevel.HIGH),
        ]
    )
    result = execute_plan(plan)
    assert result.results[0].status == StepStatus.SKIPPED_UNKNOWN_TOOL


def test_readonly_tool_executes_without_approval():
    plan = ActionPlan(
        plan=[
            PlanStep(step=1, tool="get_current_network", args={}, risk=RiskLevel.LOW),
        ]
    )
    result = execute_plan(plan)
    assert result.results[0].status == StepStatus.SUCCESS
    assert "current_network" in result.results[0].output


def test_sensitive_tool_skipped_without_approval():
    plan = ActionPlan(
        plan=[
            PlanStep(
                step=1,
                tool="switch_network",
                args={"ssid": "Home_5G"},
                risk=RiskLevel.MEDIUM,
                requires_approval=True,
                approved=False,
            ),
        ]
    )
    result = execute_plan(plan)
    assert result.results[0].status == StepStatus.SKIPPED_NOT_APPROVED


def test_sensitive_tool_runs_when_approved():
    from compufix_agents.tools.network_tools import _reset_mock_state

    _reset_mock_state()
    plan = ActionPlan(
        plan=[
            PlanStep(
                step=1,
                tool="switch_network",
                args={"ssid": "Home_5G"},
                risk=RiskLevel.MEDIUM,
                requires_approval=True,
                approved=True,
            ),
        ]
    )
    result = execute_plan(plan)
    assert result.results[0].status == StepStatus.SUCCESS
    assert result.results[0].output["success"] is True
    _reset_mock_state()


def test_kill_process_dry_run_executes_safely():
    plan = ActionPlan(
        plan=[
            PlanStep(
                step=1,
                tool="kill_process",
                args={"pid": 99_999_999, "dry_run": True},
                risk=RiskLevel.HIGH,
                requires_approval=True,
                approved=True,
            ),
        ]
    )
    result = execute_plan(plan)
    # Tool ran, but nothing was killed (nonexistent pid).
    assert result.results[0].status == StepStatus.SUCCESS
    assert result.results[0].output["killed"] is False


def test_summary_counts():
    plan = ActionPlan(
        plan=[
            PlanStep(step=1, tool="get_current_network", args={}),
            PlanStep(
                step=2,
                tool="switch_network",
                args={"ssid": "Home_5G"},
                requires_approval=True,
                approved=False,
            ),
            PlanStep(step=3, tool="bogus_tool", args={}),
        ]
    )
    result = execute_plan(plan)
    statuses = [r.status for r in result.results]
    assert StepStatus.SUCCESS in statuses
    assert StepStatus.SKIPPED_NOT_APPROVED in statuses
    assert StepStatus.SKIPPED_UNKNOWN_TOOL in statuses
    assert "executed" in result.final_response
