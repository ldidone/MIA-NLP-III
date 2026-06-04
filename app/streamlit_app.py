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
from compufix_agents.graph.workflow import (  # noqa: E402
    apply_approvals,
    run_analysis,
    run_execution,
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
    st.session_state.setdefault("analysis", None)
    st.session_state.setdefault("executed", None)
    st.session_state.setdefault("input_text", "")


def _sidebar() -> None:
    st.sidebar.title("CompuFix Agents")
    st.sidebar.caption("Multi-agent computer troubleshooting (MVP)")

    settings = get_settings()
    mode = "LLM-enabled" if settings.llm_enabled else "Deterministic (no API key)"
    st.sidebar.info(f"Mode: **{mode}**")
    st.sidebar.write(
        f"Real process kill: **{'enabled' if settings.allow_real_process_kill else 'disabled'}**"
    )

    st.sidebar.subheader("Example problems")
    for ex in EXAMPLE_INPUTS:
        if st.sidebar.button(ex, key=f"ex_{ex}", use_container_width=True):
            st.session_state.input_text = ex
            st.session_state.analysis = None
            st.session_state.executed = None


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
    approvals: dict[int, bool] = {}
    if not plan.plan:
        st.warning("No actionable plan was produced for this problem.")
        return approvals

    for step in plan.plan:
        risk_color = {"low": "green", "medium": "orange", "high": "red"}.get(
            step.risk.value, "gray"
        )
        st.markdown(
            f"**Step {step.step}: `{step.tool}`** — "
            f":{risk_color}[risk: {step.risk.value}]"
        )
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
    st.subheader("6. Final answer")
    st.success(execution.final_response)


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
            with st.spinner("Running triage, diagnosis, and planning..."):
                st.session_state.analysis = run_analysis(user_input)
            st.session_state.executed = None
        else:
            st.warning("Please describe a problem first.")

    analysis = st.session_state.analysis
    if analysis is not None:
        if analysis.errors:
            st.error("\n".join(analysis.errors))

        if analysis.triage:
            _render_triage(analysis.triage)
        if analysis.diagnosis:
            _render_diagnosis(analysis.diagnosis)

        if analysis.plan:
            approvals = _render_plan_and_approvals(analysis.plan)

            st.subheader("4. Execute")
            needs_approval = analysis.plan.requires_any_approval()
            if needs_approval:
                st.info(
                    "Sensitive steps require your approval (checkboxes above). "
                    "Unapproved sensitive steps will be skipped."
                )
            if st.button("▶️ Execute approved actions"):
                apply_approvals(analysis.plan, approvals)
                with st.spinner("Executing plan..."):
                    st.session_state.executed = run_execution(analysis)

    executed = st.session_state.executed
    if executed is not None and executed.execution is not None:
        _render_execution(executed.execution)


if __name__ == "__main__":
    main()
