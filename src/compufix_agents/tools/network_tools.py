"""Controlled network tools.

In this MVP all network state is **simulated**. No real OS network settings are
read or modified. ``switch_network`` mutates only the in-memory mock state.
"""

from __future__ import annotations

import copy

from compufix_agents.logging_config import get_logger
from compufix_agents.tools.runtime import get_runtime_preferences

logger = get_logger(__name__)


# --- Mocked network state ---------------------------------------------------

_CURRENT_NETWORK: dict = {
    "ssid": "Home_2.4G",
    "band": "2.4GHz",
    "signal_dbm": -48,
    "estimated_speed_mbps": 45,
}

_AVAILABLE_NETWORKS: list[dict] = [
    {
        "ssid": "Home_2.4G",
        "band": "2.4GHz",
        "signal_dbm": -48,
        "estimated_speed_mbps": 45,
    },
    {
        "ssid": "Home_5G",
        "band": "5GHz",
        "signal_dbm": -60,
        "estimated_speed_mbps": 220,
    },
]


def get_current_network() -> dict:
    """Return the (simulated) currently connected network.

    Read-only and safe; no approval required.
    """
    logger.info("get_current_network -> %s", _CURRENT_NETWORK["ssid"])
    return {"current_network": copy.deepcopy(_CURRENT_NETWORK)}


def list_available_networks() -> dict:
    """Return the (simulated) list of available networks.

    Read-only and safe; no approval required.
    """
    logger.info("list_available_networks -> %d networks", len(_AVAILABLE_NETWORKS))
    return {"available_networks": copy.deepcopy(_AVAILABLE_NETWORKS)}


def switch_network(ssid: str) -> dict:
    """Switch to the given SSID (simulated).

    This is a **sensitive** operation that requires user approval. In this MVP
    it only mutates the in-memory mock state and never touches the real OS.

    Args:
        ssid: The SSID to switch to.

    Returns:
        A dict with ``success``, ``message``, and (on success) the new
        ``current_network``.
    """
    global _CURRENT_NETWORK

    if get_runtime_preferences().network_mode == "off":
        logger.info("switch_network(%s) skipped (network_mode=off)", ssid)
        return {
            "success": True,
            "skipped": True,
            "message": (
                f"Network change skipped per your security preference. "
                f"To switch manually, connect to '{ssid}' from your OS Wi-Fi settings."
            ),
            "current_network": copy.deepcopy(_CURRENT_NETWORK),
        }

    target = next((n for n in _AVAILABLE_NETWORKS if n["ssid"] == ssid), None)
    if target is None:
        logger.warning("switch_network(%s) -> SSID not found", ssid)
        return {
            "success": False,
            "message": f"SSID '{ssid}' is not in the list of available networks.",
        }

    _CURRENT_NETWORK = copy.deepcopy(target)
    logger.info("switch_network -> now connected to %s (simulated)", ssid)
    return {
        "success": True,
        "message": f"Switched to '{ssid}' (simulated).",
        "current_network": copy.deepcopy(_CURRENT_NETWORK),
    }


def recommend_better_network() -> dict:
    """Recommend a faster network than the current one, if any.

    Helper used by the planner. Read-only and safe.

    Returns:
        A dict with ``recommended`` (the better network or ``None``) and a
        human-readable ``reason``.
    """
    current = _CURRENT_NETWORK
    # Candidates that are meaningfully faster and have usable signal (> -70 dBm).
    candidates = [
        n
        for n in _AVAILABLE_NETWORKS
        if n["ssid"] != current["ssid"]
        and n["estimated_speed_mbps"] > current["estimated_speed_mbps"]
        and n["signal_dbm"] > -70
    ]
    if not candidates:
        return {"recommended": None, "reason": "No faster usable network is available."}

    best = max(candidates, key=lambda n: n["estimated_speed_mbps"])
    reason = (
        f"{best['ssid']} ({best['band']}, ~{best['estimated_speed_mbps']} Mbps) is faster "
        f"than the current {current['ssid']} ({current['band']}, "
        f"~{current['estimated_speed_mbps']} Mbps)."
    )
    return {"recommended": copy.deepcopy(best), "reason": reason}


def _reset_mock_state() -> None:
    """Test helper: restore the default mocked network state."""
    global _CURRENT_NETWORK
    _CURRENT_NETWORK = {
        "ssid": "Home_2.4G",
        "band": "2.4GHz",
        "signal_dbm": -48,
        "estimated_speed_mbps": 45,
    }
