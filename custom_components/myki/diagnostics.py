"""Diagnostics for the MyKi integration (sensitive fields redacted)."""

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .api import BASE_URL
from .coordinator import MykiCoordinator

_REDACT_KEYS = {
    "msisdn", "nickname",  # nickname is a child's name
    "wifi", "whitelist_1", "whitelist_2", "phonebook_1",
    "sos_phone_1", "sos_phone_2", "sos_phone_3", "center_number",
    "password", "fw",
}


def _redact(value: Any, keys: set[str] = _REDACT_KEYS) -> Any:
    if isinstance(value, dict):
        return {
            k: ("REDACTED" if k in keys else _redact(v, keys)) for k, v in value.items()
        }
    if isinstance(value, list):
        return [_redact(v, keys) for v in value]
    if isinstance(value, str) and "," in value and all(p.strip().isdigit() for p in value.split(",")):
        return "REDACTED"  # comma-separated phone lists under unexpected keys
    return value


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: MykiCoordinator = hass.data["myki"][entry.entry_id]
    return {
        "entry": {
            "email": entry.data.get("email"),
            "scan_interval": entry.options.get("scan_interval"),
        },
        "api": BASE_URL,
        "watches": _redact(coordinator.data),
    }


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    coordinator: MykiCoordinator = hass.data["myki"][entry.entry_id]
    watch_id = next(iter(device.identifiers))[1]
    return _redact(coordinator.data.get(watch_id, {}))
