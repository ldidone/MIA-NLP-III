"""Tests for the orchestration helpers and LangGraph workflow."""

from __future__ import annotations

from compufix_agents.graph.workflow import (
    apply_approvals,
    build_workflow,
    run_analysis,
    run_execution,
    run_full,
)
from compufix_agents.schemas.execution import StepStatus
from compufix_agents.schemas.triage import ProblemType
from compufix_agents.tools.network_tools import _reset_mock_state


def test_run_analysis_populates_triage_diagnosis_plan():
    state = run_analysis("ModuleNotFoundError: No module named 'cv2'")
    assert state.triage is not None
    assert state.triage.problem_type == ProblemType.PYTHON_MISSING_LIBRARY
    assert state.diagnosis is not None
    assert state.plan is not None
    # Analysis must NOT execute anything yet.
    assert state.execution is None


def test_sensitive_step_skipped_without_approval():
    state = run_analysis("ModuleNotFoundError: No module named 'cv2'")
    state = run_execution(state)  # no approvals applied
    by_tool = {r.tool: r for r in state.execution.results}
    assert by_tool["install_python_package"].status == StepStatus.SKIPPED_NOT_APPROVED
    # Read-only steps still run.
    assert by_tool["check_python_package"].status == StepStatus.SUCCESS


def test_apply_approvals_enables_sensitive_step():
    _reset_mock_state()
    state = run_analysis("Mi internet está muy lento")
    approvals = {s.step: True for s in state.plan.plan if s.requires_approval}
    apply_approvals(state.plan, approvals)
    state = run_execution(state)
    by_tool = {r.tool: r for r in state.execution.results}
    assert by_tool["switch_network"].status == StepStatus.SUCCESS
    _reset_mock_state()


def test_run_full_network_auto_approve_is_mocked():
    _reset_mock_state()
    state = run_full("Mi internet está muy lento", auto_approve=True)
    assert state.execution is not None
    assert state.final_response
    by_tool = {r.tool: r for r in state.execution.results}
    assert by_tool["switch_network"].output["success"] is True
    _reset_mock_state()


def test_run_full_resource_usage_no_approval_needed():
    state = run_full("La computadora está lenta y consume mucha RAM")
    assert state.triage.problem_type == ProblemType.HIGH_RESOURCE_USAGE
    by_tool = {r.tool: r for r in state.execution.results}
    assert by_tool["list_top_processes"].status == StepStatus.SUCCESS


def test_build_workflow_compiles():
    graph = build_workflow(with_interrupt=True)
    assert graph is not None
    # Graph exposes the expected nodes.
    node_names = set(graph.get_graph().nodes.keys())
    assert {
        "triage_agent",
        "diagnostic_agent",
        "planner_agent",
        "executor_agent",
    } <= node_names
