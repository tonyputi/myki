"""Remaining Spot app settings: pure validation and mocked HA/cloud round trips."""

from asyncio import gather, sleep
from copy import deepcopy
import json
from unittest.mock import patch
from urllib.parse import urlencode

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.exceptions import HomeAssistantError
import pytest
from pytest_homeassistant.common import MockConfigEntry
from yarl import URL

from custom_components.myki.api import BASE_URL, MykiClient, MykiError
from custom_components.myki.settings import edit_group, read_group, validate_group, validate_zone

ZONE = {"name": "Home", "lat": 10, "lon": 20, "radius": 0.212, "profile": 1, "active": 1, "vendor_field": {"keep": True}}
APP = {
    "settings": {
        "online": "1", "mode": "sos", "battery_save_mode": "0", "fw": "G36W-test",
        "nickname": "Example tracker", "msisdn": "+15555550100",
        **{f"safe_zone_{i}": json.dumps(ZONE) for i in range(1, 4)},
    },
    "commands": {
        "profile": "1", "ringtone": "0", "led": "1",
        "sos_phone_1": "0015555550100", "whitelist_1": "0015555550101,,,", "whitelist_2": ",,,,0015555550109",
        "silencetime": "22:00-06:00,12:00-13:00,00:00-00:00,00:00-00:00",
        "remind": "06:30-1-3-0100000,07:30-0-7-0000000,08:30-1-3-1000000",
    },
}


