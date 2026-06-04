"""Tests for process tools (real listing, safe/dry-run killing)."""

from __future__ import annotations

import os

from compufix_agents.tools.process_tools import (
    _is_protected,
    kill_process,
    list_top_processes,
)


def test_list_top_processes_returns_limited_rows():
    result = list_top_processes(limit=3)
    assert "processes" in result
    assert len(result["processes"]) <= 3
    for proc in result["processes"]:
        assert {"pid", "name", "cpu_percent", "memory_percent", "protected"} <= proc.keys()


def test_kill_nonexistent_process():
    result = kill_process(99_999_999, dry_run=True)
    assert result["killed"] is False
    assert "No process" in result["message"]


def test_kill_is_dry_run_by_default():
    # Targeting our own process: protection kicks in OR dry-run, never killed.
    result = kill_process(os.getpid())
    assert result["killed"] is False


def test_protected_pids():
    assert _is_protected("launchd", 1) is True
    assert _is_protected("python", os.getpid()) is True
    assert _is_protected("systemd", 12345) is True
    assert _is_protected("my_app", 12345) is False


def test_kill_protected_process_blocked():
    result = kill_process(1, dry_run=False)
    assert result["killed"] is False
    assert "protected" in result["message"].lower()


def test_current_process_never_killed_even_real_mode():
    # Even with dry_run=False, our own process is protected.
    result = kill_process(os.getpid(), dry_run=False)
    assert result["killed"] is False
