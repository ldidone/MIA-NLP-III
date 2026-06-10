"""Triage Agent: classify a user problem and extract entities.

Hybrid design:
    1. A deterministic **rule-based** classifier handles the common patterns and
       always works offline (no API key required).
    2. An optional **LLM-based** classifier refines results when configured.

The rule-based path is always the safety net: if the LLM is unavailable or
returns something unusable, we fall back to rules.
"""

from __future__ import annotations

import json
import re
from typing import Any

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger
from compufix_agents.schemas.triage import ProblemType, TriageResult
from compufix_agents.tools.python_env_tools import map_import_to_package

logger = get_logger(__name__)

# --- Rule patterns ----------------------------------------------------------

# Capture the module name in "No module named 'x'", "No module named x",
# or "ModuleNotFoundError: ... 'x'".
_MODULE_PATTERNS = [
    re.compile(r"no module named\s*['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(
        r"modulenotfounderror[^\w]+(?:no module named\s*)?['\"]?([\w.]+)['\"]?", re.IGNORECASE
    ),
    re.compile(r"importerror[^\w]+(?:no module named\s*)?['\"]?([\w.]+)['\"]?", re.IGNORECASE),
    re.compile(r"cannot import name .* from ['\"]?([\w.]+)['\"]?", re.IGNORECASE),
]

_PYTHON_TRIGGERS = (
    "modulenotfounderror",
    "no module named",
    "importerror",
    "cannot import name",
    "pip install",
)

_PYTHON_ERROR_KEYWORDS = (
    "syntaxerror",
    "indentationerror",
    "nameerror",
    "typeerror",
    "indexerror",
    "syntax error",
    "indentation error",
    "name error",
    "type error",
    "index error",
    "missing indent",
    "typo in variable",
    "maximum index available",
    "invalid syntax",
)

_PYTHON_CODE_TRIGGERS = (
    "def ",
    "print(",
    "if x =",
    "items = ",
    "total = ",
    "import ",
)

_NETWORK_KEYWORDS = (
    "internet",
    "wifi",
    "wi-fi",
    "wlan",
    "network",
    "red lenta",
    "conexión",
    "conexion",
    "banda ancha",
    "buffering",
    "latencia",
    "ping",
    "2.4ghz",
    "5ghz",
)

_RESOURCE_KEYWORDS = (
    "cpu",
    "ram",
    "memory",
    "memoria",
    "ventilador",
    "fan",
    "proceso",
    "process",
    "computadora",
    "computer",
    "se traba",
    "freez",
    "lag",
    "high usage",
    "consume",
    "overheat",
    "caliente",
)

_SLOW_HINTS = ("lento", "lenta", "slow", "despacio")


def _extract_module(text: str) -> str | None:
    """Return the missing module's top-level import name, if present."""
    for pattern in _MODULE_PATTERNS:
        match = pattern.search(text)
        if match:
            # Keep the top-level package (e.g. "sklearn.tree" -> "sklearn").
            return match.group(1).split(".")[0]
    return None


def _count_hits(text: str, keywords: tuple[str, ...]) -> int:
    """Count how many keywords appear in the (lowercased) text."""
    return sum(1 for kw in keywords if kw in text)


def rule_based_triage(user_input: str) -> TriageResult:
    """Classify a problem using deterministic rules.

    Args:
        user_input: The raw problem description.

    Returns:
        A :class:`TriageResult`.
    """
    text = user_input.lower()
    entities: dict[str, Any] = {}

    # 1. Python missing library (most specific / highest priority).
    module = _extract_module(user_input)
    has_python_trigger = any(trig in text for trig in _PYTHON_TRIGGERS)
    if module or has_python_trigger:
        if module:
            entities["missing_module"] = module
            entities["package_name"] = map_import_to_package(module)
        return TriageResult(
            problem_type=ProblemType.PYTHON_MISSING_LIBRARY,
            confidence=0.95 if module else 0.7,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=True,
        )

    # 1b. Python syntax/runtime errors.
    has_python_error_trigger = any(kw in text for kw in _PYTHON_ERROR_KEYWORDS) or any(
        kw in text for kw in _PYTHON_CODE_TRIGGERS
    )
    if has_python_error_trigger:
        return TriageResult(
            problem_type=ProblemType.PYTHON_ERROR,
            confidence=0.9,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=False,
        )

    # 2. Network vs. high resource usage (keyword scoring).
    network_hits = _count_hits(text, _NETWORK_KEYWORDS)
    resource_hits = _count_hits(text, _RESOURCE_KEYWORDS)
    has_slow = any(h in text for h in _SLOW_HINTS)

    if network_hits or resource_hits:
        if network_hits > resource_hits:
            confidence = 0.85 if has_slow else 0.7
            return TriageResult(
                problem_type=ProblemType.NETWORK_SLOW,
                confidence=confidence,
                extracted_entities=entities,
                requires_retrieval=True,
                requires_system_tools=True,
            )
        if resource_hits > 0:
            confidence = 0.85 if has_slow else 0.7
            return TriageResult(
                problem_type=ProblemType.HIGH_RESOURCE_USAGE,
                confidence=confidence,
                extracted_entities=entities,
                requires_retrieval=True,
                requires_system_tools=True,
            )

    # 3. A bare "slow" hint with no other signal leans toward resource usage.
    if has_slow:
        return TriageResult(
            problem_type=ProblemType.HIGH_RESOURCE_USAGE,
            confidence=0.5,
            extracted_entities=entities,
            requires_retrieval=True,
            requires_system_tools=True,
        )

    return TriageResult(
        problem_type=ProblemType.UNKNOWN,
        confidence=0.3,
        extracted_entities=entities,
        requires_retrieval=True,
        requires_system_tools=False,
    )


def _llm_triage(user_input: str) -> TriageResult | None:
    """Attempt LLM-based classification; return ``None`` on any failure."""
    settings = get_settings()
    if not settings.llm_enabled:
        return None
    try:
        from langchain_openai import ChatOpenAI

        from compufix_agents.prompts.triage_prompt import build_triage_messages
    except ImportError:
        logger.info("langchain_openai not available; skipping LLM triage.")
        return None

    try:
        llm = ChatOpenAI(api_key=settings.openai_api_key, model="gpt-4o-mini", temperature=0)
        messages = build_triage_messages(user_input)
        response = llm.invoke(messages)
        raw = response.content if isinstance(response.content, str) else str(response.content)
        # Strip accidental code fences.
        raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
        data = json.loads(raw)
        result = TriageResult(**data)
        logger.info("LLM triage -> %s (%.2f)", result.problem_type, result.confidence)
        return result
    except Exception as exc:  # pragma: no cover - network/parse failures
        logger.warning("LLM triage failed (%s); falling back to rules.", exc)
        return None


def triage(user_input: str, use_llm: bool | None = None) -> TriageResult:
    """Classify a user problem, preferring the LLM when available.

    Args:
        user_input: The raw problem description.
        use_llm: Force-enable/disable the LLM path. When ``None`` (default),
            the LLM is used only if an API key is configured.

    Returns:
        A :class:`TriageResult` (rule-based fallback is always guaranteed).
    """
    if not user_input or not user_input.strip():
        return TriageResult(problem_type=ProblemType.UNKNOWN, confidence=0.0)

    settings = get_settings()
    want_llm = settings.llm_enabled if use_llm is None else use_llm
    if want_llm:
        llm_result = _llm_triage(user_input)
        if llm_result is not None:
            return llm_result

    return rule_based_triage(user_input)
