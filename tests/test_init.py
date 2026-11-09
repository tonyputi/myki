"""Integration tests: config entry setup against a mocked MyKi cloud.

These would have caught the platform setup signature bug found in the field.
"""

from copy import deepcopy
from datetime import timedelta
import json
import time
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.myki.api import BASE_URL, MykiError
from custom_components.myki.const import DOMAIN

WATCH_ID = "3747004238"
NICK = "TestKid"

WATCHES = {"isok": True, "data": {"allw": [{"id": WATCH_ID, "nickname": NICK, "api": 2}]}}

ZONES = {
    "safe_zone_1": json.dumps(
        {"name": "Home", "lat": 35.92414, "lon": 14.45332, "radius": 0.212, "active": 1, "profile": 1}
    ),
    "safe_zone_2": json.dumps(
        {"name": "School", "lat": 35.90756, "lon": 14.49165, "radius": 0.127, "active": 1, "profile": 1}
    ),
}

APP_DATA = {
    "isok": True,
    "id": WATCH_ID,
    "data": {
        "current": {
            "takenat": "2026-11-07 12:37:29",
            "position": {"type": "WiFi", "latitude": 35.92417, "longitude": 14.45502, "accuracy": 25},
            "gpsSatelites": 3,
            "wifi": [{"ssid": "a"}, {"ssid": "b"}],
            "baseStations": 4,
            "battery": "85", "RTT_secondsLeft": "0",
            "steps": {"allSteps": 1353915, "todaySteps": 4321},
        },
        "settings": {"online": "1", "nickname": NICK, "msisdn": "+35679060465", "mcc_mnc": "27821", "last_data_package": str(int(time.time())), **ZONES},
        "commands": {"sos_phone_1": "0035679248232", "whitelist_1": "0035679248232,0035699859524", "volume_ring": "4", "volume_call": "6"},
    },
}


def _mock_cloud(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE_URL}/watch", json=WATCHES)
    aioclient_mock.get(f"{BASE_URL}/watch/app-data?id={WATCH_ID}", json=APP_DATA)
    aioclient_mock.get(
        f"{BASE_URL}/watch/history/events?id={WATCH_ID}",
        json={"isok": True, "data": {"events": [
            {"event_name": "low_battery", "timestamp": "1794000000"},
            {"event_name": "sos_alarm", "timestamp": "1794010000"},
        ]}},
    )


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.config_entry is entry
    assert DOMAIN not in hass.data

    tracker = hass.states.get(f"device_tracker.{NICK.lower()}")
    assert tracker is not None
    assert tracker.attributes["latitude"] == 35.92417
    assert tracker.attributes["longitude"] == 14.45502
    assert tracker.attributes["zone"] == "Home"

    assert hass.states.get(f"sensor.{NICK.lower()}_battery").state == "85"
    assert hass.states.get(f"sensor.{NICK.lower()}_zone").state == "Home"
    assert hass.states.get(f"sensor.{NICK.lower()}_steps_today").state == "4321"
    assert hass.states.get(f"binary_sensor.{NICK.lower()}_online").state == "on"


