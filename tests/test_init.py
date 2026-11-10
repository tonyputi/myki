"""Integration tests: config entry setup against a mocked MyKi cloud.

These would have caught the platform setup signature bug found in the field.
"""

from asyncio import gather, sleep
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


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, *, legacy_controls=True) -> MockConfigEntry:
    """Existing control tests explicitly opt in to the disabled compatibility entities."""
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if legacy_controls:
        registry = er.async_get(hass)
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
                registry.async_update_entity(entity.entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
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
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})
    aioclient_mock.get(
        f"{BASE_URL}/watch/callvolset?id={WATCH_ID}&volume=5", json={"isok": True}
    )
    assert hass.states.get(f"button.{NICK.lower()}_find").state == "unknown"
    assert hass.states.get(f"button.{NICK.lower()}_call_me") is None
    assert hass.states.get(f"select.{NICK.lower()}_call_contact") is None

    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{NICK.lower()}_find"}, blocking=True
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/find" in u for u in urls)

    # Tracker settings are edited in Configure, not duplicated on the device page.
    registry = er.async_get(hass)
    for control in ("ring_volume", "call_volume"):
        entity_id = f"number.{NICK.lower()}_{control}"
        assert hass.states.get(entity_id) is None
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(f"switch.{NICK.lower()}_flashlight") is not None
    assert entry.minor_version == 2
    assert not any("callvolset" in str(url) for _, url, *_ in aioclient_mock.mock_calls)


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
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=0015555550100", json={"isok": True}
    )
    await hass.services.async_call(
        "myki",
        "make_call",
        {"entity_id": f"device_tracker.{NICK.lower()}", "phone": "+15555550100"},
        blocking=True,
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/call" in u and "phone=0015555550100" in u for u in urls)


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
    ("find", "find"), ("live_tracking", "start_rtt"),
])
async def test_failed_button_is_reported(hass: HomeAssistant, aioclient_mock, button, method):
    entry = await _setup(hass, aioclient_mock)
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
        patch.object(entry.runtime_data.client, "app_data", side_effect=[deepcopy(APP_DATA["data"]), cloud_data]),
    ):
        with pytest.raises(HomeAssistantError, match="not confirmed"):
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



async def test_shared_contacts_follow_app_refresh(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    entity_id = f"text.{NICK.lower()}_sos_1"
    assert hass.states.get(entity_id).state == "0015555550100"
    changed = deepcopy(APP_DATA["data"])
    changed["commands"]["sos_phone_1"] = "0015555550103"
    with patch.object(entry.runtime_data.client, "app_data", return_value=changed):
        await entry.runtime_data.async_request_refresh()
    assert hass.states.get(entity_id).state == "0015555550103"


async def test_edit_sos_contact_verifies_cloud_readback(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    confirmed = deepcopy(APP_DATA["data"])
    confirmed["commands"]["sos_phone_1"] = "0015555550103"
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=[APP_DATA["data"], confirmed]),
        patch.object(entry.runtime_data.client, "set_sos_number") as write,
    ):
        await hass.services.async_call("text", "set_value", {
            "entity_id": f"text.{NICK.lower()}_sos_1", "value": "+15555550103",
        }, blocking=True)
        write.assert_awaited_once_with(WATCH_ID, 1, "0015555550103")
    assert hass.states.get(f"text.{NICK.lower()}_sos_1").state == "0015555550103"


async def test_whitelist_preserves_hidden_slots_and_latest_siblings(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    fresh = deepcopy(APP_DATA["data"])
    fresh["commands"]["whitelist_2"] = "0015555550104,,0015555550106,,0015555550108"
    confirmed = deepcopy(fresh)
    confirmed["commands"]["whitelist_2"] = "0015555550104,0015555550105,0015555550106,,0015555550108"
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=[fresh, confirmed]),
        patch.object(entry.runtime_data.client, "set_whitelist") as write,
    ):
        await hass.services.async_call("text", "set_value", {
            "entity_id": f"text.{NICK.lower()}_whitelist_7", "value": "+15555550105",
        }, blocking=True)
        write.assert_awaited_once_with(WATCH_ID, 2, [
            "0015555550104", "0015555550105", "0015555550106", "", "0015555550108",
        ])
    assert hass.states.get(f"text.{NICK.lower()}_whitelist_7").state == "0015555550105"


