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

EXAMPLE_INPUTS = [
    "ModuleNotFoundError: No module named 'cv2'",
    "ModuleNotFoundError: No module named 'sklearn'",
    "Mi internet está muy lento",
    "La computadora está lenta y consume mucha RAM",
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


def _sidebar() -> None:
    st.sidebar.title("CompuFix Agents")
    st.sidebar.caption("Multi-agent computer troubleshooting (MVP)")

    settings = get_settings()
    mode = "LLM-enabled" if settings.llm_enabled else "Deterministic (no API key)"
    st.sidebar.info(f"Mode: **{mode}**")
    st.sidebar.write(
        f"Real process kill: **{'enabled' if settings.allow_real_process_kill else 'disabled'}**"
    )

    if st.session_state.conversation_history:
        st.sidebar.subheader("Conversation history")
        for turn in st.session_state.conversation_history:
            role = "🧑" if turn.role == "user" else "🤖"
            st.sidebar.caption(f"{role} {turn.content[:120]}...")

    if st.sidebar.button("🔄 Nueva conversación"):
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
        st.warning("🔄 Re-diagnóstico tras error de ejecución")
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
            st.info(f"🔄 Intento de re-diagnóstico #{state.retry_count}/{state.max_retries}")

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
    st.subheader("5. Execution results")
    for r in execution.results:
        icon = _STATUS_ICON.get(r.status, "•")
        st.markdown(f"{icon} **Step {r.step}: `{r.tool}`** — {r.status.value}")
        if r.output:
            with st.expander(f"Output of step {r.step}"):
                st.json(r.output)
        if r.message:
            st.caption(r.message)

    state = st.session_state.agent_state
    if state and state.solution_saved:
        st.success("📚 Solución guardada automáticamente en la base de conocimiento.")

    st.subheader("6. Final answer")
    st.success(execution.final_response)


def _render_clarification() -> None:
    st.subheader("💬 Necesito más información")
    state = st.session_state.agent_state
    st.info(state.clarification_question)

    clarification_input = st.text_area(
        "Tu respuesta",
        key="clarification_input",
        height=100,
        placeholder="Describe con más detalle qué está ocurriendo...",
    )

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("📤 Enviar", key="send_clarification", type="primary"):
            if clarification_input.strip():
                _process_clarification(clarification_input)
                st.rerun()
            else:
                st.warning("Por favor escribe una respuesta.")

    with col2:
        if st.button("⏭️ Omitir", key="skip_clarification"):
            _process_clarification("No tengo más información para agregar.")
            st.rerun()

    st.caption(f"Intento {state.clarification_count + 1} de 2")


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
                                f"🔄 Re-diagnosticando tras error "
                                f"(intento {state.retry_count}/{state.max_retries})..."
                            )
                            state = run_analysis(state.user_input, state)
                            st.session_state.agent_state = state
                            st.session_state.analysis_done = True
                            st.rerun()

                    st.rerun()

            with col2:
                if state.retry_count > 0:
                    st.caption(f"Re-diagnóstico #{state.retry_count}")

    executed = st.session_state.executed
    if executed is not None:
        _render_execution(executed)

        st.markdown("---")
        st.subheader("💬 Seguimiento")
        st.caption(
            "Si el problema se resolvió parcialmente o tienes un nuevo síntoma, "
            "escríbelo aquí para continuar la conversación."
        )

        follow_up = st.text_area(
            "Tu seguimiento",
            key="followup_input",
            height=80,
            placeholder="Ej: ya instalé la librería pero ahora me da este error...",
        )

        col_fu1, col_fu2, col_fu3 = st.columns([1, 1, 4])
        with col_fu1:
            if st.button("📤 Enviar seguimiento", key="send_followup", type="primary"):
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
                    st.warning("Escribe un mensaje de seguimiento.")

        with col_fu2:
            if st.button("🔄 Nuevo problema"):
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()


if __name__ == "__main__":
    main()
