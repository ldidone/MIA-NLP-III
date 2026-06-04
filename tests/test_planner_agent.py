"""Tests for the Planner & Safety Agent."""

from __future__ import annotations

from compufix_agents.agents.planner_agent import plan_actions
from compufix_agents.schemas.plan import ActionPlan
from compufix_agents.schemas.triage import ProblemType, TriageResult


def _triage(problem_type, entities=None):
    return TriageResult(
        problem_type=problem_type,
        confidence=0.9,
        extracted_entities=entities or {},
    )


def test_python_plan_has_check_install_verify():
    triage = _triage(
        ProblemType.PYTHON_MISSING_LIBRARY,
        {"missing_module": "cv2", "package_name": "opencv-python"},
    )
    plan = plan_actions(triage)
    tools = [s.tool for s in plan.plan]
    assert tools == ["check_python_package", "install_python_package", "verify_python_import"]


def test_install_requires_approval_check_does_not():
    triage = _triage(
        ProblemType.PYTHON_MISSING_LIBRARY,
        {"missing_module": "cv2", "package_name": "opencv-python"},
    )
    plan = plan_actions(triage)
    by_tool = {s.tool: s for s in plan.plan}
    assert by_tool["check_python_package"].requires_approval is False
    assert by_tool["install_python_package"].requires_approval is True
    assert by_tool["verify_python_import"].requires_approval is False
    assert plan.requires_any_approval() is True


def test_network_plan_includes_switch_with_approval():
    triage = _triage(ProblemType.NETWORK_SLOW)
    plan = plan_actions(triage)
    tools = [s.tool for s in plan.plan]
    assert "get_current_network" in tools
    assert "list_available_networks" in tools
    assert "switch_network" in tools
    switch = next(s for s in plan.plan if s.tool == "switch_network")
    assert switch.requires_approval is True
    # Read-only steps do not require approval.
    assert all(
        not s.requires_approval
        for s in plan.plan
        if s.tool in ("get_current_network", "list_available_networks")
    )


def test_high_resource_plan_lists_processes_no_approval():
    triage = _triage(ProblemType.HIGH_RESOURCE_USAGE)
    plan = plan_actions(triage)
    tools = [s.tool for s in plan.plan]
    assert "list_top_processes" in tools
    listing = next(s for s in plan.plan if s.tool == "list_top_processes")
    assert listing.requires_approval is False


def test_high_resource_kill_requires_approval_when_pid_present():
    triage = _triage(ProblemType.HIGH_RESOURCE_USAGE, {"suspected_pid": 4242})
    plan = plan_actions(triage)
    kill = next((s for s in plan.plan if s.tool == "kill_process"), None)
    assert kill is not None
    assert kill.requires_approval is True
    assert kill.args.get("dry_run") is True


def test_unknown_problem_yields_empty_plan():
    triage = _triage(ProblemType.UNKNOWN)
    plan = plan_actions(triage)
    assert plan.plan == []


def test_only_known_tools_appear_in_plan():
    triage = _triage(
        ProblemType.PYTHON_MISSING_LIBRARY,
        {"missing_module": "cv2", "package_name": "opencv-python"},
    )
    plan = plan_actions(triage)
    from compufix_agents.tools.registry import is_known_tool

    assert all(is_known_tool(s.tool) for s in plan.plan)
    assert isinstance(plan, ActionPlan)


def test_steps_are_contiguously_numbered():
    triage = _triage(
        ProblemType.PYTHON_MISSING_LIBRARY,
        {"missing_module": "cv2", "package_name": "opencv-python"},
    )
    plan = plan_actions(triage)
    assert [s.step for s in plan.plan] == list(range(1, len(plan.plan) + 1))
