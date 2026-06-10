"""Tests for runtime security preferences and preference-aware tools."""

from __future__ import annotations

import sys

import pytest

from compufix_agents.tools.network_tools import _reset_mock_state, switch_network
from compufix_agents.tools.process_tools import kill_process, list_top_processes
from compufix_agents.tools.python_env_tools import (
    ensure_virtualenv,
    install_python_package,
    verify_python_import,
)
from compufix_agents.tools.runtime import (
    RuntimePreferences,
    get_runtime_preferences,
    reset_runtime_preferences,
    set_runtime_preferences,
)


@pytest.fixture(autouse=True)
def _reset_prefs():
    reset_runtime_preferences()
    _reset_mock_state()
    yield
    reset_runtime_preferences()
    _reset_mock_state()


def test_defaults_match_legacy_behavior():
    prefs = get_runtime_preferences()
    assert prefs.package_install_mode == "current"
    assert prefs.process_mode == "real"
    assert prefs.network_mode == "simulated"


def test_set_and_reset_preferences():
    set_runtime_preferences(process_mode="simulated", network_mode="off")
    prefs = get_runtime_preferences()
    assert prefs.process_mode == "simulated"
    assert prefs.network_mode == "off"
    reset_runtime_preferences()
    assert get_runtime_preferences() == RuntimePreferences()


# --- Package installation ---------------------------------------------------


def test_install_off_mode_skips_without_installing():
    set_runtime_preferences(package_install_mode="off")
    result = install_python_package("this-package-should-never-be-installed")
    assert result["success"] is True
    assert result["skipped"] is True
    assert result["interpreter"] is None
    assert "skipped" in result["message"].lower()


def test_install_off_via_target_override():
    # Even with the default "current" preference, an explicit target wins.
    result = install_python_package("whatever", target="off")
    assert result["skipped"] is True


def test_ensure_virtualenv_creates_and_reuses(tmp_path):
    venv_dir = tmp_path / "venv_under_test"
    first = ensure_virtualenv(str(venv_dir))
    assert first["success"] is True
    assert first["created"] is True
    assert venv_dir.exists()

    second = ensure_virtualenv(str(venv_dir))
    assert second["success"] is True
    assert second["created"] is False


def test_install_venv_mode_uses_venv_interpreter(tmp_path, monkeypatch):
    venv_dir = tmp_path / "venv_install"
    # Create the venv for real first, so the mocked subprocess below only affects
    # the pip install call (not venv creation).
    ensure_virtualenv(str(venv_dir))
    set_runtime_preferences(package_install_mode="venv", venv_path=str(venv_dir))

    captured: dict = {}

    def fake_run(cmd, *args, **kwargs):  # noqa: ANN001
        captured["cmd"] = cmd

        class _Proc:
            returncode = 0
            stdout = "ok"
            stderr = ""

        return _Proc()

    # The real venv is created (offline), but the pip install is mocked so the
    # test never hits the network.
    monkeypatch.setattr("compufix_agents.tools.python_env_tools.subprocess.run", fake_run)
    result = install_python_package("somepkg")

    assert result["success"] is True
    assert result["interpreter"] != sys.executable
    assert str(venv_dir) in result["interpreter"]
    assert captured["cmd"][0] == result["interpreter"]


def test_verify_import_targets_venv_when_selected(tmp_path):
    venv_dir = tmp_path / "venv_verify"
    ensure_virtualenv(str(venv_dir))
    set_runtime_preferences(package_install_mode="venv", venv_path=str(venv_dir))

    result = verify_python_import("sys")
    assert result["importable"] is True
    assert str(venv_dir) in result["interpreter"]


# --- Processes --------------------------------------------------------------


def test_simulated_process_listing_does_not_touch_real_system():
    set_runtime_preferences(process_mode="simulated")
    result = list_top_processes(limit=3)
    assert result.get("simulated") is True
    assert len(result["processes"]) == 3
    for proc in result["processes"]:
        assert {"pid", "name", "cpu_percent", "memory_percent", "protected"} <= proc.keys()


def test_simulated_kill_is_never_real():
    set_runtime_preferences(process_mode="simulated")
    result = kill_process(4242)
    assert result["killed"] is False
    assert result.get("simulated") is True


# --- Network ----------------------------------------------------------------


def test_network_off_mode_skips_switch():
    set_runtime_preferences(network_mode="off")
    result = switch_network("Home_5G")
    assert result.get("skipped") is True
    # The simulated current network must remain unchanged.
    assert result["current_network"]["ssid"] == "Home_2.4G"


def test_network_simulated_still_switches():
    set_runtime_preferences(network_mode="simulated")
    result = switch_network("Home_5G")
    assert result["success"] is True
    assert result["current_network"]["ssid"] == "Home_5G"