@pytest.mark.parametrize("failure", ["offline", "rejected", "changed", "unconfirmed", "missing_group", "malformed"])
async def test_contact_failures_never_claim_success(hass: HomeAssistant, aioclient_mock, failure):
    entry = await _setup(hass, aioclient_mock)
    fresh = deepcopy(APP_DATA["data"])
    slot = "sos_1"
    expected = "0015555550100"
    if failure == "offline":
        fresh["settings"]["online"] = "0"
    elif failure == "changed":
        fresh["commands"]["sos_phone_1"] = "0015555550109"
    elif failure == "missing_group":
        slot, expected = "whitelist_7", ""
    elif failure == "malformed":
        fresh["commands"]["whitelist_1"] = "invalid"
    with (
        patch.object(entry.runtime_data.client, "app_data", return_value=fresh),
        patch.object(entry.runtime_data.client, "set_sos_number", side_effect=MykiError("rejected") if failure == "rejected" else None) as sos,
        patch.object(entry.runtime_data.client, "set_whitelist") as whitelist,
    ):
        with pytest.raises(MykiError):
            await entry.runtime_data.async_set_contact(WATCH_ID, slot, "+15555550103", expected)
        if failure not in ("unconfirmed", "rejected"):
            sos.assert_not_awaited()
        whitelist.assert_not_awaited()
    assert hass.states.get(f"text.{NICK.lower()}_sos_1").state != "0015555550103"


async def test_equivalent_contact_edit_does_not_rewrite_storage(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    with patch.object(entry.runtime_data.client, "set_sos_number") as write:
        await entry.runtime_data.async_set_contact(WATCH_ID, "sos_1", "+15555550100", "0015555550100")
        write.assert_not_awaited()


async def test_call_slot_resolves_current_cloud_value(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    changed = deepcopy(APP_DATA["data"])
    changed["commands"]["sos_phone_1"] = "0015555550103"
    with (
        patch.object(entry.runtime_data.client, "app_data", return_value=changed),
        patch.object(entry.runtime_data.client, "make_call") as call,
    ):
        await hass.services.async_call(DOMAIN, "make_call", {
            "entity_id": f"device_tracker.{NICK.lower()}", "contact": "sos_1",
        }, blocking=True)
        call.assert_awaited_once_with(WATCH_ID, "0015555550103")


@pytest.mark.parametrize("target", [{"contact": "sos_3"}, {"phone": "+15555550109"}, {}])
async def test_call_rejects_empty_or_unshared_contacts(hass: HomeAssistant, aioclient_mock, target):
    entry = await _setup(hass, aioclient_mock)
    with patch.object(entry.runtime_data.client, "make_call") as call:
        with pytest.raises(HomeAssistantError):
            await hass.services.async_call(DOMAIN, "make_call", {
                "entity_id": f"device_tracker.{NICK.lower()}", **target,
            }, blocking=True)
        call.assert_not_awaited()


@pytest.mark.parametrize("retired_options", [
    {},
    {"call_me_number": "+15555550100"},
    {"call_contacts": {WATCH_ID: "sos_1"}},
    {"call_me_number": "+15555550109", "call_contacts": {WATCH_ID: "sos_2"}},
])
async def test_retired_call_controls_removed_without_cloud_writes(hass: HomeAssistant, aioclient_mock, retired_options):
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN, data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        options={"scan_interval": 120, **retired_options},
    )
    entry.add_to_hass(hass)
    other_entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id="other")
    other_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    retired = [
        registry.async_get_or_create(
            domain, DOMAIN, f"{wid}_{suffix}", config_entry=entry,
            suggested_object_id=f"custom_{wid}_{suffix}", disabled_by=er.RegistryEntryDisabler.USER,
        )
        for wid in (WATCH_ID, "removed-tracker")
        for domain, suffix in (("button", "call_me"), ("select", "call_contact"))
    ]
    other = registry.async_get_or_create(
        "select", DOMAIN, "other_call_contact", config_entry=other_entry,
    )
    contact = registry.async_get_or_create(
        "text", DOMAIN, f"{WATCH_ID}_sos_1", config_entry=entry,
    )
    registry.async_update_entity(contact.entity_id, name="My SOS contact")
    with (
        patch("custom_components.myki.api.MykiClient.set_sos_number") as sos,
        patch("custom_components.myki.api.MykiClient.set_whitelist") as whitelist,
        patch("custom_components.myki.api.MykiClient.make_call") as call,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.LOADED
        assert entry.options == {"scan_interval": 120}
        assert all(registry.async_get(entity.entity_id) is None for entity in retired)
        assert registry.async_get(other.entity_id) is other
        assert registry.async_get(contact.entity_id).name == "My SOS contact"
        assert entry.runtime_data.data[WATCH_ID]["app"]["commands"] == APP_DATA["data"]["commands"]
        assert hass.states.get(f"select.{NICK.lower()}_call_contact") is None
        assert hass.states.get(f"button.{NICK.lower()}_call_me") is None
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.options == {"scan_interval": 120}
        assert registry.async_get(contact.entity_id).name == "My SOS contact"
        sos.assert_not_awaited()
        whitelist.assert_not_awaited()
        call.assert_not_awaited()


async def test_contact_writes_are_serialized_without_losing_siblings(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    cloud = deepcopy(APP_DATA["data"])
    cloud["commands"]["whitelist_1"] = ",,,,"
    active = maximum = 0

    async def read(wid):
        return deepcopy(cloud)

    async def write(wid, group, phones):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await sleep(0)  # Allow the second edit to contend for the lock.
        cloud["commands"][f"whitelist_{group}"] = ",".join(phones)
        active -= 1

    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=read),
        patch.object(entry.runtime_data.client, "set_whitelist", side_effect=write),
    ):
        await gather(
            entry.runtime_data.async_set_contact(WATCH_ID, "whitelist_1", "0015555550104", ""),
            entry.runtime_data.async_set_contact(WATCH_ID, "whitelist_2", "0015555550105", ""),
        )
    assert maximum == 1
    assert cloud["commands"]["whitelist_1"] == "0015555550104,0015555550105,,,"


