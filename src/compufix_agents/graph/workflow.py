"""LangGraph workflow wiring the four agents together.

Flow::

    user input
      -> triage agent
      -> [if low confidence] -> ask clarification -> (user responds) -> re-triage
      -> diagnostic agent
      -> planner agent
      -> (human approval, handled outside the graph in the MVP)
      -> executor agent
      -> [if any step failed and retries remain] -> re-diagnosis
      -> [if all succeeded and novel solution] -> auto-save to KB
      -> final response

The compiled LangGraph graph (:func:`build_workflow`) interrupts *before* the
executor so a human can approve sensitive steps. For the Streamlit MVP we also
expose simple, deterministic orchestration helpers that reuse the same agent
functions without requiring callers to manage LangGraph checkpoints.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from compufix_agents.agents.diagnostic_agent import diagnose
from compufix_agents.agents.executor_agent import execute_plan
from compufix_agents.agents.planner_agent import plan_actions
from compufix_agents.agents.triage_agent import triage
from compufix_agents.graph.state import AgentState
from compufix_agents.logging_config import get_logger
from compufix_agents.rag.ingest import save_solution_to_knowledge_base
from compufix_agents.rag.vectorstore import build_vectorstore
from compufix_agents.schemas.diagnosis import DiagnosisResult
from compufix_agents.schemas.execution import ExecutionResult, StepStatus
from compufix_agents.schemas.plan import ActionPlan
from compufix_agents.schemas.triage import ProblemType, TriageResult

logger = get_logger(__name__)

MAX_RETRIES = 2
CLARIFICATION_MAX = 2


class WorkflowState(TypedDict, total=False):
    """Dict-shaped state used by the LangGraph graph."""

    user_input: str
    conversation_history: list[dict]
    triage: TriageResult | None
    diagnosis: DiagnosisResult | None
    plan: ActionPlan | None
    execution: ExecutionResult | None
    needs_clarification: bool
    clarification_question: str
    clarification_count: int
    retry_count: int
    execution_error: str
    final_response: str
    errors: list[str]
    solution_saved: bool


# --- Routing helpers --------------------------------------------------------


def _should_clarify(state: WorkflowState) -> Literal["clarify", "diagnose"]:
    """Route to clarification node if triage confidence is low."""
    triage_result = state.get("triage")
    if (
        triage_result
        and triage_result.needs_clarification
        and state.get("clarification_count", 0) < CLARIFICATION_MAX
    ):
        return "clarify"
    return "diagnose"


def _after_execution(state: WorkflowState) -> Literal["rediagnose", "save", "done"]:
    """Route after execution: re-diagnose on failure, or save on success."""
    execution = state.get("execution")
    if execution is None:
        return "done"

    retry_count = state.get("retry_count", 0)
    has_failure = any(r.status == StepStatus.FAILED for r in execution.results)

    if has_failure and retry_count < MAX_RETRIES:
        return "rediagnose"

    has_success = any(r.status == StepStatus.SUCCESS for r in execution.results)
    if has_success and not state.get("solution_saved", False):
        return "save"

    return "done"


# --- Graph nodes ------------------------------------------------------------


def triage_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: classify the problem."""
    user_input = state["user_input"]
    context = _build_context_str(state.get("conversation_history", []))
    result = triage(user_input, conversation_context=context)
    update: WorkflowState = {"triage": result}
    if result.needs_clarification:
        update["needs_clarification"] = True
        update["clarification_question"] = result.clarification_question
    return update


