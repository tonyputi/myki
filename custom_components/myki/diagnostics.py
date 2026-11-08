"""Diagnostics for the MyKi integration (sensitive fields redacted)."""

import re
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.redact import async_redact_data

from .api import BASE_URL
from .const import CONF_SCAN_INTERVAL, DOMAIN
from .coordinator import MykiCoordinator

# keys matched at any depth; patterns for numbered siblings
_TO_REDACT: set[str | re.Pattern[str]] = {
    "email",
    "password",
    "msisdn",
    "nickname",  # a child's name
    "phone",
    "latitude",
    "longitude",
    "wifi",
    "fw",
    re.compile(r"^sos_phone_\d+$"),
    re.compile(r"^whitelist_\d+$"),
    re.compile(r"^phonebook_\d+$"),
    re.compile(r"^safe_zone_\d+$"),
    "center_number",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    return async_redact_data(
        {
            "email": entry.data.get("email"),
            "scan_interval": entry.options.get(CONF_SCAN_INTERVAL),
            "api": BASE_URL,
            "watches": coordinator.data,
        },
        _TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    watch_id = next(iter(device.identifiers))[1]
    return async_redact_data(coordinator.data.get(watch_id, {}), _TO_REDACT)