async def test_readback_checks_untouched_whitelist_entries_too(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    confirmed = deepcopy(APP_DATA["data"])
    confirmed["commands"]["whitelist_1"] = "0015555550104,0015555550109"
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=[APP_DATA["data"], confirmed]),
        patch.object(entry.runtime_data.client, "set_whitelist"),
    ):
        with pytest.raises(MykiError, match="not confirmed"):
            await entry.runtime_data.async_set_contact(WATCH_ID, "whitelist_1", "0015555550104", "0015555550100")
    assert hass.states.get(f"text.{NICK.lower()}_whitelist_2").state == "0015555550109"


async def test_contact_write_can_clear_a_slot(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    confirmed = deepcopy(APP_DATA["data"])
    confirmed["commands"]["sos_phone_1"] = ""
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=[APP_DATA["data"], confirmed]),
        patch.object(entry.runtime_data.client, "set_sos_number") as write,
    ):
        await entry.runtime_data.async_set_contact(WATCH_ID, "sos_1", "", "0015555550100")
        write.assert_awaited_once_with(WATCH_ID, 1, "")
    assert hass.states.get(f"text.{NICK.lower()}_sos_1").state == ""



async def test_failed_contact_readback_is_not_reported_as_success(hass: HomeAssistant, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=[
            APP_DATA["data"], MykiError("request timed out"), APP_DATA["data"],
        ]),
        patch.object(entry.runtime_data.client, "set_sos_number") as write,
    ):
        with pytest.raises(HomeAssistantError, match="contact update failed"):
            await hass.services.async_call("text", "set_value", {
                "entity_id": f"text.{NICK.lower()}_sos_1", "value": "0015555550103",
            }, blocking=True)
        write.assert_awaited_once_with(WATCH_ID, 1, "0015555550103")
    assert hass.states.get(f"text.{NICK.lower()}_sos_1").state == "0015555550100"



