"""Controlled, safe tools the executor agent is allowed to call."""

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

__all__ = [
    "check_python_package",
    "install_python_package",
    "verify_python_import",
    "get_current_network",
    "list_available_networks",
    "switch_network",
    "list_top_processes",
    "kill_process",
]
