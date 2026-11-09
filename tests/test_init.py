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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_track_state_change_event
import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.myki.api import BASE_URL, MykiError
from custom_components.myki.const import DOMAIN

WATCH_ID = "test-tracker"
NICK = "TestKid"

WATCHES = {"isok": True, "data": {"allw": [{"id": WATCH_ID, "nickname": NICK, "api": 2}]}}

ZONES = {
    "safe_zone_1": json.dumps(
        {"name": "Home", "lat": 10.0, "lon": 20.0, "radius": 0.212, "active": 1, "profile": 1}
    ),
    "safe_zone_2": json.dumps(
        {"name": "School", "lat": 10.03, "lon": 20.02, "radius": 0.127, "active": 1, "profile": 1}
    ),
}

APP_DATA = {
    "isok": True,
    "id": WATCH_ID,
    "data": {
        "current": {
            "takenat": "2026-11-07 12:37:29",
            "position": {"type": "WiFi", "latitude": 10.0001, "longitude": 20.0001, "accuracy": 25},
            "gpsSatelites": 3,
            "wifi": [{"ssid": "a"}, {"ssid": "b"}],
            "baseStations": 4,
            "battery": "85", "RTT_secondsLeft": "0",
            "steps": {"allSteps": 1353915, "todaySteps": 4321},
        },
        "settings": {"online": "1", "nickname": NICK, "msisdn": "+15555550100", "mcc_mnc": "27821", "last_data_package": str(int(time.time())), **ZONES},
        "commands": {"sos_phone_1": "0015555550100", "whitelist_1": "0015555550100,0015555550101", "volume_ring": "4", "volume_call": "6"},
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
    assert tracker.attributes["latitude"] == 10.0001
    assert tracker.attributes["longitude"] == 20.0001
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
        options={"call_me_number": "+15555550100"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})
    aioclient_mock.get(
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=%2B15555550100", json={"isok": True}
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
    assert any("watch/call" in u and "phone=%2B15555550100" in u for u in urls)

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
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=%2B15555550100", json={"isok": True}
    )
    await hass.services.async_call(
        "myki",
        "make_call",
        {"entity_id": f"device_tracker.{NICK.lower()}", "phone": "+15555550100"},
        blocking=True,
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/call" in u and "phone=%2B15555550100" in u for u in urls)


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
    assert tracker.attributes["latitude"] == 10.0001
    assert tracker.attributes["zone"] is None

    coordinator.async_set_updated_data(original)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "Home"


@pytest.mark.parametrize("button,method", [
    ("find", "find"), ("call_me", "make_call"), ("live_tracking", "start_rtt"),
])
async def test_failed_button_is_reported(hass: HomeAssistant, aioclient_mock, button, method):
    entry = await _setup(hass, aioclient_mock)
    hass.config_entries.async_update_entry(entry, options={"call_me_number": "+15555550100"})
    await hass.async_block_till_done()
    with patch.object(entry.runtime_data.client, method, side_effect=MykiError("offline")):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "button", "press", {"entity_id": f"button.{NICK.lower()}_{button}"}, blocking=True
            )


@pytest.mark.parametrize("control,method", [
    ("ring_volume", "set_ring_volume"), ("call_volume", "set_call_volume"),
])
async def test_failed_volume_write_keeps_confirmed_value(hass: HomeAssistant, aioclient_mock, control, method):
    entry = await _setup(hass, aioclient_mock)
    entity_id = f"number.{NICK.lower()}_{control}"
    previous = hass.states.get(entity_id).state
    with patch.object(entry.runtime_data.client, method, side_effect=MykiError("offline")):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(
                "number", "set_value", {"entity_id": entity_id, "value": 3}, blocking=True
            )
    assert hass.states.get(entity_id).state == previous


@pytest.mark.parametrize("control,method,key", [
    ("ring_volume", "set_ring_volume", "volume_ring"),
    ("call_volume", "set_call_volume", "volume_call"),
])
async def test_volume_displays_cloud_readback(hass: HomeAssistant, aioclient_mock, control, method, key):
    entry = await _setup(hass, aioclient_mock)
    cloud_data = deepcopy(APP_DATA["data"])
    cloud_data["commands"][key] = "2"
    with (
        patch.object(entry.runtime_data.client, method) as write,
        patch.object(entry.runtime_data.client, "app_data", return_value=cloud_data),
    ):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": f"number.{NICK.lower()}_{control}", "value": 3}, blocking=True,
        )
        await hass.async_block_till_done()
        write.assert_awaited_once_with(WATCH_ID, 3)
    assert hass.states.get(f"number.{NICK.lower()}_{control}").state == "2"


@pytest.mark.parametrize("service,method", [("find", "find"), ("make_call", "make_call")])
async def test_failed_tracker_action(hass: HomeAssistant, aioclient_mock, caplog, service, method):
    entry = await _setup(hass, aioclient_mock)
    data = {"entity_id": f"device_tracker.{NICK.lower()}"}
    if service == "make_call":
        data["phone"] = "+15555550100"
    with patch.object(entry.runtime_data.client, method, side_effect=MykiError("offline")):
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert all(
        "+15555550100" not in record.getMessage()
        for record in caplog.records if record.name.startswith("custom_components.myki")
    )


async def test_action_targets_only_selected_tracker(hass: HomeAssistant, aioclient_mock):
    other = {"id": "other-tracker", "nickname": "Other tracker"}
    aioclient_mock.get(f"{BASE_URL}/watch/app-data?id=other-tracker", json=APP_DATA)
    aioclient_mock.get(f"{BASE_URL}/watch/history/events?id=other-tracker", json={"isok": True})
    with patch("custom_components.myki.api.MykiClient.watches", return_value=[WATCHES["data"]["allw"][0], other]):
        entry = await _setup(hass, aioclient_mock)
    with patch.object(entry.runtime_data.client, "find") as find:
        await hass.services.async_call(
            DOMAIN, "find", {"entity_id": f"device_tracker.{NICK.lower()}"}, blocking=True
        )
        find.assert_awaited_once_with(WATCH_ID)


async def test_reload_preserves_user_entity_customization(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    old_id = f"sensor.{NICK.lower()}_gsm_signal"
    unique_id = registry.async_get(old_id).unique_id
    registry.async_update_entity(old_id, new_entity_id="sensor.custom_signal", name="Custom signal")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    restored = registry.async_get("sensor.custom_signal")
    assert restored.unique_id == unique_id
    assert restored.name == "Custom signal"
    assert hass.states.get("sensor.custom_signal") is not None


async def test_removed_tracker_makes_all_entities_unavailable(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    entry.runtime_data.async_set_updated_data({})
    await hass.async_block_till_done()
    assert all(hass.states.get(entity.entity_id).state == "unavailable" for entity in entities)


@pytest.mark.parametrize("offset,expected", [(-10, "on"), (-1801, "off"), (10, "off"), (None, "unknown")])
async def test_fresh_data_requires_a_recent_past_timestamp(hass: HomeAssistant, aioclient_mock, offset, expected):
    entry = await _setup(hass, aioclient_mock)
    data = deepcopy(entry.runtime_data.data)
    data[WATCH_ID]["app"]["settings"]["last_data_package"] = None if offset is None else time.time() + offset
    entry.runtime_data.async_set_updated_data(data)
    await hass.async_block_till_done()
    assert hass.states.get(f"binary_sensor.{NICK.lower()}_fresh_data").state == expected