async def test_grouped_names_preserve_entity_ids_and_custom_names(hass, aioclient_mock):
    """Display groups must not rename existing IDs or user-customized entities."""
    entry = await _setup(hass, aioclient_mock)
    grouped = {
        "number.testkid_ring_volume": "Audio: Ring volume",
        "number.testkid_call_volume": "Audio: Call volume",
        "select.testkid_ring_mode": "Audio: Ring mode",
        "select.testkid_ringtone": "Audio: Ringtone",
        "text.testkid_sos_1": "Contacts: SOS 1",
        "text.testkid_whitelist_1": "Contacts: Whitelist 1",
        "switch.testkid_status_led": "Lights: Status LED",
        "sensor.testkid_cell_towers": "Reception: Cell towers",
        "sensor.testkid_gps_satellites": "Reception: GPS satellites",
        "sensor.testkid_wifi_networks": "Reception: WiFi networks",
    }
    for entity_id, label in grouped.items():
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.attributes["friendly_name"] == f"{NICK} {label}"
    registry = er.async_get(hass)
    entity_id = "switch.testkid_status_led"
    registry.async_update_entity(entity_id, name="My custom light")
    await hass.async_block_till_done()
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(entity_id).name == "My custom light"
    assert hass.states.get(entity_id).attributes["friendly_name"] == f"{NICK} My custom light"


async def _setup_personalization(hass, aioclient_mock):
    entry = await _setup(hass, aioclient_mock)
    cloud = deepcopy(APP_DATA["data"])
    cloud["commands"].update({"profile": "1", "ringtone": "0", "led": "1"})
    entry.runtime_data._publish_contacts(WATCH_ID, deepcopy(cloud))
    await hass.async_block_till_done()
    return entry, cloud


@pytest.mark.parametrize("key,value,entity,state", [
    ("profile", "1", "select.testkid_ring_mode", "sound_and_vibration"),
    ("profile", 2, "select.testkid_ring_mode", "sound"),
    ("profile", "3", "select.testkid_ring_mode", "vibration"),
    ("profile", "4", "select.testkid_ring_mode", "mute"),
    ("ringtone", 0, "select.testkid_ringtone", "classic"),
    ("ringtone", "1", "select.testkid_ringtone", "playtime"),
    ("ringtone", "2", "select.testkid_ringtone", "twinkle"),
    ("led", "0", "switch.testkid_status_led", "off"),
    ("led", 1, "switch.testkid_status_led", "on"),
    ("led", "2", "switch.testkid_status_led", "unknown"),
])
async def test_personalization_tracks_cloud(hass, aioclient_mock, key, value, entity, state):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    cloud["commands"][key] = value
    entry.runtime_data._publish_contacts(WATCH_ID, cloud)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == state
    assert entry.options == {}
    assert hass.states.get(f"number.{NICK.lower()}_ring_volume").state == "4"
    assert hass.states.get(f"number.{NICK.lower()}_call_volume").state == "6"


@pytest.mark.parametrize("option,value", [("classic", "0"), ("playtime", "1"), ("twinkle", "2")])
async def test_missing_ringtone_uses_app_default_and_allows_edit(hass, aioclient_mock, option, value):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    del cloud["commands"]["ringtone"]
    with patch.object(entry.runtime_data.client, "set_personalization") as write:
        entry.runtime_data._publish_contacts(WATCH_ID, deepcopy(cloud))
        await hass.async_block_till_done()
        assert hass.states.get("select.testkid_ringtone").state == "classic"
        write.assert_not_awaited()

        async def update(watch_id, key, requested):
            cloud["commands"][key] = requested

        write.side_effect = update
        with patch.object(entry.runtime_data.client, "app_data", side_effect=lambda _: deepcopy(cloud)):
            await hass.services.async_call("select", "select_option", {
                "entity_id": "select.testkid_ringtone", "option": option,
            }, blocking=True)
        if option == "classic":
            write.assert_not_awaited()
            assert "ringtone" not in cloud["commands"]
        else:
            write.assert_awaited_once_with(WATCH_ID, "ringtone", value)
        assert hass.states.get("select.testkid_ringtone").state == option
        assert entry.options == {}