@pytest.fixture
async def settings_entry(hass, aioclient_mock):
    cloud = {f"test-{i}": deepcopy(APP) for i in range(2)}
    aioclient_mock.get(f"{BASE_URL}/watch", json={"isok": True, "data": {"allw": [
        {"id": wid, "nickname": f"TestKid{i}", "api": 2} for i, wid in enumerate(cloud)
    ]}})
    for wid in cloud:
        aioclient_mock.get(f"{BASE_URL}/watch/history/events?id={wid}", json={"isok": True})

    async def read(wid):
        return deepcopy(cloud[wid])

    entry = MockConfigEntry(domain="myki", data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"})
    entry.add_to_hass(hass)
    with patch.object(MykiClient, "app_data", side_effect=read):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, cloud


def _write_group(cloud, wid, key, value):
    section = "settings" if key.startswith("safe_zone_") else "commands"
    cloud[wid][section][key] = json.dumps(value) if section == "settings" else ",".join(value)


@pytest.mark.parametrize("field,value", [
    ("lat", True), ("lat", 91), ("lon", -181), ("radius", "nan"), ("radius", "inf"),
    ("radius", 0), ("radius", -1), ("lat", []), ("profile", 5), ("active", True), ("name", " "),
])
def test_zone_validation(field, value):
    with pytest.raises(ValueError):
        validate_zone({**ZONE, field: value})


@pytest.mark.parametrize("key,raw", [
    ("safe_zone_1", "not json"), ("safe_zone_1", "[]"), ("safe_zone_1", "null"),
    ("remind", "00:00-0-3-0000000"), ("remind", "25:00-0-3-0000000," * 3),
    ("silencetime", "00:00-00:00"), ("silencetime", None),
])
def test_invalid_cloud_group_is_rejected(key, raw):
    app = deepcopy(APP)
    app["settings" if key.startswith("safe_zone") else "commands"][key] = raw
    with pytest.raises(ValueError):
        read_group(app, key)


@pytest.mark.parametrize("changes", [
    {"latitude": float("nan")}, {"radius": 0}, {"radius": True}, {"ring_mode": "5"},
    {"enabled": "false"}, {"color": "#ffffff"}, {},
])
def test_invalid_zone_edit(changes):
    with pytest.raises((ValueError, OverflowError)):
        edit_group("safe_zone_1", ZONE, changes, None)


@pytest.mark.parametrize("changes", [
    {"enabled": True, "start": "08:00", "end": "08:00"},
    {"enabled": True, "start": "24:00"}, {"enabled": True, "end": "12:60"},
    {"enabled": "yes"}, {"enabled": True, "start": "08:00:00"},
])
def test_invalid_dnd_edit(changes):
    with pytest.raises(ValueError):
        edit_group("silencetime", read_group(APP, "silencetime"), changes, 0)


@pytest.mark.parametrize("changes", [
    {"time": "24:00"}, {"time": "8:00"}, {"weekdays": ["monday"]},
    {"weekdays": ["mon", "mon"]}, {"weekdays": "mon"}, {"weekdays": []},
    {"enabled": "1"}, {"timezone": "UTC"}, {},
])
def test_invalid_alarm_edit(changes):
    with pytest.raises(ValueError):
        edit_group("remind", read_group(APP, "remind"), changes, 0)


def test_weekday_mapping_and_opaque_digit():
    current = read_group(APP, "remind")
    result = edit_group("remind", current, {"weekdays": ["sun", "sat"], "time": "23:59"}, 0)
    assert result == ["23:59-1-3-1000001", *current[1:]]
    assert edit_group("remind", current, {"enabled": False}, 0)[0] == "06:30-0-3-0100000"
    assert current == read_group(APP, "remind")


async def test_cloud_configuration_states(hass, settings_entry):
    entry, cloud = settings_entry
    assert entry.runtime_data.data["test-0"]["app"]["settings"]["mode"] == "sos"
    assert entry.runtime_data.data["test-0"]["app"]["settings"]["battery_save_mode"] == "0"
    assert hass.states.get("switch.testkid0_flashlight").state == "off"
    zone = hass.states.get("sensor.testkid0_safe_zone_1")
    assert zone.state == "Home"
    assert zone.attributes["radius"] == 212
    assert zone.attributes["ring_mode"] == "sound_and_vibration"
    assert hass.states.get("sensor.testkid0_do_not_disturb").attributes["periods"][1] == "12:00-13:00"
    alarm = hass.states.get("sensor.testkid0_alarm_1")
    assert alarm.state == "06:30"
    assert alarm.attributes["enabled"] is True
    assert alarm.attributes["weekdays"] == ["mon"]
    cloud["test-0"]["commands"]["remind"] = "broken"
    cloud["test-0"]["settings"]["mode"] = "unknown-mode"
    cloud["test-0"]["settings"]["battery_save_mode"] = None
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.testkid0_alarm_1").state == "unknown"
    assert hass.states.get("select.testkid0_operating_mode") is None
    assert hass.states.get("switch.testkid0_battery_save") is None
    assert entry.options == {}


@pytest.mark.parametrize("key,value", [("battery_save_mode", "1"), ("mode", "pet"), ("mode", "asset"), ("flashlight", "2")])
async def test_scalar_actions_target_and_confirm(hass, settings_entry, key, value):
    entry, cloud = settings_entry
    before = deepcopy(cloud)

    async def write(wid, setting, raw):
        assert (wid, setting, raw) == ("test-0", key, value)
        section = "settings" if key in ("mode", "battery_save_mode") else "commands"
        field = "led" if key == "flashlight" else key
        cloud[wid][section][field] = raw
        before[wid][section][field] = raw

    with patch.object(entry.runtime_data.client, "set_personalization", side_effect=write) as request:
        if key == "flashlight":
            await hass.services.async_call("switch", "turn_on", {"entity_id": "switch.testkid0_flashlight"}, blocking=True)
        else:
            await entry.runtime_data.async_set_personalization("test-0", key, value, APP["settings"][key])
        request.assert_awaited_once_with("test-0", key, value)
    assert cloud == before
    assert entry.options == {}


async def test_mode_side_effect_is_reported_without_rollback(hass, settings_entry):
    entry, cloud = settings_entry

    async def write(wid, key, raw):
        cloud[wid]["settings"]["mode"] = raw
        cloud[wid]["commands"]["sos_phone_1"] = ""

    with patch.object(entry.runtime_data.client, "set_personalization", side_effect=write) as request:
        with pytest.raises(MykiError, match="mode changed other configuration"):
            await entry.runtime_data.async_set_personalization("test-0", "mode", "pet", "sos")
        request.assert_awaited_once()
    assert cloud["test-0"]["commands"]["sos_phone_1"] == ""
    assert cloud["test-0"]["settings"]["mode"] == "pet"


@pytest.mark.parametrize("key,index,action,params", [
    ("safe_zone_1", None, "set_safe_zone", {"zone": "safe_zone_1", "radius": 70, "enabled": False, "ring_mode": "4"}),
    ("safe_zone_2", None, "set_safe_zone", {"zone": "safe_zone_2", "name": "Office", "latitude": 11, "longitude": 21}),
    ("silencetime", 0, "set_dnd", {"enabled": False}),
    ("silencetime", 0, "set_dnd", {"enabled": True, "start": "23:00", "end": "05:00"}),
    ("remind", 0, "set_alarm", {"alarm": "alarm_1", "time": "07:15", "weekdays": ["sun", "sat"]}),
    ("remind", 1, "set_alarm", {"alarm": "alarm_2", "enabled": True, "weekdays": ["wed"]}),
    ("remind", 2, "set_alarm", {"alarm": "alarm_3", "enabled": False}),
])
async def test_group_actions_preserve_siblings(hass, settings_entry, key, index, action, params):
    entry, cloud = settings_entry
    before = deepcopy(cloud)
    changes = {field: val for field, val in params.items() if field not in ("zone", "alarm")}
    expected = edit_group(key, read_group(APP, key), changes, index)

    async def write(wid, actual_key, requested):
        assert (wid, actual_key, requested) == ("test-0", key, expected)
        _write_group(cloud, wid, actual_key, requested)
        _write_group(before, wid, actual_key, requested)

    with patch.object(entry.runtime_data.client, "set_setting_group", side_effect=write) as request:
        await hass.services.async_call("myki", action, {"entity_id": "device_tracker.testkid0", **params}, blocking=True)
        request.assert_awaited_once()
    assert cloud == before
    assert entry.options == {}


@pytest.mark.parametrize("key,index,changes", [
    ("safe_zone_1", None, {"radius": 71}), ("silencetime", 0, {"enabled": False}),
    ("remind", 0, {"time": "07:10"}),
])
@pytest.mark.parametrize("failure", ["stale", "offline", "malformed", "rejected", "unconfirmed", "readback_failed"])
async def test_group_failures_never_retry_or_rollback(settings_entry, key, index, changes, failure):
    entry, cloud = settings_entry
    current = read_group(APP, key)
    expected = current[index] if index is not None else current
    if failure == "offline":
        cloud["test-0"]["settings"]["online"] = "0"
    elif failure == "stale":
        fresh = edit_group(key, current, {"name": "Changed"} if index is None else {"time": "08:10"} if key == "remind" else {"enabled": True, "start": "21:00"}, index)
        _write_group(cloud, "test-0", key, fresh)
    elif failure == "malformed":
        cloud["test-0"]["settings" if index is None else "commands"][key] = "invalid"
    with patch.object(entry.runtime_data.client, "set_setting_group", side_effect=MykiError("rejected") if failure == "rejected" else None) as request:
        if failure == "readback_failed":
            with patch.object(entry.runtime_data.client, "app_data", side_effect=[deepcopy(cloud["test-0"]), MykiError("request timed out")]):
                with pytest.raises(MykiError):
                    await entry.runtime_data.async_edit_setting_group("test-0", key, changes, expected, index)
        else:
            with pytest.raises(MykiError):
                await entry.runtime_data.async_edit_setting_group("test-0", key, changes, expected, index)
        assert request.await_count == (0 if failure in ("stale", "offline", "malformed") else 1)


async def test_latest_alarm_sibling_and_concurrent_commands(settings_entry):
    entry, cloud = settings_entry
    current = read_group(APP, "remind")
    fresh = [*current[:2], "09:15-1-9-0000010"]
    _write_group(cloud, "test-0", "remind", fresh)
    active = maximum = 0

    async def write(wid, key, requested):
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await sleep(0)
        _write_group(cloud, wid, key, requested)
        active -= 1

    with patch.object(entry.runtime_data.client, "set_setting_group", side_effect=write):
        await gather(
            entry.runtime_data.async_edit_setting_group("test-0", "remind", {"time": "07:10"}, current[0], 0),
            entry.runtime_data.async_edit_setting_group("test-0", "remind", {"time": "07:20"}, current[1], 1),
        )
    assert maximum == 1
    assert read_group(cloud["test-0"], "remind") == ["07:10-1-3-0100000", "07:20-0-7-0000000", fresh[2]]


@pytest.mark.parametrize("key,value,endpoint,params", [
    ("mode", "asset", "mode", {"mode": "asset"}),
    ("battery_save_mode", "1", "save-settings", {"key": "battery_save_mode", "val": "1"}),
    ("flashlight", "2", "led", {"status": "2"}),
])
async def test_scalar_endpoints(settings_entry, aioclient_mock, key, value, endpoint, params):
    entry, _ = settings_entry
    url = f"{BASE_URL}/watch/{endpoint}?" + urlencode({"id": "test&tracker", **params})
    aioclient_mock.get(url, json={"isok": True})
    await entry.runtime_data.client.set_personalization("test&tracker", key, value)
    assert aioclient_mock.mock_calls[-1][1] == URL(url)


@pytest.mark.parametrize("key,endpoint", [("safe_zone_1", "save-settings"), ("silencetime", "silencetime"), ("remind", "remind")])
async def test_group_endpoints(settings_entry, aioclient_mock, key, endpoint):
    entry, _ = settings_entry
    value = read_group(APP, key)
    if key.startswith("safe_zone"):
        params = {"key": key, "val": json.dumps(value, allow_nan=False, separators=(",", ":"))}
    else:
        prefix = "period" if key == "silencetime" else "alarm"
        params = {f"{prefix}{i}": raw for i, raw in enumerate(value, 1)}
    url = f"{BASE_URL}/watch/{endpoint}?" + urlencode({"id": "test&tracker", **params})
    aioclient_mock.get(url, json={"isok": True})
    await entry.runtime_data.client.set_setting_group("test&tracker", key, value)
    assert aioclient_mock.mock_calls[-1][1] == URL(url)


@pytest.mark.parametrize("key,value", [("safe_zone_3", ZONE), ("safe_zone_1", {}), ("remind", []), ("silencetime", ["invalid"] * 4)])
async def test_invalid_group_request_stops_at_boundary(settings_entry, aioclient_mock, key, value):
    entry, _ = settings_entry
    calls = len(aioclient_mock.mock_calls)
    with pytest.raises(MykiError):
        await entry.runtime_data.client.set_setting_group("test-0", key, value)
    assert len(aioclient_mock.mock_calls) == calls


def test_group_validator_refuses_unknown_key():
    with pytest.raises(ValueError):
        validate_group("safe_zone_3", [])


@pytest.mark.parametrize("action,command", [("power_off", "poweroff"), ("restart", "reset")])
@pytest.mark.parametrize("failure", [None, "not_confirmed", "offline", "rejected"])
async def test_device_commands_require_confirmation_and_do_not_fake_completion(hass, settings_entry, action, command, failure):
    entry, cloud = settings_entry
    if failure == "offline":
        cloud["test-0"]["settings"]["online"] = "0"
    before = deepcopy(cloud)
    data = {"entity_id": "device_tracker.testkid0", "confirm": failure != "not_confirmed"}
    with patch.object(entry.runtime_data.client, "device_command", side_effect=MykiError("rejected") if failure == "rejected" else None) as request:
        if failure:
            with pytest.raises(HomeAssistantError):
                await hass.services.async_call("myki", action, data, blocking=True)
        else:
            await hass.services.async_call("myki", action, data, blocking=True)
        assert request.await_count == (0 if failure in ("not_confirmed", "offline") else 1)
        if request.await_count:
            request.assert_awaited_once_with("test-0", command)
    assert cloud == before
    if failure is None:
        assert hass.states.get("binary_sensor.testkid0_online").state == "on"


@pytest.mark.parametrize("command", ["poweroff", "reset"])
async def test_device_command_endpoints(settings_entry, aioclient_mock, command):
    entry, _ = settings_entry
    url = f"{BASE_URL}/watch/{command}?id=test%26tracker"
    aioclient_mock.get(url, json={"isok": True})
    await entry.runtime_data.client.device_command("test&tracker", command)
    assert aioclient_mock.mock_calls[-1][1] == URL(url)


@pytest.mark.parametrize("command", ["factory", "delete", "poweron", "reset&factory=1"])
async def test_destructive_commands_are_not_available(settings_entry, aioclient_mock, command):
    entry, _ = settings_entry
    calls = len(aioclient_mock.mock_calls)
    with pytest.raises(MykiError):
        await entry.runtime_data.client.device_command("test-0", command)
    assert len(aioclient_mock.mock_calls) == calls


async def test_empty_zone_requires_full_explicit_configuration(hass, settings_entry):
    entry, cloud = settings_entry
    cloud["test-0"]["settings"]["safe_zone_1"] = ""
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    with patch.object(entry.runtime_data.client, "set_setting_group") as request:
        with pytest.raises(HomeAssistantError, match="invalid safe-zone"):
            await hass.services.async_call("myki", "set_safe_zone", {
                "entity_id": "device_tracker.testkid0", "zone": "safe_zone_1", "enabled": True,
            }, blocking=True)
        request.assert_not_awaited()
    with patch.object(entry.runtime_data.client, "set_setting_group", side_effect=lambda wid, key, raw: _write_group(cloud, wid, key, raw)):
        await hass.services.async_call("myki", "set_safe_zone", {
            "entity_id": "device_tracker.testkid0", "zone": "safe_zone_1", "name": "Office",
            "latitude": 12, "longitude": 21, "radius": 70, "enabled": True, "ring_mode": "1",
        }, blocking=True)
    assert read_group(cloud["test-0"], "safe_zone_1")["radius"] == 0.07


@pytest.mark.parametrize("raw,expected", [("0", "off"), ("1", "off"), ("2", "on"), (None, "unknown")])
async def test_flashlight_state_and_off_does_not_enable_disabled_status_led(hass, settings_entry, raw, expected):
    entry, cloud = settings_entry
    cloud["test-0"]["commands"]["led"] = raw
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("switch.testkid0_flashlight").state == expected
    if raw == "0":
        with patch.object(entry.runtime_data.client, "set_personalization") as request:
            await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.testkid0_flashlight"}, blocking=True)
            request.assert_not_awaited()


async def test_group_edit_noop_and_input_validation(settings_entry):
    entry, _ = settings_entry
    with patch.object(entry.runtime_data.client, "set_setting_group") as request:
        await entry.runtime_data.async_edit_setting_group("test-0", "safe_zone_1", {"radius": 212}, ZONE)
        request.assert_not_awaited()
        for index in (True, -1, 3, "0"):
            with pytest.raises(MykiError, match="invalid schedule slot"):
                await entry.runtime_data.async_edit_setting_group("test-0", "remind", {"time": "07:00"}, "", index)
        request.assert_not_awaited()


async def test_new_settings_use_cloud_after_reload_and_disappearance(hass, settings_entry):
    entry, cloud = settings_entry
    cloud["test-0"]["settings"]["mode"] = "asset"
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["test-0"]["app"]["settings"]["mode"] == "asset"
    assert entry.options == {}
    entry.runtime_data.async_set_updated_data({"test-1": entry.runtime_data.data["test-1"]})
    await hass.async_block_till_done()
    for entity in ("switch.testkid0_flashlight", "sensor.testkid0_alarm_1", "sensor.testkid0_do_not_disturb", "sensor.testkid0_safe_zone_1"):
        assert hass.states.get(entity).state == "unavailable"


@pytest.mark.parametrize("key,value", [("nickname", "Example renamed"), ("msisdn", "+15555550102")])
async def test_shared_tracker_details_preserve_fresh_sibling(hass, settings_entry, key, value):
    entry, cloud = settings_entry
    sibling = "msisdn" if key == "nickname" else "nickname"
    cloud["test-0"]["settings"][sibling] = "+15555550103" if sibling == "msisdn" else "App rename"
    before = deepcopy(cloud)

    async def write(wid, name, phone):
        assert wid == "test-0"
        cloud[wid]["settings"].update(nickname=name, msisdn=phone)
        before[wid]["settings"][key] = value

    with patch.object(entry.runtime_data.client, "set_tracker_details", side_effect=write) as request:
        await entry.runtime_data.async_set_tracker_detail("test-0", key, value, APP["settings"][key])
        request.assert_awaited_once()
    assert entry.runtime_data.data["test-0"]["app"]["settings"][key] == value
    assert cloud == before
    assert entry.options == {}


@pytest.mark.parametrize("failure", ["stale", "offline", "rejected", "unconfirmed"])
async def test_tracker_detail_failures(hass, settings_entry, failure):
    entry, cloud = settings_entry
    if failure == "stale":
        cloud["test-0"]["settings"]["nickname"] = "Changed by app"
    elif failure == "offline":
        cloud["test-0"]["settings"]["online"] = "0"
    with patch.object(entry.runtime_data.client, "set_tracker_details", side_effect=MykiError("rejected") if failure == "rejected" else None) as request:
        with pytest.raises(MykiError):
            await entry.runtime_data.async_set_tracker_detail("test-0", "nickname", "Rename", APP["settings"]["nickname"])
        assert request.await_count == (0 if failure in ("stale", "offline") else 1)


async def test_tracker_details_post_body_and_error_privacy(settings_entry, aioclient_mock):
    entry, _ = settings_entry
    url = f"{BASE_URL}/watch/edit"
    aioclient_mock.post(url, json={"isok": True})
    await entry.runtime_data.client.set_tracker_details("test&tracker", "Example", "+15555550102")
    method, requested_url, body, _ = aioclient_mock.mock_calls[-1]
    assert method.upper() == "POST"
    assert requested_url == URL(url)
    assert body == {"watchId": "test&tracker", "watchName": "Example", "watchPhone": "+15555550102"}
    aioclient_mock.clear_requests()
    aioclient_mock.post(url, status=503, json={"isok": False, "err": "private-sentinel"})
    with pytest.raises(MykiError) as err:
        await entry.runtime_data.client.set_tracker_details("test&tracker", "Example", "+15555550102")
    assert "private-sentinel" not in str(err.value)


@pytest.mark.parametrize("name,phone", [("", "+15555550100"), ("Name", "invalid"), ("Name", ""), ("Name", None), (None, "+15555550100")])
async def test_invalid_tracker_details_never_write(settings_entry, aioclient_mock, name, phone):
    entry, _ = settings_entry
    calls = len(aioclient_mock.mock_calls)
    with pytest.raises(MykiError):
        await entry.runtime_data.client.set_tracker_details("test-0", name, phone)
    assert len(aioclient_mock.mock_calls) == calls
