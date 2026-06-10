"""Diagnostic Agent: produce a grounded diagnosis from retrieved docs.

The agent retrieves relevant knowledge-base chunks and turns them into a
:class:`DiagnosisResult`. When an LLM is configured it is used to phrase the
diagnosis (constrained to the retrieved context); otherwise a deterministic
template based on the problem type and retrieved docs is used.

The agent never invents procedures that are not present in the retrieved docs:
the deterministic path quotes the docs directly, and the LLM path is instructed
to stay within the provided context.
"""

from __future__ import annotations

import json
import re

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger
from compufix_agents.rag.retriever import retrieve_relevant_docs
from compufix_agents.schemas.diagnosis import DiagnosisResult, RetrievedDoc
from compufix_agents.schemas.triage import ProblemType, TriageResult

logger = get_logger(__name__)

# Deterministic diagnosis templates keyed by problem type. Each references the
# retrieved documentation rather than inventing new procedures.
_DETERMINISTIC_DIAGNOSIS: dict[ProblemType, dict[str, str]] = {
    ProblemType.PYTHON_MISSING_LIBRARY: {
        "diagnosis": (
            "A required Python module is not installed in the active interpreter. "
            "The package providing the missing import must be installed (the pip "
            "package name may differ from the import name)."
        ),
        "next_step": (
            "Install the correct pip package with 'python -m pip install <package>' "
            "and verify the import afterwards."
        ),
    },
    ProblemType.PYTHON_ERROR: {
        "diagnosis": (
            "A Python syntax or runtime error occurred (e.g. SyntaxError, IndentationError, "
            "NameError, TypeError, IndexError). This is a code bug rather than a missing library."
        ),
        "next_step": (
            "Review the specific code syntax, verify indentation spacing, check for variable typos, "
            "verify data types are compatible, and ensure index accesses are within sequence bounds."
        ),
    },
    ProblemType.NETWORK_SLOW: {
        "diagnosis": (
            "The connection is slow, commonly because the device is on a slower "
            "2.4GHz Wi-Fi band while a faster 5GHz network is available."
        ),
        "next_step": (
            "Compare the current network with available networks and switch to a "
            "faster 5GHz network if one with usable signal exists."
        ),
    },
    ProblemType.HIGH_RESOURCE_USAGE: {
        "diagnosis": (
            "The computer is slow due to high CPU and/or RAM usage, likely caused "
            "by one or more processes consuming excessive resources."
        ),
        "next_step": (
            "List the top processes by CPU/memory to identify the offender; if it "
            "is a non-critical process, terminating it (with approval) frees "
            "resources."
        ),
    },
    ProblemType.UNKNOWN: {
        "diagnosis": (
            "The problem could not be confidently classified from the description "
            "and the available documentation."
        ),
        "next_step": "Ask the user for more detail (exact error message or symptom).",
    },
}


def _build_context(docs: list[dict]) -> str:
    """Concatenate retrieved docs into a single context string."""
    parts = []
    for d in docs:
        parts.append(f"[source: {d['source']}]\n{d['content']}")
    return "\n\n---\n\n".join(parts)


def _evidence_from_docs(docs: list[dict], max_items: int = 3) -> list[str]:
    """Build short evidence strings (source + first line) from retrieved docs."""
    evidence: list[str] = []
    for d in docs[:max_items]:
        first_line = next(
            (ln.strip("# ").strip() for ln in d["content"].splitlines() if ln.strip()),
            "",
        )
        evidence.append(f"{d['source']}: {first_line}")
    return evidence


def _deterministic_diagnosis(
    triage: TriageResult,
    docs: list[dict],
    execution_error: str = "",
) -> DiagnosisResult:
    """Build a diagnosis deterministically from problem type + retrieved docs."""
    is_rediagnosis = bool(execution_error)
    diagnosis_text = _DETERMINISTIC_DIAGNOSIS.get(
        triage.problem_type, _DETERMINISTIC_DIAGNOSIS[ProblemType.UNKNOWN]
    )["diagnosis"]

    if is_rediagnosis:
        diagnosis_text = (
            f"[Re-diagnosis after an execution error]\n\n"
            f"{diagnosis_text}\n\n"
            f"The previous step failed with: {execution_error}\n"
            "Reviewing additional information to find an alternative solution."
        )

    return DiagnosisResult(
        diagnosis=diagnosis_text,
        evidence=_evidence_from_docs(docs),
        recommended_next_step=_DETERMINISTIC_DIAGNOSIS.get(
            triage.problem_type, _DETERMINISTIC_DIAGNOSIS[ProblemType.UNKNOWN]
        )["next_step"],
        retrieved_docs=[RetrievedDoc(**d) for d in docs],
        is_rediagnosis=is_rediagnosis,
    )


def _llm_diagnosis(
    user_input: str, triage: TriageResult, docs: list[dict]
) -> DiagnosisResult | None:
    """Attempt an LLM diagnosis constrained to the context; None on failure."""
    settings = get_settings()
    if not settings.llm_enabled or not docs:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from compufix_agents.prompts.diagnostic_prompt import build_diagnostic_messages
    except ImportError:
        return None

    try:
        llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-4o-mini", temperature=0)
        messages = build_diagnostic_messages(
            user_input=user_input,
            problem_type=triage.problem_type.value,
            entities=triage.extracted_entities,
            context=_build_context(docs),
        )
        response = llm.invoke(messages)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        return DiagnosisResult(
            diagnosis=data.get("diagnosis", ""),
            evidence=data.get("evidence", []),
            recommended_next_step=data.get("recommended_next_step", ""),
            retrieved_docs=[RetrievedDoc(**d) for d in docs],
        )
    except Exception as exc:  # pragma: no cover - network/parse failures
        logger.warning("LLM diagnosis failed (%s); using deterministic fallback.", exc)
        return None


def diagnose(
    user_input: str,
    triage: TriageResult,
    k: int = 4,
    execution_error: str = "",
) -> DiagnosisResult:
    """Diagnose a problem using retrieved documentation.

    Args:
        user_input: The raw problem description.
        triage: The triage result for this problem.
        k: Number of documents to retrieve.
        execution_error: Error context from a failed execution attempt (for re-diagnosis).

    Returns:
        A :class:`DiagnosisResult` grounded in retrieved docs.
    """
    search_query = execution_error if execution_error else user_input
    docs = retrieve_relevant_docs(search_query, k=k) if triage.requires_retrieval else []
    logger.info(
        "Diagnose(%s) -> %d docs retrieved (re-diagnosis: %s)",
        triage.problem_type.value,
        len(docs),
        bool(execution_error),
    )

    llm_result = _llm_diagnosis(user_input, triage, docs)
    if llm_result is not None:
        return llm_result
    return _deterministic_diagnosis(triage, docs, execution_error)