@pytest.mark.parametrize("key,entity", [
    ("profile", "select.testkid_ring_mode"),
    ("ringtone", "select.testkid_ringtone"),
    ("led", "switch.testkid_status_led"),
])
@pytest.mark.parametrize("value", [None, "", "99", [], {}, True, 1.5])
async def test_invalid_personalization_is_unknown(hass, aioclient_mock, key, entity, value):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    cloud["commands"][key] = value
    entry.runtime_data._publish_contacts(WATCH_ID, cloud)
    await hass.async_block_till_done()
    assert hass.states.get(entity).state == "unknown"


@pytest.mark.parametrize("key,value,domain,action,entity,extra,state", [
    ("profile", "2", "select", "select_option", "select.testkid_ring_mode", {"option": "sound"}, "sound"),
    ("profile", "3", "select", "select_option", "select.testkid_ring_mode", {"option": "vibration"}, "vibration"),
    ("profile", "4", "select", "select_option", "select.testkid_ring_mode", {"option": "mute"}, "mute"),
    ("ringtone", "1", "select", "select_option", "select.testkid_ringtone", {"option": "playtime"}, "playtime"),
    ("ringtone", "2", "select", "select_option", "select.testkid_ringtone", {"option": "twinkle"}, "twinkle"),
    ("led", "0", "switch", "turn_off", "switch.testkid_status_led", {}, "off"),
    ("led", "1", "switch", "turn_on", "switch.testkid_status_led", {}, "on"),
])
async def test_personalization_write_requires_cloud_readback(hass, aioclient_mock, key, value, domain, action, entity, extra, state):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    if key == "led":
        cloud["commands"]["led"] = "2"  # Explicit switch action exits temporary party mode.
        entry.runtime_data._publish_contacts(WATCH_ID, deepcopy(cloud))
        await hass.async_block_till_done()
    previous = hass.states.get(entity).state
    untouched = deepcopy(cloud)

    async def read(wid):
        assert wid == WATCH_ID
        return deepcopy(cloud)

    async def write(wid, setting, requested):
        assert (wid, setting, requested) == (WATCH_ID, key, value)
        assert hass.states.get(entity).state == previous
        cloud["commands"][setting] = requested

    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=read),
        patch.object(entry.runtime_data.client, "set_personalization", side_effect=write) as request,
    ):
        await hass.services.async_call(domain, action, {"entity_id": entity, **extra}, blocking=True)
        request.assert_awaited_once_with(WATCH_ID, key, value)
    await hass.async_block_till_done()
    untouched["commands"][key] = value
    assert cloud == untouched
    assert hass.states.get(entity).state == state
    assert entry.options == {}


@pytest.mark.parametrize("key,value,expected", [("profile", "2", "1"), ("ringtone", "1", "0"), ("led", "0", "1")])
@pytest.mark.parametrize("failure", ["offline", "stale", "missing", "invalid", "rejected", "unconfirmed", "readback_failed"])
async def test_personalization_failures(hass, aioclient_mock, key, value, expected, failure):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    if failure == "offline":
        cloud["settings"]["online"] = "0"
    elif failure == "stale":
        cloud["commands"][key] = value
    elif failure == "missing":
        cloud["commands"].pop(key)
    elif failure == "invalid":
        cloud["commands"][key] = "99"
    reads = [deepcopy(cloud), MykiError("request timed out")] if failure == "readback_failed" else [deepcopy(cloud), deepcopy(cloud)]
    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=reads),
        patch.object(entry.runtime_data.client, "set_personalization", side_effect=MykiError("rejected") if failure == "rejected" else None) as write,
    ):
        with pytest.raises(MykiError):
            await entry.runtime_data.async_set_personalization(WATCH_ID, key, value, expected)
        if failure in ("rejected", "unconfirmed", "readback_failed") or (failure == "missing" and key == "ringtone"):
            write.assert_awaited_once_with(WATCH_ID, key, value)
        else:
            write.assert_not_awaited()
    assert entry.options == {}


@pytest.mark.parametrize("key,value", [("profile", "1"), ("ringtone", "0"), ("led", "1")])
async def test_unchanged_personalization_does_not_write(hass, aioclient_mock, key, value):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    with (
        patch.object(entry.runtime_data.client, "app_data", return_value=cloud),
        patch.object(entry.runtime_data.client, "set_personalization") as write,
    ):
        await entry.runtime_data.async_set_personalization(WATCH_ID, key, value, value)
        write.assert_not_awaited()


