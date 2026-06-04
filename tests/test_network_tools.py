"""Tests for the mocked network tools."""

from __future__ import annotations

import pytest

from compufix_agents.tools.network_tools import (
    _reset_mock_state,
    get_current_network,
    list_available_networks,
    recommend_better_network,
    switch_network,
)


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure each test starts from the default mocked network state."""
    _reset_mock_state()
    yield
    _reset_mock_state()


def test_get_current_network_default():
    current = get_current_network()["current_network"]
    assert current["ssid"] == "Home_2.4G"
    assert current["band"] == "2.4GHz"


def test_list_available_networks():
    nets = list_available_networks()["available_networks"]
    ssids = {n["ssid"] for n in nets}
    assert {"Home_2.4G", "Home_5G"} <= ssids


def test_recommend_better_network_picks_5g():
    rec = recommend_better_network()
    assert rec["recommended"] is not None
    assert rec["recommended"]["ssid"] == "Home_5G"


def test_switch_network_success():
    result = switch_network("Home_5G")
    assert result["success"] is True
    assert get_current_network()["current_network"]["ssid"] == "Home_5G"


def test_switch_network_unknown_ssid():
    result = switch_network("Nonexistent_SSID")
    assert result["success"] is False
    # State should remain unchanged.
    assert get_current_network()["current_network"]["ssid"] == "Home_2.4G"


def test_no_recommendation_when_already_on_fastest():
    switch_network("Home_5G")
    rec = recommend_better_network()
    assert rec["recommended"] is None
