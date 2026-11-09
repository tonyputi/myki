"""Diagnostics expose technical state, never raw account or tracker payloads."""

from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.myki.const import DOMAIN
from custom_components.myki.diagnostics import (
    async_get_config_entry_diagnostics,
    async_get_device_diagnostics,
)

TRACKER_ID = "private-tracker-id"
PRIVATE = "private-sentinel"


def make_entry(hass: HomeAssistant) -> tuple[MockConfigEntry, dict]:
    """Include private values in strings, nested payloads and dictionary keys."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"email": f"{PRIVATE}@example.com", "password": PRIVATE},
        options={"call_me_number": PRIVATE, "scan_interval": 60},
    )
    tracker = {
        "watch": {"id": TRACKER_ID, "nickname": PRIVATE},
        "app": {
            "current": {
                "battery": "85",
                "gsmSignalStrength": "99",
                "steps": {"todaySteps": 123},
                "position": {"latitude": 12.345678, "longitude": 23.456789},
                "wifi": [{"ssid": PRIVATE, "bssid": PRIVATE}],
                "baseStations": [{"cellId": PRIVATE}],
                "unexpected_vendor_field": PRIVATE,
            },
            "settings": {
                "online": "1",
                "fw": "G36W_test",
                "msisdn": PRIVATE,
                "nickname": PRIVATE,
                "timezone": json.dumps({"latitude": 12.345678, "value": PRIVATE}),
                **{f"safe_zone_{i}": json.dumps({"name": PRIVATE}) for i in (1, 3, 20)},
            },
            "commands": {
                **{f"{prefix}_{i}": PRIVATE for prefix in ("sos_phone", "whitelist", "phonebook") for i in (1, 3, 20)},
                "unexpected_vendor_field": PRIVATE,
            },
        },
        "events": [{"event_name": PRIVATE, "timestamp": "1234567890"}],
    }
    hass.data[DOMAIN] = {
        entry.entry_id: SimpleNamespace(data={TRACKER_ID: tracker}, last_update_success=True)
    }
    return entry, tracker


def assert_private_data_absent(result: dict) -> None:
    serialized = json.dumps(result)
    for private in (PRIVATE, TRACKER_ID, "12.345678", "23.456789", "1234567890"):
        assert private not in serialized


async def test_entry_diagnostics_are_private(hass: HomeAssistant) -> None:
    entry, tracker = make_entry(hass)
    original = deepcopy(tracker)

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert_private_data_absent(result)
    assert result["scan_interval"] == 60
    assert result["last_update_success"] is True
    assert result["watches"] == [{
        "model": "MyKi Spot", "battery": 85, "gsm_signal": 99,
        "steps_today": 123, "online": True,
    }]
    assert tracker == original


async def test_device_diagnostics_are_private(hass: HomeAssistant) -> None:
    entry, tracker = make_entry(hass)
    original = deepcopy(tracker)
    device = MagicMock(spec=DeviceEntry)
    device.identifiers = {("another_integration", "unrelated-id"), (DOMAIN, TRACKER_ID)}

    result = await async_get_device_diagnostics(hass, entry, device)

    assert_private_data_absent(result)
    assert result == {
        "model": "MyKi Spot", "battery": 85, "gsm_signal": 99,
        "steps_today": 123, "online": True,
    }
    assert tracker == original


async def test_unrelated_device_has_no_diagnostics(hass: HomeAssistant) -> None:
    entry, _ = make_entry(hass)
    device = MagicMock(spec=DeviceEntry)
    device.identifiers = {("another_integration", TRACKER_ID)}

    assert await async_get_device_diagnostics(hass, entry, device) == {}


async def test_removed_device_has_no_diagnostics(hass: HomeAssistant) -> None:
    entry, _ = make_entry(hass)
    device = MagicMock(spec=DeviceEntry)
    device.identifiers = {(DOMAIN, "removed-id")}

    assert await async_get_device_diagnostics(hass, entry, device) == {}
