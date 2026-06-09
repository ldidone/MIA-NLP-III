"""Tests for the Diagnostic Agent (deterministic, no-API-key path)."""

from __future__ import annotations

from compufix_agents.agents.diagnostic_agent import diagnose
from compufix_agents.agents.triage_agent import rule_based_triage
from compufix_agents.schemas.diagnosis import DiagnosisResult


def test_diagnose_python_missing_library_is_grounded():
    triage = rule_based_triage("ModuleNotFoundError: No module named 'cv2'")
    result = diagnose("ModuleNotFoundError: No module named 'cv2'", triage)
    assert isinstance(result, DiagnosisResult)
    assert result.diagnosis
    assert result.recommended_next_step
    # Diagnosis is grounded in retrieved docs.
    assert result.retrieved_docs
    assert any("python" in d.source.replace("\\", "/") for d in result.retrieved_docs)


def test_diagnose_network_slow():
    triage = rule_based_triage("Mi internet está muy lento")
    result = diagnose("Mi internet está muy lento", triage)
    assert "5GHz" in result.diagnosis or "network" in result.diagnosis.lower()
    assert result.retrieved_docs


def test_diagnose_high_resource_usage():
    text = "La computadora está lenta y consume mucha RAM"
    triage = rule_based_triage(text)
    result = diagnose(text, triage)
    assert result.diagnosis
    assert result.evidence  # evidence comes from retrieved docs


def test_diagnose_respects_requires_retrieval_false():
    triage = rule_based_triage("ModuleNotFoundError: No module named 'cv2'")
    triage.requires_retrieval = False
    result = diagnose("ModuleNotFoundError: No module named 'cv2'", triage)
    assert result.retrieved_docs == []
    # Still returns a deterministic diagnosis.
    assert result.diagnosis
