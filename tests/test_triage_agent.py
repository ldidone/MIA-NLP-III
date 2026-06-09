"""Tests for the rule-based triage classifier and import->package mapping."""

from __future__ import annotations

import pytest

from compufix_agents.agents.triage_agent import rule_based_triage, triage
from compufix_agents.schemas.triage import ProblemType
from compufix_agents.tools.python_env_tools import map_import_to_package


@pytest.mark.parametrize(
    ("text", "expected_module", "expected_package"),
    [
        ("ModuleNotFoundError: No module named 'cv2'", "cv2", "opencv-python"),
        ("ModuleNotFoundError: No module named 'sklearn'", "sklearn", "scikit-learn"),
        ("ImportError: No module named yaml", "yaml", "PyYAML"),
        ("No module named 'sklearn.tree'", "sklearn", "scikit-learn"),
        ("ModuleNotFoundError: No module named 'pandas'", "pandas", "pandas"),
    ],
)
def test_python_missing_library(text, expected_module, expected_package):
    result = rule_based_triage(text)
    assert result.problem_type == ProblemType.PYTHON_MISSING_LIBRARY
    assert result.extracted_entities["missing_module"] == expected_module
    assert result.extracted_entities["package_name"] == expected_package
    assert result.confidence >= 0.9


@pytest.mark.parametrize(
    "text",
    [
        "Mi internet está muy lento",
        "My wifi is really slow",
        "the network connection is slow today",
    ],
)
def test_network_slow(text):
    result = rule_based_triage(text)
    assert result.problem_type == ProblemType.NETWORK_SLOW


@pytest.mark.parametrize(
    "text",
    [
        "La computadora está muy lenta y el ventilador hace ruido",
        "La computadora está lenta y consume mucha RAM",
        "high CPU usage is slowing everything down",
    ],
)
def test_high_resource_usage(text):
    result = rule_based_triage(text)
    assert result.problem_type == ProblemType.HIGH_RESOURCE_USAGE


def test_unknown_for_empty_or_irrelevant():
    assert rule_based_triage("").problem_type == ProblemType.UNKNOWN
    assert triage("   ").problem_type == ProblemType.UNKNOWN
    assert rule_based_triage("hello there").problem_type == ProblemType.UNKNOWN


@pytest.mark.parametrize(
    ("module", "package"),
    [
        ("cv2", "opencv-python"),
        ("sklearn", "scikit-learn"),
        ("PIL", "Pillow"),
        ("yaml", "PyYAML"),
        ("dotenv", "python-dotenv"),
        ("pandas", "pandas"),  # no mapping -> identity
        ("numpy", "numpy"),
    ],
)
def test_map_import_to_package(module, package):
    assert map_import_to_package(module) == package


def test_triage_without_llm_uses_rules():
    # use_llm=False guarantees the deterministic path.
    result = triage("ModuleNotFoundError: No module named 'cv2'", use_llm=False)
    assert result.problem_type == ProblemType.PYTHON_MISSING_LIBRARY
    assert result.extracted_entities["package_name"] == "opencv-python"


@pytest.mark.parametrize(
    "text",
    [
        'if x = 10\n    print("Hello")',
        'def my_function():\nprint("Missing indent")',
        'message = "Welcome"\nprint(mesage)  # Typo in variable name',
        'total = "Price: " + 50',
        'items = ["apple", "banana"]\nprint(items[2])  # The maximum index available is 1',
        "SyntaxError: invalid syntax",
        "IndentationError: expected an indented block",
        "NameError: name 'mesage' is not defined",
        "TypeError: can only concatenate str (not 'int') to str",
        "IndexError: list index out of range",
    ],
)
def test_python_errors_triage(text):
    result = rule_based_triage(text)
    assert result.problem_type == ProblemType.PYTHON_ERROR
    assert result.requires_retrieval is True
    assert result.requires_system_tools is False

