"""Controlled process inspection tools.

Process **listing** uses real data via ``psutil`` and is read-only/safe.
Process **termination** is dry-run by default and is gated behind both a
configuration flag (``ALLOW_REAL_PROCESS_KILL``) and explicit user approval.
Critical/system processes are always protected.
"""

from __future__ import annotations

import os

import psutil

from compufix_agents.config import get_settings
from compufix_agents.logging_config import get_logger

logger = get_logger(__name__)

# Process names that must never be terminated by this tool.
PROTECTED_PROCESS_NAMES: frozenset[str] = frozenset(
    {
        # Unix / macOS
        "systemd",
        "init",
        "launchd",
        "kernel_task",
        "WindowServer",
        "loginwindow",
        # Windows
        "system",
        "csrss.exe",
        "wininit.exe",
        "winlogon.exe",
        "services.exe",
        "smss.exe",
        "lsass.exe",
    }
)


def _is_protected(name: str | None, pid: int) -> bool:
    """Return True if a process must not be killed."""
    if pid in (0, 1):
        return True
    if pid == os.getpid():  # never kill ourselves
        return True
    if name and name.lower() in {n.lower() for n in PROTECTED_PROCESS_NAMES}:
        return True
    return False


def list_top_processes(limit: int = 5) -> dict:
    """List the top processes by CPU usage (real data via psutil).

    Read-only and safe; no approval required.

    Args:
        limit: Maximum number of processes to return.

    Returns:
        A dict with a ``processes`` list, each item containing ``pid``,
        ``name``, ``cpu_percent``, ``memory_percent``, and ``protected``.
    """
    procs: list[psutil.Process] = list(psutil.process_iter(["pid", "name"]))

    # Prime cpu_percent; the first call returns 0.0, so we sample twice.
    for p in procs:
        try:
            p.cpu_percent(interval=None)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    psutil.cpu_percent(interval=0.1)  # brief interval to gather meaningful deltas

    rows: list[dict] = []
    for p in procs:
        try:
            with p.oneshot():
                name = p.name()
                rows.append(
                    {
                        "pid": p.pid,
                        "name": name,
                        "cpu_percent": round(p.cpu_percent(interval=None), 2),
                        "memory_percent": round(p.memory_percent(), 2),
                        "protected": _is_protected(name, p.pid),
                    }
                )
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    rows.sort(key=lambda r: (r["cpu_percent"], r["memory_percent"]), reverse=True)
    top = rows[: max(0, limit)]
    logger.info("list_top_processes(limit=%d) -> %d processes", limit, len(top))
    return {"processes": top}


def kill_process(pid: int, dry_run: bool = True) -> dict:
    """Terminate a process by PID.

    This is a **high-risk** operation. Safeguards:
        * ``dry_run`` defaults to ``True`` (reports without killing).
        * Real kills require ``ALLOW_REAL_PROCESS_KILL=true`` in the environment.
        * Critical/system processes are always protected.

    Args:
        pid: Target process id.
        dry_run: If True (default), do not actually terminate the process.

    Returns:
        A dict describing the outcome: ``pid``, ``name``, ``killed`` (bool),
        ``dry_run``, and ``message``.
    """
    settings = get_settings()

    try:
        proc = psutil.Process(pid)
        name = proc.name()
    except psutil.NoSuchProcess:
        logger.warning("kill_process(%s) -> no such process", pid)
        return {
            "pid": pid,
            "name": None,
            "killed": False,
            "dry_run": dry_run,
            "message": f"No process with pid {pid}.",
        }
    except psutil.AccessDenied:
        return {
            "pid": pid,
            "name": None,
            "killed": False,
            "dry_run": dry_run,
            "message": f"Access denied for pid {pid}.",
        }

    if _is_protected(name, pid):
        logger.warning("kill_process(%s, %s) blocked: protected process", pid, name)
        return {
            "pid": pid,
            "name": name,
            "killed": False,
            "dry_run": dry_run,
            "message": f"'{name}' (pid {pid}) is protected and cannot be killed.",
        }

    if dry_run:
        logger.info("kill_process(%s, %s) -> DRY RUN, not killed", pid, name)
        return {
            "pid": pid,
            "name": name,
            "killed": False,
            "dry_run": True,
            "message": f"[dry-run] Would terminate '{name}' (pid {pid}).",
        }

    if not settings.allow_real_process_kill:
        logger.warning("kill_process(%s) blocked: ALLOW_REAL_PROCESS_KILL is false", pid)
        return {
            "pid": pid,
            "name": name,
            "killed": False,
            "dry_run": False,
            "message": "Real process kill is disabled (ALLOW_REAL_PROCESS_KILL=false).",
        }

    try:
        proc.terminate()
        proc.wait(timeout=5)
        logger.info("kill_process(%s, %s) -> terminated", pid, name)
        return {
            "pid": pid,
            "name": name,
            "killed": True,
            "dry_run": False,
            "message": f"Terminated '{name}' (pid {pid}).",
        }
    except psutil.TimeoutExpired:
        return {
            "pid": pid,
            "name": name,
            "killed": False,
            "dry_run": False,
            "message": f"'{name}' (pid {pid}) did not terminate within timeout.",
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        return {
            "pid": pid,
            "name": name,
            "killed": False,
            "dry_run": False,
            "message": f"Failed to terminate pid {pid}: {exc}",
        }
