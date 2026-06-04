"""Tests for Python environment tools (read-only paths)."""

from __future__ import annotations

import sys

from compufix_agents.tools.python_env_tools import (
    check_python_package,
    map_import_to_package,
    verify_python_import,
)


def test_check_python_package_installed():
    result = check_python_package("json")
    assert result["installed"] is True
    assert result["interpreter"] == sys.executable


def test_check_python_package_missing():
    result = check_python_package("definitely_not_a_real_module_xyz")
    assert result["installed"] is False


def test_check_python_package_resolves_via_mapping():
    # 'sys' is a builtin and importable; mapping identity should hold.
    assert map_import_to_package("sys") == "sys"


def test_verify_python_import_success():
    result = verify_python_import("json")
    assert result["importable"] is True
    assert result["error"] == ""


def test_verify_python_import_failure():
    result = verify_python_import("definitely_not_a_real_module_xyz")
    assert result["importable"] is False
    assert result["error"]