@pytest.mark.parametrize("domain,action,entity,extra", [
    ("select", "select_option", "select.testkid_ring_mode", {"option": "sound"}),
    ("select", "select_option", "select.testkid_ringtone", {"option": "playtime"}),
    ("switch", "turn_off", "switch.testkid_status_led", {}),
])
async def test_failed_personalization_action_refreshes_and_reports_error(hass, aioclient_mock, domain, action, entity, extra):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    previous = hass.states.get(entity).state
    with (
        patch.object(entry.runtime_data.client, "app_data", return_value=deepcopy(cloud)),
        patch.object(entry.runtime_data.client, "set_personalization", side_effect=MykiError("rejected")) as write,
    ):
        with pytest.raises(HomeAssistantError, match="update failed"):
            await hass.services.async_call(domain, action, {"entity_id": entity, **extra}, blocking=True)
        write.assert_awaited_once()
    assert hass.states.get(entity).state == previous


async def test_personalization_writes_are_serialized(hass, aioclient_mock):
    entry, cloud = await _setup_personalization(hass, aioclient_mock)
    active = maximum = 0

    async def read(wid):
        return deepcopy(cloud)

    async def write(wid, key, value):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await sleep(0)
        cloud["commands"][key] = value
        active -= 1

    with (
        patch.object(entry.runtime_data.client, "app_data", side_effect=read),
        patch.object(entry.runtime_data.client, "set_personalization", side_effect=write),
    ):
        await gather(
            entry.runtime_data.async_set_personalization(WATCH_ID, "profile", "2", "1"),
            entry.runtime_data.async_set_personalization(WATCH_ID, "ringtone", "1", "0"),
        )
    assert maximum == 1
    assert cloud["commands"]["profile"] == "2"
    assert cloud["commands"]["ringtone"] == "1"



async def test_personalization_targets_selected_tracker_and_survives_reload(hass, aioclient_mock):
    other_id = "other-tracker"
    other_app = deepcopy(APP_DATA)
    other_app["data"]["commands"].update({"profile": "1", "ringtone": "0", "led": "1"})
    aioclient_mock.get(f"{BASE_URL}/watch/app-data?id={other_id}", json=other_app)
    aioclient_mock.get(f"{BASE_URL}/watch/history/events?id={other_id}", json={"isok": True})
    with patch.dict(WATCHES["data"], allw=[
        WATCHES["data"]["allw"][0], {"id": other_id, "nickname": "OtherKid", "api": 2},
    ]):
        entry = await _setup(hass, aioclient_mock)
        registry = er.async_get(hass)
        entity = registry.async_get("select.otherkid_ring_mode")
        registry.async_update_entity(entity.entity_id, new_entity_id="select.custom_ring_mode", name="My ring mode")
        await hass.async_block_till_done()
        cloud = deepcopy(other_app["data"])

        async def write(wid, key, value):
            assert wid == other_id
            cloud["commands"][key] = value

        with (
            patch.object(entry.runtime_data.client, "app_data", side_effect=lambda wid: deepcopy(cloud)) as read,
            patch.object(entry.runtime_data.client, "set_personalization", side_effect=write) as request,
        ):
            await hass.services.async_call("select", "select_option", {
                "entity_id": "select.custom_ring_mode", "option": "sound",
            }, blocking=True)
            request.assert_awaited_once_with(other_id, "profile", "2")
            assert all(call.args == (other_id,) for call in read.await_args_list)
        assert entry.runtime_data.data[WATCH_ID]["app"] == APP_DATA["data"]
        assert entry.options == {}
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.states.get("select.custom_ring_mode").state == "sound_and_vibration"
        assert registry.async_get("select.custom_ring_mode").name == "My ring mode"
        assert entry.options == {}
        entry.runtime_data.async_set_updated_data({WATCH_ID: entry.runtime_data.data[WATCH_ID]})
        await hass.async_block_till_done()
        assert hass.states.get("select.custom_ring_mode").state == "unavailable"
        assert hass.states.get("select.otherkid_ringtone").state == "unavailable"
        assert hass.states.get("switch.otherkid_status_led").state == "unavailable"