def clarify_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: placeholder for clarification (handled by human)."""
    return {}


def diagnostic_node(state: WorkflowState) -> WorkflowState:
    """LangGraph node: produce a grounded diagnosis."""
    user_input = state["user_input"]
    triage_result = state["triage"]
    error = state.get("execution_error", "")
    result = diagnose(user_input, triage_result, execution_error=error)
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


def rediagnose_setup_node(state: WorkflowState) -> WorkflowState:
    """Prepare state for a re-diagnosis round after execution failure."""
    execution = state.get("execution")
    failed = [r for r in execution.results if r.status == StepStatus.FAILED]
    parts = []
    for r in failed:
        detail = f"Step {r.step} ({r.tool}): {r.message}"
        if r.output and "error" in r.output:
            detail += f" | {r.output['error']}"
        parts.append(detail)
    error_msg = "; ".join(parts)
    return {
        "retry_count": state.get("retry_count", 0) + 1,
        "execution_error": error_msg,
        "plan": None,
        "execution": None,
    }


def save_solution_node(state: WorkflowState) -> WorkflowState:
    """Persist a successful solution to the knowledge base and rebuild vector store."""
    user_input = state["user_input"]
    triage_result = state.get("triage")
    execution = state.get("execution")
    problem_type = triage_result.problem_type.value if triage_result else "unknown"
    summary = execution.final_response if execution else user_input

    path = save_solution_to_knowledge_base(
        problem=user_input,
        solution=summary,
        problem_type=problem_type,
    )
    if path:
        built = build_vectorstore()
        if built:
            logger.info("Vector store rebuilt with new solution.")
        state["final_response"] = (
            f"{state.get('final_response', '')}\n\n✅ Solution saved to the knowledge base: {path}"
        )
    return {"solution_saved": True}


def _build_context_str(history: list) -> str:
    """Build a context string from conversation history."""
    if not history:
        return ""
    lines = []
    for turn in history:
        if isinstance(turn, dict):
            role = turn.get("role", "user")
            content = turn.get("content", "")
        else:
            role = turn.role
            content = turn.content
        lines.append(f"{role.capitalize()}: {content}")
    return "\n".join(lines)


# --- Graph construction -----------------------------------------------------


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
    graph.add_node("clarify_agent", clarify_node)
    graph.add_node("diagnostic_agent", diagnostic_node)
    graph.add_node("planner_agent", planner_node)
    graph.add_node("executor_agent", executor_node)
    graph.add_node("rediagnose_setup", rediagnose_setup_node)
    graph.add_node("save_solution", save_solution_node)

    graph.add_edge(START, "triage_agent")

    graph.add_conditional_edges(
        "triage_agent",
        _should_clarify,
        {
            "clarify": "clarify_agent",
            "diagnose": "diagnostic_agent",
        },
    )

    graph.add_edge("clarify_agent", END)

    graph.add_edge("diagnostic_agent", "planner_agent")
    graph.add_edge("planner_agent", "executor_agent")

    graph.add_conditional_edges(
        "executor_agent",
        _after_execution,
        {
            "rediagnose": "rediagnose_setup",
            "save": "save_solution",
            "done": END,
        },
    )

    graph.add_edge("rediagnose_setup", "diagnostic_agent")
    graph.add_edge("save_solution", END)

    checkpointer = MemorySaver()
    interrupt_nodes = ["executor_agent"]
    if with_interrupt:
        return graph.compile(checkpointer=checkpointer, interrupt_before=interrupt_nodes)
    return graph.compile(checkpointer=checkpointer)


# --- Deterministic orchestration helpers (used by the Streamlit UI) ---------


def run_analysis(user_input: str, state: AgentState | None = None) -> AgentState:
    """Run triage -> diagnostic -> planner and return the partial state.

    Stops *before* execution so sensitive steps can be approved by a human.
    Supports clarification: if triage has low confidence, the state is marked
    and no further analysis is performed.

    Args:
        user_input: The raw problem description.
        state: Optional existing state for multi-turn / re-diagnosis.

    Returns:
        An :class:`AgentState` populated with triage, diagnosis, and plan.
    """
    if state is None:
        state = AgentState(user_input=user_input)
    else:
        state.user_input = user_input

    try:
        context = state.build_conversation_context()
        state.triage = triage(user_input, conversation_context=context)

        if state.triage.needs_clarification and state.clarification_count < CLARIFICATION_MAX:
            state.needs_clarification = True
            state.clarification_question = state.triage.clarification_question
            return state

        state.diagnosis = diagnose(
            user_input,
            state.triage,
            execution_error=state.execution_error,
        )
        state.plan = plan_actions(state.triage, state.diagnosis)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Analysis failed")
        state.errors.append(str(exc))
    return state


def handle_clarification(user_input: str, state: AgentState) -> AgentState:
    """Process a clarification response and re-run triage.

    Args:
        user_input: The user's clarification response.
        state: The current state needing clarification.

    Returns:
        Updated state after re-triage with additional context.
    """
    state.add_user_turn(user_input)
    state.clarification_count += 1
    state.needs_clarification = False
    state.clarification_question = ""
    state.execution_error = ""

    try:
        context = state.build_conversation_context()
        combined_input = f"{state.user_input}\n{user_input}"
        state.triage = triage(combined_input, conversation_context=context)

        if state.triage.needs_clarification and state.clarification_count < CLARIFICATION_MAX:
            state.needs_clarification = True
            state.clarification_question = state.triage.clarification_question
            return state

        state.diagnosis = diagnose(combined_input, state.triage)
        state.plan = plan_actions(state.triage, state.diagnosis)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Clarification analysis failed")
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


def _save_solution_to_kb(state: AgentState) -> None:
    """Save a successful solution to the knowledge base and rebuild vector store."""
    problem_type = state.triage.problem_type.value if state.triage else "unknown"
    path = save_solution_to_knowledge_base(
        problem=state.user_input,
        solution=state.final_response,
        problem_type=problem_type,
    )
    if path:
        built = build_vectorstore()
        if built:
            logger.info("Vector store rebuilt with new solution.")
        state.final_response += "\n\n✅ Solution saved to the knowledge base."
        state.solution_saved = True


def run_execution(state: AgentState) -> AgentState:
    """Execute the (approved) plan stored in ``state`` and record results.

    Supports re-diagnosis: if any step fails and retries remain, the state is
    updated with the error context and re-analysis is triggered.

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
        state.add_assistant_turn(state.final_response)

        # Check for re-diagnosis opportunity
        if state.retry_count < state.max_retries:
            failed = [r for r in state.execution.results if r.status == StepStatus.FAILED]
            if failed:
                parts = []
                for r in failed:
                    detail = f"Step {r.step} ({r.tool}): {r.message}"
                    if r.output and "error" in r.output:
                        detail += f" | {r.output['error']}"
                    parts.append(detail)
                error_msg = "; ".join(parts)
                state.retry_count += 1
                state.execution_error = error_msg
                state.plan = None
                state.execution = None
                logger.info(
                    "Re-diagnosis attempt %d/%d after error: %s",
                    state.retry_count,
                    state.max_retries,
                    error_msg,
                )

        # Auto-save to KB on successful execution
        if (
            state.execution is not None
            and state.execution.all_succeeded
            and not state.solution_saved
        ):
            _save_solution_to_kb(state)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Execution failed")
        state.errors.append(str(exc))
    return state


