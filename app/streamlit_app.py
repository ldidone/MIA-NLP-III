"""Streamlit UI for CompuFix Agents.

Run with::

    streamlit run app/streamlit_app.py

The UI runs the analysis pipeline (triage -> diagnosis -> plan), lets the user
approve sensitive steps, and then executes the approved plan. Network actions
are simulated and process kills default to dry-run.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make the 'src' layout importable when run via `streamlit run app/streamlit_app.py`.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import streamlit as st  # noqa: E402

from compufix_agents.config import get_settings  # noqa: E402
from compufix_agents.graph.state import AgentState  # noqa: E402
from compufix_agents.graph.workflow import (  # noqa: E402
    apply_approvals,
    handle_clarification,
    run_analysis,
    run_execution,
    run_followup,
)
from compufix_agents.schemas.execution import StepStatus  # noqa: E402
from compufix_agents.tools.runtime import set_runtime_preferences  # noqa: E402

EXAMPLE_INPUTS = [
    "ModuleNotFoundError: No module named 'cv2'",
    "ModuleNotFoundError: No module named 'sklearn'",
    "My internet is very slow",
    "My computer is slow and using a lot of RAM",
]

_STATUS_ICON = {
    StepStatus.SUCCESS: "✅",
    StepStatus.FAILED: "❌",
    StepStatus.SKIPPED_NOT_APPROVED: "⏭️",
    StepStatus.SKIPPED_UNKNOWN_TOOL: "🚫",
}


def _init_state() -> None:
    st.session_state.setdefault("agent_state", None)
    st.session_state.setdefault("input_text", "")
    st.session_state.setdefault("conversation_history", [])
    st.session_state.setdefault("clarification_mode", False)
    st.session_state.setdefault("show_clarification_input", False)
    st.session_state.setdefault("analysis_done", False)
    st.session_state.setdefault("executed", None)
    st.session_state.setdefault("followup_mode", False)


def _security_preferences() -> None:
    """Ask the user how sensitive actions should be performed, then apply them.

    These choices are applied to the runtime preferences on every rerun, so they
    take effect before any plan is executed.
    """
    st.sidebar.subheader("🔐 Security & execution")
    st.sidebar.caption("Choose how CompuFix is allowed to act on your machine.")

    pkg_labels = {
        "Don't install — just tell me how (safest)": "off",
        "Install into a virtual environment (.venv)": "venv",
        "Install into the current interpreter": "current",
    }
    pkg_choice = st.sidebar.radio(
        "Python packages",
        list(pkg_labels),
        index=0,
        key="pref_pkg",
    )
    venv_path = ".venv"
    if pkg_labels[pkg_choice] == "venv":
        venv_path = st.sidebar.text_input(
            "Virtual environment folder",
            value=st.session_state.get("pref_venv_path", ".venv"),
            key="pref_venv_path",
            help="Created automatically if it doesn't exist (relative to the project root).",
        )

    proc_labels = {
        "Simulated — never touch real processes (safest)": "simulated",
        "Real — inspect/kill actual processes": "real",
    }
    proc_choice = st.sidebar.radio(
        "Processes",
        list(proc_labels),
        index=0,
        key="pref_proc",
    )

    net_labels = {
        "Simulated switch (demo)": "simulated",
        "Don't change my network (safest)": "off",
    }
    net_choice = st.sidebar.radio(
        "Network",
        list(net_labels),
        index=0,
        key="pref_net",
    )

    set_runtime_preferences(
        package_install_mode=pkg_labels[pkg_choice],
        venv_path=venv_path,
        process_mode=proc_labels[proc_choice],
        network_mode=net_labels[net_choice],
    )
    st.sidebar.divider()


def _sidebar() -> None:
    st.sidebar.title("CompuFix Agents")
    st.sidebar.caption("Multi-agent computer troubleshooting (MVP)")

    settings = get_settings()
    mode = "LLM-enabled" if settings.llm_enabled else "Deterministic (no API key)"
    st.sidebar.info(f"Mode: **{mode}**")

    _security_preferences()

    if st.session_state.conversation_history:
        st.sidebar.subheader("Conversation history")
        for turn in st.session_state.conversation_history:
            role = "🧑" if turn.role == "user" else "🤖"
            st.sidebar.caption(f"{role} {turn.content[:120]}...")

    if st.sidebar.button("🔄 New conversation"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

    st.sidebar.subheader("Example problems")
    for ex in EXAMPLE_INPUTS:
        if st.sidebar.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state.input_text = ex
            for key in list(st.session_state.keys()):
                if key not in ("input_text",):
                    del st.session_state[key]
            _init_state()
            st.session_state.input_text = ex


def _render_triage(triage) -> None:
    st.subheader("1. Detected problem")
    col1, col2 = st.columns(2)
    col1.metric("Problem type", triage.problem_type.value)
    col2.metric("Confidence", f"{triage.confidence:.2f}")
    if triage.extracted_entities:
        st.write("**Extracted entities**")
        st.json(triage.extracted_entities)


def _render_diagnosis(diagnosis) -> None:
    st.subheader("2. Diagnosis")
    if diagnosis.is_rediagnosis:
        st.warning("🔄 Re-diagnosis after an execution error")
    st.write(diagnosis.diagnosis)
    if diagnosis.recommended_next_step:
        st.success(f"**Recommended next step:** {diagnosis.recommended_next_step}")

    if diagnosis.retrieved_docs:
        with st.expander(f"Retrieved documents ({len(diagnosis.retrieved_docs)})"):
            for doc in diagnosis.retrieved_docs:
                score = f" (score: {doc.score})" if doc.score is not None else ""
                st.markdown(f"**{doc.source}**{score}")
                st.code(doc.content[:600], language="markdown")


def _render_plan_and_approvals(plan) -> dict[int, bool]:
    st.subheader("3. Proposed action plan")
    if state := st.session_state.agent_state:
        if state.retry_count > 0:
            st.info(f"🔄 Re-diagnosis attempt #{state.retry_count}/{state.max_retries}")

    approvals: dict[int, bool] = {}
    if not plan.plan:
        st.warning("No actionable plan was produced for this problem.")
        return approvals

    for step in plan.plan:
        risk_color = {"low": "green", "medium": "orange", "high": "red"}.get(
            step.risk.value, "gray"
        )
        st.markdown(f"**Step {step.step}: `{step.tool}`** — :{risk_color}[risk: {step.risk.value}]")
        if step.args:
            st.caption(f"args: {step.args}")
        if step.rationale:
            st.caption(step.rationale)
        if step.requires_approval:
            approvals[step.step] = st.checkbox(
                f"✋ Approve step {step.step} ({step.tool})",
                key=f"approve_{step.step}",
                value=False,
            )
        else:
            st.caption("No approval required (read-only).")
        st.divider()
    return approvals


def _render_execution(execution) -> None:
    state = st.session_state.agent_state
    if execution.results:
        st.subheader("5. Execution results")
        for r in execution.results:
            icon = _STATUS_ICON.get(r.status, "•")
            st.markdown(f"{icon} **Step {r.step}: `{r.tool}`** — {r.status.value}")
            if r.output:
                with st.expander(f"Output of step {r.step}"):
                    st.json(r.output)
            if r.message:
                st.caption(r.message)

        if state and state.solution_saved:
            st.success("📚 Solution automatically saved to the knowledge base.")

        st.subheader("6. Final answer")
        st.success(execution.final_response)
    else:
        # Diagnosis-only problems (no executed steps): show the final answer
        # from the agent state, which carries the diagnosis-based response.
        st.subheader("4. Final answer")
        final_text = (
            state.final_response if state and state.final_response else execution.final_response
        )
        st.success(final_text)


def _render_clarification() -> None:
    st.subheader("💬 I need more information")
    state = st.session_state.agent_state
    st.info(state.clarification_question)

    clarification_input = st.text_area(
        "Your answer",
        key="clarification_input",
        height=100,
        placeholder="Describe in more detail what is happening...",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("📤 Send", key="send_clarification", type="primary"):
            if clarification_input.strip():
                _process_clarification(clarification_input)
                st.rerun()
            else:
                st.warning("Please type an answer.")

    with col2:
        if st.button("⏭️ Skip", key="skip_clarification"):
            _process_clarification("I have no more information to add.")
            st.rerun()

    st.caption(f"Attempt {state.clarification_count + 1} of 2")


def _process_clarification(response: str) -> None:
    state = st.session_state.agent_state
    state = handle_clarification(response, state)
    st.session_state.agent_state = state
    st.session_state.conversation_history = state.conversation_history

    if state.needs_clarification:
        st.session_state.clarification_mode = True
        st.session_state.show_clarification_input = True
    else:
        st.session_state.clarification_mode = False
        st.session_state.show_clarification_input = False
        st.session_state.analysis_done = True


def _run_analysis_flow() -> None:
    state = AgentState(user_input=st.session_state.input_text)
    state = run_analysis(st.session_state.input_text, state)
    st.session_state.agent_state = state
    st.session_state.conversation_history = state.conversation_history

    if state.needs_clarification:
        st.session_state.clarification_mode = True
        st.session_state.show_clarification_input = True
    else:
        st.session_state.clarification_mode = False
        st.session_state.analysis_done = True


def main() -> None:
    st.set_page_config(page_title="CompuFix Agents", page_icon="🛠️", layout="wide")
    _init_state()
    _sidebar()

    st.title("🛠️ CompuFix Agents")
    st.write(
        "Describe a computer problem (e.g. a Python error, slow internet, or a "
        "slow computer). The agents will triage, diagnose, and propose a safe plan."
    )

    user_input = st.text_area(
        "Describe your problem",
        value=st.session_state.input_text,
        height=120,
        placeholder="ModuleNotFoundError: No module named 'cv2'",
    )

    if st.button("🔍 Analyze problem", type="primary"):
        if user_input.strip():
            st.session_state.input_text = user_input
            _run_analysis_flow()
            st.rerun()
        else:
            st.warning("Please describe a problem first.")

    state = st.session_state.agent_state

    if state and st.session_state.show_clarification_input:
        _render_clarification()
        return

    if state and st.session_state.analysis_done:
        if state.errors:
            st.error("\n".join(state.errors))

        if state.triage:
            _render_triage(state.triage)
        if state.diagnosis:
            _render_diagnosis(state.diagnosis)

        if state.plan:
            approvals = _render_plan_and_approvals(state.plan)

            if not state.plan.plan:
                # Diagnosis-only problems: nothing to approve, so produce the
                # final answer automatically.
                if st.session_state.executed is None:
                    state = run_execution(state)
                    st.session_state.agent_state = state
                    st.session_state.executed = state.execution
            else:
                st.subheader("4. Execute")
                needs_approval = state.plan.requires_any_approval()
                if needs_approval:
                    st.info(
                        "Sensitive steps require your approval (checkboxes above). "
                        "Unapproved sensitive steps will be skipped."
                    )

                col1, col2 = st.columns([1, 5])
                with col1:
                    if st.button("▶️ Execute approved actions", type="primary"):
                        apply_approvals(state.plan, approvals)
                        with st.spinner("Executing plan..."):
                            state = run_execution(state)
                            st.session_state.agent_state = state
                            st.session_state.executed = state.execution

                            # Check for re-diagnosis
                            if state.plan is None and state.execution_error:
                                st.info(
                                    f"🔄 Re-diagnosing after an error "
                                    f"(attempt {state.retry_count}/{state.max_retries})..."
                                )
                                state = run_analysis(state.user_input, state)
                                st.session_state.agent_state = state
                                st.session_state.analysis_done = True
                                st.rerun()

                        st.rerun()

                with col2:
                    if state.retry_count > 0:
                        st.caption(f"Re-diagnosis #{state.retry_count}")

    executed = st.session_state.executed
    if executed is not None:
        _render_execution(executed)

        st.markdown("---")
        st.subheader("💬 Follow-up")
        st.caption(
            "If the problem was only partially solved or you have a new symptom, "
            "write it here to continue the conversation."
        )

        follow_up = st.text_area(
            "Your follow-up",
            key="followup_input",
            height=80,
            placeholder="E.g.: I already installed the library but now I get this error...",
        )

        col_fu1, col_fu2, col_fu3 = st.columns([1, 1, 4])
        with col_fu1:
            if st.button("📤 Send follow-up", key="send_followup", type="primary"):
                if follow_up.strip():
                    state = st.session_state.agent_state
                    state = run_followup(follow_up, state)
                    st.session_state.agent_state = state
                    st.session_state.conversation_history = state.conversation_history
                    st.session_state.executed = None

                    if state.needs_clarification:
                        st.session_state.show_clarification_input = True
                        st.session_state.clarification_mode = True
                        st.session_state.analysis_done = False
                    else:
                        st.session_state.show_clarification_input = False
                        st.session_state.clarification_mode = False
                        st.session_state.analysis_done = True
                    st.session_state.followup_mode = True
                    st.rerun()
                else:
                    st.warning("Type a follow-up message.")

        with col_fu2:
            if st.button("🔄 New problem"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()


if __name__ == "__main__":
    main()
