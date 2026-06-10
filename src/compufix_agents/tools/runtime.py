"""Runtime (session) preferences for how sensitive tools behave.

Unlike :mod:`compufix_agents.config` (which reads immutable settings from the
environment), these preferences are chosen *interactively* by the user — for
example, from the Streamlit sidebar — and answer questions like:

    * Should packages be installed into a **virtual environment** (created if it
      doesn't exist), into the **current interpreter**, or **not at all** (for
      security)?
    * Should process listing/killing use **real** system data, or run in a
      **simulated** mode that never touches real processes?
    * Should network changes be **simulated**, or skipped entirely (**off**)?

The defaults intentionally match the historical tool behavior so that code and
tests that don't set preferences keep working unchanged. The UI defaults to the
*secure* options and writes the user's choice here before executing a plan.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

PackageInstallMode = Literal["current", "venv", "off"]
ProcessMode = Literal["real", "simulated"]
NetworkMode = Literal["simulated", "off"]


class RuntimePreferences(BaseModel):
    """User-chosen preferences that gate how sensitive tools execute."""

    # Where to install packages.
    #   "current" -> the running interpreter (sys.executable)  [legacy default]
    #   "venv"    -> a project virtual environment, created if missing
    #   "off"     -> do not install anything (report guidance instead)
    package_install_mode: PackageInstallMode = "current"

    # Virtual environment directory (relative to the project root, or absolute).
    venv_path: str = ".venv"

    # How process tools behave.
    #   "real"      -> real psutil listing; killing honors dry_run + config  [legacy]
    #   "simulated" -> simulated process list; killing is always dry-run
    process_mode: ProcessMode = "real"

    # How network changes behave.
    #   "simulated" -> simulate the switch in memory (MVP behavior)  [legacy]
    #   "off"       -> do not change the network at all
    network_mode: NetworkMode = "simulated"


# Process-global preferences. Mutable so the UI can update it between runs.
_PREFERENCES = RuntimePreferences()


def get_runtime_preferences() -> RuntimePreferences:
    """Return the current runtime preferences."""
    return _PREFERENCES


def set_runtime_preferences(**kwargs: object) -> RuntimePreferences:
    """Update one or more runtime preferences and return the new value.

    Args:
        **kwargs: Any subset of :class:`RuntimePreferences` fields.

    Returns:
        The updated :class:`RuntimePreferences`.
    """
    global _PREFERENCES
    _PREFERENCES = _PREFERENCES.model_copy(update=kwargs)
    return _PREFERENCES


def reset_runtime_preferences() -> RuntimePreferences:
    """Restore the default (legacy-compatible) preferences. Useful in tests."""
    global _PREFERENCES
    _PREFERENCES = RuntimePreferences()
    return _PREFERENCES
