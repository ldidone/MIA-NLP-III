"""LangGraph workflow wiring the four agents together.

Flow::

    user input
      -> triage agent
      -> diagnostic agent
      -> planner agent
      -> (human approval, handled outside the graph in the MVP)
      -> executor agent
      -> final response

The compiled LangGraph graph (:func:`build_workflow`) interrupts *before* the
executor so a human can approve sensitive steps. For the Streamlit MVP we also
expose simple, deterministic orchestration helpers (:func:`run_analysis`,
:func:`apply_approvals`, :func:`run_execution`) that reuse the same agent
functions without requiring callers to manage LangGraph checkpoints.
"""

from __future__ import annotations

from typing import TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from compufix_agents.agents.diagnostic_agent import diagnose
from compufix_agents.agents.executor_agent import execute_plan
from compufix_agents.agents.planner_agent import plan_actions
from compufix_agents.agents.triage_agent import triage
from compufix_agents.graph.state import AgentState
from compufix_agents.logging_config import get_logger
from compufix_agents.schemas.diagnosis import DiagnosisResult
from compufix_agents.schemas.execution import ExecutionResult
from compufix_agents.schemas.plan import ActionPlan
from compufix_agents.schemas.triage import ProblemType, TriageResult

logger = get_logger(__name__)


class WorkflowState(TypedDict, total=False):
    """Dict-shaped state used by the LangGraph graph."""

    user_input: str
    triage: TriageResult | None
    diagnosis: DiagnosisResult | None
    plan: ActionPlan | None
    execution: ExecutionResult | None
    final_response: str


# --- Graph nodes (thin wrappers around the agent layer) ---------------------


def triage_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: classify the problem."""
    result = triage(state["user_input"])
    return {"triage": result}


def diagnostic_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: produce a grounded diagnosis."""
    result = diagnose(state["user_input"], state["triage"])
    return {"diagnosis": result}


def planner_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: build a safe action plan."""
    result = plan_actions(state["triage"], state.get("diagnosis"))
    return {"plan": result}


def _get_python_error_final_response(
    triage: TriageResult | None, diagnosis: DiagnosisResult | None
) -> str | None:
    if triage and triage.problem_type == ProblemType.PYTHON_ERROR and diagnosis:
        return (
            f"No system actions required. Diagnosis:\n"
            f"{diagnosis.diagnosis}\n\n"
            f"Recommended Fix:\n"
            f"{diagnosis.recommended_next_step}"
        )
    return None


def executor_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: execute approved / safe steps."""
    result = execute_plan(state["plan"])
    final_response = (
        _get_python_error_final_response(state.get("triage"), state.get("diagnosis"))
        or result.final_response
    )
    return {"execution": result, "final_response": final_response}


def build_workflow(with_interrupt: bool = True):
    """Build and compile the LangGraph workflow.

    Args:
        with_interrupt: If True, the graph interrupts before the executor so a
            human can approve sensitive steps (requires a checkpointer +
            thread config when invoked).

    Returns:
        A compiled LangGraph graph.
    """
    graph = StateGraph(WorkflowState)
    graph.add_node("triage_agent", triage_node)
    graph.add_node("diagnostic_agent", diagnostic_node)
    graph.add_node("planner_agent", planner_node)
    graph.add_node("executor_agent", executor_node)

    graph.add_edge(START, "triage_agent")
    graph.add_edge("triage_agent", "diagnostic_agent")
    graph.add_edge("diagnostic_agent", "planner_agent")
    graph.add_edge("planner_agent", "executor_agent")
    graph.add_edge("executor_agent", END)

    checkpointer = MemorySaver()
    if with_interrupt:
        return graph.compile(checkpointer=checkpointer, interrupt_before=["executor_agent"])
    return graph.compile(checkpointer=checkpointer)


# --- Deterministic orchestration helpers (used by the Streamlit UI) ---------


def run_analysis(user_input: str) -> AgentState:
    """Run triage -> diagnostic -> planner and return the partial state.

    Stops *before* execution so sensitive steps can be approved by a human.

    Args:
        user_input: The raw problem description.

    Returns:
        An :class:`AgentState` populated with triage, diagnosis, and plan.
    """
    state = AgentState(user_input=user_input)
    try:
        state.triage = triage(user_input)
        state.diagnosis = diagnose(user_input, state.triage)
        state.plan = plan_actions(state.triage, state.diagnosis)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Analysis failed")
        state.errors.append(str(exc))
    return state


def apply_approvals(plan: ActionPlan, approvals: dict[int, bool]) -> ActionPlan:
    """Apply per-step human approval decisions to a plan.

    Args:
        plan: The action plan to update.
        approvals: Mapping of ``step number -> approved (bool)``.

    Returns:
        The same plan with ``approved`` flags set on each step.
    """
    for step in plan.plan:
        if step.requires_approval:
            step.approved = bool(approvals.get(step.step, False))
    return plan


def run_execution(state: AgentState) -> AgentState:
    """Execute the (approved) plan stored in ``state`` and record results.

    Args:
        state: An :class:`AgentState` containing an approved plan.

    Returns:
        The updated state with execution results and a final response.
    """
    if state.plan is None:
        state.errors.append("No plan to execute.")
        return state
    try:
        state.execution = execute_plan(state.plan)
        py_final = _get_python_error_final_response(state.triage, state.diagnosis)
        state.final_response = py_final if py_final is not None else state.execution.final_response
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Execution failed")
        state.errors.append(str(exc))
    return state


def run_full(user_input: str, auto_approve: bool = False) -> AgentState:
    """Run the entire pipeline end to end (convenience for tests/CLI/eval).

    Args:
        user_input: The raw problem description.
        auto_approve: If True, approve all sensitive steps automatically. Use
            with care; intended for tests and non-destructive demos (network is
            mocked and process kills default to dry-run).

    Returns:
        The fully populated :class:`AgentState`.
    """
    state = run_analysis(user_input)
    if state.plan is not None:
        if auto_approve:
            approvals = {s.step: True for s in state.plan.plan if s.requires_approval}
            apply_approvals(state.plan, approvals)
        state = run_execution(state)
    return state
