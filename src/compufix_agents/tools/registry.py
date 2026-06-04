"""Central registry of controlled tools.

This is the single source of truth for:
    * which tool names are allowed (the executor allowlist), and
    * which tools are *sensitive* (always require user approval).

Both the Planner/Safety agent and the Executor agent import from here so their
notions of "allowed" and "requires approval" can never drift apart.
"""

from __future__ import annotations

from collections.abc import Callable

from compufix_agents.schemas.plan import RiskLevel
from compufix_agents.tools.network_tools import (
    get_current_network,
    list_available_networks,
    switch_network,
)
from compufix_agents.tools.process_tools import kill_process, list_top_processes
from compufix_agents.tools.python_env_tools import (
    check_python_package,
    install_python_package,
    verify_python_import,
)

# name -> callable. The executor will ONLY ever call functions in this map.
TOOL_REGISTRY: dict[str, Callable[..., dict]] = {
    "check_python_package": check_python_package,
    "install_python_package": install_python_package,
    "verify_python_import": verify_python_import,
    "get_current_network": get_current_network,
    "list_available_networks": list_available_networks,
    "switch_network": switch_network,
    "list_top_processes": list_top_processes,
    "kill_process": kill_process,
}

# Sensitive tools that mutate state and therefore ALWAYS require approval.
SENSITIVE_TOOLS: frozenset[str] = frozenset(
    {
        "install_python_package",
        "switch_network",
        "kill_process",
    }
)

# Default risk level per tool.
TOOL_RISK: dict[str, RiskLevel] = {
    "check_python_package": RiskLevel.LOW,
    "install_python_package": RiskLevel.MEDIUM,
    "verify_python_import": RiskLevel.LOW,
    "get_current_network": RiskLevel.LOW,
    "list_available_networks": RiskLevel.LOW,
    "switch_network": RiskLevel.MEDIUM,
    "list_top_processes": RiskLevel.LOW,
    "kill_process": RiskLevel.HIGH,
}


def is_known_tool(name: str) -> bool:
    """Return True if ``name`` is an allowed controlled tool."""
    return name in TOOL_REGISTRY


def is_sensitive_tool(name: str) -> bool:
    """Return True if ``name`` requires user approval.

    Unknown tools are treated as sensitive (fail-safe): if the risk is unclear,
    approval is required.
    """
    if name not in TOOL_REGISTRY:
        return True
    return name in SENSITIVE_TOOLS


def risk_for(name: str) -> RiskLevel:
    """Return the default risk level for a tool (HIGH for unknown tools)."""
    return TOOL_RISK.get(name, RiskLevel.HIGH)