def run_followup(follow_up: str, state: AgentState) -> AgentState:
    """Process a multi-turn follow-up from the user.

    Appends the follow-up to the conversation history, resets analysis state,
    and re-runs triage -> diagnosis -> planner with full conversational context.

    Args:
        follow_up: The user's follow-up message (e.g. "I already installed that but now I get this error").
        state: The existing agent state from the previous turn.

    Returns:
        Updated state with new triage, diagnosis, and plan for the follow-up.
    """
    state.add_user_turn(follow_up)
    state.triage = None
    state.diagnosis = None
    state.plan = None
    state.execution = None
    state.needs_clarification = False
    state.clarification_question = ""
    state.clarification_count = 0
    state.retry_count = 0
    state.max_retries = 2
    state.execution_error = ""
    state.final_response = ""
    state.errors = []
    state.solution_saved = False

    return run_analysis(follow_up, state)


def run_full(user_input: str, auto_approve: bool = False) -> AgentState:
    """Run the entire pipeline end to end (convenience for tests/CLI/eval).

    Supports clarification, re-diagnosis, and KB auto-expansion.

    Args:
        user_input: The raw problem description.
        auto_approve: If True, approve all sensitive steps automatically. Use
            with care; intended for tests and non-destructive demos (network is
            mocked and process kills default to dry-run).

    Returns:
        The fully populated :class:`AgentState`.
    """
    state = run_analysis(user_input)

    # Clarification loop
    while state.needs_clarification:
        simulated_response = "I have no more information."
        state = handle_clarification(simulated_response, state)

    # Execution loop with re-diagnosis support
    max_cycles = MAX_RETRIES + 1
    cycle = 0
    while state.plan is not None and cycle < max_cycles:
        cycle += 1
        if auto_approve:
            approvals = {s.step: True for s in state.plan.plan if s.requires_approval}
            apply_approvals(state.plan, approvals)
        state = run_execution(state)

        if state.execution is not None and state.execution.all_succeeded:
            break

    return state
