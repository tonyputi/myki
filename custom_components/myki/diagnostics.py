"""Diagnostics containing only anonymous technical state."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import BASE_URL
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MykiConfigEntry
from .utils import get_battery, get_gsm_signal, get_model, get_steps_today, is_online


def _get_tracker_diagnostics(tracker: dict[str, Any]) -> dict[str, Any]:
    """Allowlist parsed values so new vendor fields cannot leak personal data."""
    app = tracker.get("app") or {}
    return {
        "model": get_model(app),
        "battery": get_battery(app),
        "gsm_signal": get_gsm_signal(app),
        "steps_today": get_steps_today(app),
        "online": is_online(app),
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MykiConfigEntry
) -> dict[str, Any]:
    """Return account diagnostics without credentials or device identifiers."""
    coordinator = entry.runtime_data
    return {
        "scan_interval": entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        "api": BASE_URL,
        "last_update_success": coordinator.last_update_success,
        "watches": [_get_tracker_diagnostics(tracker) for tracker in coordinator.data.values()],
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: MykiConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """Return anonymous diagnostics for the device's MyKi identifier only."""
    coordinator = entry.runtime_data
    watch_id = next((identifier for domain, identifier in device.identifiers if domain == DOMAIN), None)
    if watch_id not in coordinator.data:
        return {}
    return _get_tracker_diagnostics(coordinator.data[watch_id])