async def test_find_service(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})

    await hass.services.async_call(
        DOMAIN, "find", {"entity_id": f"device_tracker.{NICK.lower()}"}, blocking=True
    )
    urls = [str(url) for method, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/find" in url for url in urls)


async def test_unload(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert not hasattr(entry, "runtime_data")


async def test_failed_unload_keeps_runtime_data(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    with patch("homeassistant.config_entries.ConfigEntries.async_unload_platforms", return_value=False):
        assert not await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.FAILED_UNLOAD
    assert entry.runtime_data is coordinator
    assert coordinator.data[WATCH_ID]["watch"]["nickname"] == NICK


async def test_options_reload_replaces_coordinator(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    previous = entry.runtime_data
    hass.config_entries.async_update_entry(entry, options={"scan_interval": 120})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not previous
    assert entry.runtime_data.config_entry is entry
    assert entry.runtime_data.update_interval == timedelta(seconds=120)
    assert hass.states.get(f"sensor.{NICK.lower()}_battery").state == "85"


async def test_failed_first_refresh_has_no_runtime_data(hass: HomeAssistant, aioclient_mock) -> None:
    with patch("custom_components.myki.api.MykiClient.watches", side_effect=MykiError("offline")):
        entry = await _setup(hass, aioclient_mock)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hasattr(entry, "runtime_data")


async def test_device_page_entities(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        options={"call_me_number": "+35679060465"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})
    aioclient_mock.get(
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=%2B35679060465", json={"isok": True}
    )
    aioclient_mock.get(
        f"{BASE_URL}/watch/callvolset?id={WATCH_ID}&volume=5", json={"isok": True}
    )
    # buttons exist; call_me available only with the option set
    assert hass.states.get(f"button.{NICK.lower()}_find").state == "unknown"
    assert hass.states.get(f"button.{NICK.lower()}_call_me").state == "unknown"

    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{NICK.lower()}_find"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{NICK.lower()}_call_me"}, blocking=True
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/find" in u for u in urls)
    assert any("watch/call" in u and "phone=%2B35679060465" in u for u in urls)

    # volume sliders reflect the payload and can be set
    assert hass.states.get(f"number.{NICK.lower()}_ring_volume").state == "4"
    assert hass.states.get(f"number.{NICK.lower()}_call_volume").state == "6"
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{NICK.lower()}_call_volume", "value": 5},
        blocking=True,
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("callvolset" in u and "volume=5" in u for u in urls)


async def test_rotated_events_produce_individual_state_changes(hass: HomeAssistant, aioclient_mock) -> None:
    """Two new SOS records must each reach HA automations, even after rotation."""
    entry = await _setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    entity_id = f"event.{NICK.lower()}_events"
    changes = []

    @callback
    def record_change(event):
        changes.append(event.data["new_state"])

    unsubscribe = async_track_state_change_event(hass, [entity_id], record_change)
    try:
        data = {WATCH_ID: {
            **coordinator.data[WATCH_ID],
            "events": [
                {"event_name": "sos_alarm", "timestamp": "1794010001"},
                {"event_name": "sos_alarm", "timestamp": "1794010002"},
            ],
        }}
        coordinator.async_set_updated_data(data)
        await hass.async_block_till_done()
        assert [state.attributes["timestamp"] for state in changes] == ["1794010001", "1794010002"]
        assert all(state.attributes["event_type"] == "sos_alarm" for state in changes)

        coordinator.async_set_updated_data(data)
        await hass.async_block_till_done()
        assert len(changes) == 2
    finally:
        unsubscribe()


async def test_p3b_entities(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(f"{BASE_URL}/watch/rtt?id={WATCH_ID}&duration=10", json={"isok": True})

    kid = NICK.lower()
    ev = hass.states.get(f"event.{kid}_events")
    assert ev is not None
    assert "sos_alarm" in ev.attributes["event_types"]
    assert "low_battery" in ev.attributes["event_types"]

    assert hass.states.get(f"sensor.{kid}_live_tracking_seconds_left").state == "0"
    assert hass.states.get(f"binary_sensor.{kid}_fresh_data").state == "on"

    tracker = hass.states.get(f"device_tracker.{kid}")
    assert tracker.attributes["phone"] is not None

    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{kid}_live_tracking"}, blocking=True
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/rtt" in u and "duration=10" in u for u in urls)


async def test_diagnostic_sensors(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    kid = NICK.lower()
    assert hass.states.get(f"sensor.{kid}_gps_satellites").state == "3"
    assert hass.states.get(f"sensor.{kid}_wifi_networks").state == "2"
    assert hass.states.get(f"sensor.{kid}_cell_towers").state == "4"


async def test_make_call_service(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=%2B35679060465", json={"isok": True}
    )
    await hass.services.async_call(
        "myki",
        "make_call",
        {"entity_id": f"device_tracker.{NICK.lower()}", "phone": "+35679060465"},
        blocking=True,
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/call" in u and "phone=%2B35679060465" in u for u in urls)


async def test_unique_ids_are_stable(hass: HomeAssistant, aioclient_mock) -> None:
    """unique_id must never change: HA would orphan the old entities."""
    from homeassistant.helpers import entity_registry as er

    await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    uids = {
        e.unique_id
        for e in registry.entities.values()
        if e.platform == "myki" and e.domain == "sensor"
    }
    assert f"{WATCH_ID}_gsm_signal" in uids
    assert f"{WATCH_ID}_rtt_seconds_left" in uids
    assert f"{WATCH_ID}_gps_satellites" not in uids  # satellites keep the payload key


async def test_invalid_safe_zone_is_unknown_and_recovers(hass: HomeAssistant, aioclient_mock) -> None:
    """A malformed active zone must not generate a Home -> away transition."""
    entry = await _setup(hass, aioclient_mock)
    coordinator = entry.runtime_data
    original = deepcopy(coordinator.data)
    entity_id = f"sensor.{NICK.lower()}_zone"
    assert hass.states.get(entity_id).state == "Home"

    data = deepcopy(original)
    data[WATCH_ID]["app"]["settings"]["safe_zone_1"] = json.dumps({"active": 1})
    coordinator.async_set_updated_data(data)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state.state == "unknown"
    assert state.attributes["options"] == ["away"]
    assert not any(key.startswith("distance_to_") for key in state.attributes)
    tracker = hass.states.get(f"device_tracker.{NICK.lower()}")
    assert tracker.attributes["latitude"] == 35.92417
    assert tracker.attributes["zone"] is None

    coordinator.async_set_updated_data(original)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "Home"
