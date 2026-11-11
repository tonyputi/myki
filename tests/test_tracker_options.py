"""Native tracker configuration through HA's actual options-flow manager."""

from copy import deepcopy
import json
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er, selector
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.myki.api import BASE_URL, MykiAuthError, MykiClient, MykiError

ZONE = {"name": "Home", "lat": 10, "lon": 20, "radius": 0.2, "active": 1, "profile": 1, "opaque": {"keep": True}}
APP = {
    "settings": {"online": "1", "nickname": "Example", "msisdn": "+15555550100", "mode": "sos", "battery_save_mode": "0", **{f"safe_zone_{i}": json.dumps(ZONE) for i in range(1, 4)}},
    "commands": {"profile": "1", "ringtone": "0", "led": "1", "volume_ring": "4", "volume_call": "6", "sos_phone_1": "0015555550100", "whitelist_1": "0015555550101,,,,", "whitelist_2": ",,,,0015555550109", "silencetime": "22:00-06:00,12:00-13:00,00:00-00:00,00:00-00:00", "remind": "06:30-1-3-0100000,07:30-0-7-0000000,08:30-1-3-1000000"},
}


@pytest.fixture
async def tracker_entry(hass, aioclient_mock):
    cloud = {f"test-{i}": deepcopy(APP) for i in range(2)}
    aioclient_mock.get(f"{BASE_URL}/watch", json={"isok": True, "data": {"allw": [{"id": wid, "nickname": f"Tracker {i}"} for i, wid in enumerate(cloud)]}})
    for wid in cloud:
        aioclient_mock.get(f"{BASE_URL}/watch/history/events?id={wid}", json={"isok": True})
    entry = MockConfigEntry(domain="myki", data={"email": "test@example.com", "password": "test-password"}, options={"scan_interval": 120})
    entry.add_to_hass(hass)

    async def read(wid):
        return deepcopy(cloud[wid])

    async def scalar(wid, key, value):
        section = "settings" if key in ("mode", "battery_save_mode") else "commands"
        cloud[wid][section][key] = value

    async def group(wid, key, value):
        section = "settings" if key.startswith("safe_zone_") else "commands"
        cloud[wid][section][key] = json.dumps(value) if section == "settings" else ",".join(value)

    async def sos(wid, slot, phone):
        cloud[wid]["commands"][f"sos_phone_{slot}"] = phone

    async def whitelist(wid, group, phones):
        cloud[wid]["commands"][f"whitelist_{group}"] = ",".join(phones)

    async def details(wid, name, phone):
        cloud[wid]["settings"].update(nickname=name, msisdn=phone)

    async def ring(wid, level):
        cloud[wid]["commands"]["volume_ring"] = str(level)

    async def call(wid, level):
        cloud[wid]["commands"]["volume_call"] = str(level)

    with (
        patch.object(MykiClient, "app_data", side_effect=read),
        patch.object(MykiClient, "set_personalization", side_effect=scalar) as scalar_write,
        patch.object(MykiClient, "set_setting_group", side_effect=group) as group_write,
        patch.object(MykiClient, "set_sos_number", side_effect=sos) as sos_write,
        patch.object(MykiClient, "set_whitelist", side_effect=whitelist) as whitelist_write,
        patch.object(MykiClient, "set_tracker_details", side_effect=details) as details_write,
        patch.object(MykiClient, "set_ring_volume", side_effect=ring) as ring_write,
        patch.object(MykiClient, "set_call_volume", side_effect=call) as call_write,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        yield entry, cloud, [scalar_write, group_write, sos_write, whitelist_write, details_write, ring_write, call_write]


async def editor(hass, entry, section, choice, *, tracker="test-0", expected_type=FlowResultType.FORM, language="en"):
    result = await hass.config_entries.options.async_init(entry.entry_id, context={"language": language})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["tracker", "polling"]
    flow_id = result["flow_id"]
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "tracker"})
    assert result["step_id"] == "tracker"
    result = await hass.config_entries.options.async_configure(flow_id, {"tracker": tracker})
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["contacts", "audio", "device", "zones", "schedules"]
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": section})
    result = await hass.config_entries.options.async_configure(flow_id, choice)
    assert result["type"] is expected_type
    return result


def suggested(result):
    return {key.schema: key.description["suggested_value"] for key in result["data_schema"].schema if isinstance(key.description, dict) and "suggested_value" in key.description}


async def test_default_device_page_only_exposes_status_diagnostics_and_quick_controls(hass, tracker_entry):
    entry, _, writes = tracker_entry
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.domain in ("number", "select", "text") or entity.unique_id.endswith(("_status_led", "_battery_save_mode")):
            pytest.fail(f"Retired configuration entity was recreated: {entity.entity_id}")
        else:
            assert entity.disabled_by is None
            assert hass.states.get(entity.entity_id) is not None
    assert hass.states.get("switch.tracker_0_flashlight") is not None
    assert all(write.await_count == 0 for write in writes)


@pytest.mark.parametrize("section,choice,expected", [
    ("contacts", {"contact": "sos_1"}, {"value": "0015555550100"}),
    ("audio", {"setting": "ringtone"}, {"value": "0"}),
    ("audio", {"setting": "volume_call"}, {"value": 6}),
    ("device", {"setting": "nickname"}, {"value": "Example"}),
    ("schedules", {"schedule": "alarm_2"}, {"enabled": False, "time": "07:30", "weekdays": []}),
    ("schedules", {"schedule": "dnd"}, {"enabled": True, "start": "22:00", "end": "06:00"}),
])
async def test_forms_read_fresh_cloud_values_without_writing(hass, tracker_entry, section, choice, expected):
    entry, _, writes = tracker_entry
    result = await editor(hass, entry, section, choice)
    assert suggested(result) == expected
    hass.config_entries.options.async_abort(result["flow_id"])
    assert all(write.await_count == 0 for write in writes)
    assert entry.options == {"scan_interval": 120}


@pytest.mark.parametrize("language,label", [("en", "Safe zone 2"), ("it", "Zona sicura 2")])
async def test_editor_identifies_selected_tracker_and_setting_in_both_languages(hass, tracker_entry, language, label):
    entry, _, _ = tracker_entry
    result = await editor(hass, entry, "zones", {"zone": "safe_zone_2"}, tracker="test-1", language=language)
    assert result["description_placeholders"] == {"tracker": "Tracker 1", "setting": label}


async def test_native_zone_map_has_current_center_and_meter_radius(hass, tracker_entry):
    entry, cloud, writes = tracker_entry
    fresh = {**ZONE, "lat": 11, "radius": 0.321}
    cloud["test-0"]["settings"]["safe_zone_1"] = json.dumps(fresh)
    result = await editor(hass, entry, "zones", {"zone": "safe_zone_1"})
    assert suggested(result) == {"name": "Home", "location": {"latitude": 11, "longitude": 20, "radius": 321}, "enabled": True, "ring_mode": "1"}
    location = next(value for key, value in result["data_schema"].schema.items() if key.schema == "location")
    assert isinstance(location, selector.LocationSelector)
    assert location.config["radius"] is True
    assert all(write.await_count == 0 for write in writes)
    before = deepcopy(cloud)
    submitted = {"name": "School", "location": {"latitude": 12.1, "longitude": 22.3, "radius": 250}, "enabled": False, "ring_mode": "3"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["reason"] == "settings_saved"
    written = json.loads(cloud["test-0"]["settings"]["safe_zone_1"])
    assert written == {**fresh, "name": "School", "lat": 12.1, "lon": 22.3, "radius": 0.25, "active": 0, "profile": 3}
    before["test-0"]["settings"]["safe_zone_1"] = cloud["test-0"]["settings"]["safe_zone_1"]
    assert cloud == before
    assert entry.options == {"scan_interval": 120}
    assert writes[1].await_count == 1


@pytest.mark.parametrize("section,choice,submitted,section_key,key,value", [
    ("audio", {"setting": "profile"}, {"value": "4"}, "commands", "profile", "4"),
    ("audio", {"setting": "ringtone"}, {"value": "2"}, "commands", "ringtone", "2"),
    ("audio", {"setting": "led"}, {"value": "0"}, "commands", "led", "0"),
    ("audio", {"setting": "volume_ring"}, {"value": 2}, "commands", "volume_ring", "2"),
    ("audio", {"setting": "volume_call"}, {"value": 3}, "commands", "volume_call", "3"),
    ("device", {"setting": "mode"}, {"value": "pet"}, "settings", "mode", "pet"),
    ("device", {"setting": "battery_save_mode"}, {"value": "1"}, "settings", "battery_save_mode", "1"),
    ("device", {"setting": "nickname"}, {"value": "New name"}, "settings", "nickname", "New name"),
    ("device", {"setting": "msisdn"}, {"value": "+15555550102"}, "settings", "msisdn", "+15555550102"),
])
async def test_setting_forms_write_only_selected_tracker_and_field(hass, tracker_entry, section, choice, submitted, section_key, key, value):
    entry, cloud, writes = tracker_entry
    before = deepcopy(cloud)
    coordinator = entry.runtime_data
    result = await editor(hass, entry, section, choice, tracker="test-1")
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["reason"] == "settings_saved"
    before["test-1"][section_key][key] = value
    assert cloud == before
    assert sum(write.await_count for write in writes) == 1
    assert entry.runtime_data is coordinator
    assert entry.options == {"scan_interval": 120}


@pytest.mark.parametrize("slot,submitted,expected", [("sos_1", {"value": "+15555550102"}, "0015555550102"), ("sos_1", {}, ""), ("whitelist_7", {"value": "+15555550102"}, "0015555550102")])
async def test_contacts_preserve_latest_siblings_and_allow_clear(hass, tracker_entry, slot, submitted, expected):
    entry, cloud, writes = tracker_entry
    result = await editor(hass, entry, "contacts", {"contact": slot})
    cloud["test-0"]["commands"]["whitelist_2"] = ",,,0015555550108,0015555550109"
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["reason"] == "settings_saved"
    if slot == "sos_1":
        assert cloud["test-0"]["commands"]["sos_phone_1"] == expected
    else:
        assert cloud["test-0"]["commands"]["whitelist_2"] == f",{expected},,0015555550108,0015555550109"
    assert entry.options == {"scan_interval": 120}
    assert sum(write.await_count for write in writes) == 1


@pytest.mark.parametrize("schedule,submitted,expected", [
    ("alarm_2", {"enabled": True, "time": "09:15:00", "weekdays": ["sun", "wed", "sat"]}, "09:15-1-7-1001001"),
    ("alarm_1", {"enabled": False, "time": "06:30", "weekdays": ["mon"]}, "06:30-0-3-0100000"),
    ("dnd", {"enabled": True, "start": "21:00:00", "end": "07:00:00"}, "21:00-07:00"),
    ("dnd", {"enabled": False, "start": "22:00", "end": "06:00"}, "00:00-00:00"),
])
async def test_schedule_edit_keeps_latest_siblings_opaque_digit_and_wall_clock(hass, tracker_entry, schedule, submitted, expected):
    entry, cloud, writes = tracker_entry
    result = await editor(hass, entry, "schedules", {"schedule": schedule})
    key = "silencetime" if schedule == "dnd" else "remind"
    index = 0 if schedule == "dnd" else int(schedule[-1]) - 1
    siblings = cloud["test-0"]["commands"][key].split(",")
    siblings[-1] = "13:00-14:00" if key == "silencetime" else "10:00-0-8-0000001"
    cloud["test-0"]["commands"][key] = ",".join(siblings)
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["reason"] == "settings_saved"
    siblings[index] = expected
    assert cloud["test-0"]["commands"][key] == ",".join(siblings)
    assert writes[1].await_count == 1
    assert entry.options == {"scan_interval": 120}


@pytest.mark.parametrize("section,choice,submitted", [
    ("contacts", {"contact": "sos_1"}, {"value": "not a phone"}),
    ("contacts", {"contact": "sos_1"}, {"value": "1" * 33}),
    ("device", {"setting": "nickname"}, {"value": " "}),
    ("device", {"setting": "msisdn"}, {"value": "bad"}),
    ("zones", {"zone": "safe_zone_1"}, {"name": "Home", "location": {"latitude": 10, "longitude": 20, "radius": 0}, "enabled": True, "ring_mode": "1"}),
    ("schedules", {"schedule": "alarm_1"}, {"enabled": True, "time": "08:00:00", "weekdays": []}),
    ("schedules", {"schedule": "alarm_1"}, {"enabled": True, "time": "08:00:01", "weekdays": ["mon"]}),
    ("schedules", {"schedule": "dnd"}, {"enabled": True, "start": "08:00:00", "end": "08:00:00"}),
])
async def test_invalid_edits_keep_form_open_without_any_write(hass, tracker_entry, section, choice, submitted):
    entry, cloud, writes = tracker_entry
    before = deepcopy(cloud)
    result = await editor(hass, entry, section, choice)
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_input"}
    assert all(write.await_count == 0 for write in writes)
    assert before == cloud


@pytest.mark.parametrize("failure", ["stale", "offline", "rejected", "unconfirmed", "readback_timeout"])
@pytest.mark.parametrize("setting", ["ringtone", "volume_ring"])
async def test_uncertain_or_conflicting_edits_close_draft_without_retry(hass, tracker_entry, failure, setting):
    entry, cloud, writes = tracker_entry
    result = await editor(hass, entry, "audio", {"setting": setting})
    write = writes[0 if setting == "ringtone" else 5]
    if failure == "stale":
        cloud["test-0"]["commands"][setting] = "1"
    elif failure == "offline":
        cloud["test-0"]["settings"]["online"] = "0"
    elif failure == "rejected":
        write.side_effect = MykiError("private error must not be shown")
    elif failure == "unconfirmed":
        write.side_effect = None
    else:
        original = entry.runtime_data.client.app_data.side_effect
        calls = 0

        async def timeout_read(wid):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MykiError("request timed out")
            return await original(wid)

        entry.runtime_data.client.app_data.side_effect = timeout_read
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"value": "2" if setting == "ringtone" else 2})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "write_failed"
    assert write.await_count == (0 if failure in ("stale", "offline") else 1)
    assert entry.options == {"scan_interval": 120}


@pytest.mark.parametrize("section,choice,part,key,invalid", [
    ("zones", {"zone": "safe_zone_1"}, "settings", "safe_zone_1", "not JSON"),
    ("schedules", {"schedule": "alarm_1"}, "commands", "remind", None),
    ("schedules", {"schedule": "dnd"}, "commands", "silencetime", None),
    ("audio", {"setting": "ringtone"}, "commands", "ringtone", "99"),
    ("audio", {"setting": "volume_ring"}, "commands", "volume_ring", "99"),
    ("device", {"setting": "nickname"}, "settings", "nickname", None),
])
async def test_malformed_cloud_settings_are_not_invented(hass, tracker_entry, section, choice, part, key, invalid):
    entry, cloud, writes = tracker_entry
    cloud["test-0"][part][key] = invalid
    result = await editor(hass, entry, section, choice, expected_type=FlowResultType.ABORT)
    assert result["reason"] == "invalid_settings"
    assert all(write.await_count == 0 for write in writes)


@pytest.mark.parametrize("setting", ["profile", "ringtone", "led"])
@pytest.mark.parametrize("value", [None, "", "99", [], {}, True, 1.5])
async def test_invalid_personalization_cannot_open_an_edit_form(hass, tracker_entry, setting, value):
    entry, cloud, writes = tracker_entry
    cloud["test-0"]["commands"][setting] = value
    result = await editor(hass, entry, "audio", {"setting": setting}, expected_type=FlowResultType.ABORT)
    assert result["reason"] == "invalid_settings"
    assert all(write.await_count == 0 for write in writes)


async def test_absent_ringtone_default_and_temporary_led_are_not_written_on_open(hass, tracker_entry):
    entry, cloud, writes = tracker_entry
    del cloud["test-0"]["commands"]["ringtone"]
    result = await editor(hass, entry, "audio", {"setting": "ringtone"})
    assert suggested(result) == {"value": "0"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"value": "0"})
    assert result["reason"] == "settings_saved"
    cloud["test-0"]["commands"]["led"] = "2"
    result = await editor(hass, entry, "audio", {"setting": "led"})
    assert suggested(result) == {}
    assert all(write.await_count == 0 for write in writes)


@pytest.mark.parametrize("section,choice,submitted", [
    ("audio", {"setting": "ringtone"}, {"value": "1"}),
    ("audio", {"setting": "volume_ring"}, {"value": 2}),
    ("device", {"setting": "nickname"}, {"value": "Changed"}),
    ("contacts", {"contact": "sos_1"}, {"value": "+15555550102"}),
    ("schedules", {"schedule": "alarm_2"}, {"enabled": True, "time": "09:00", "weekdays": ["mon"]}),
])
async def test_unloading_while_editor_is_open_blocks_submission(hass, tracker_entry, section, choice, submitted):
    entry, _, writes = tracker_entry
    result = await editor(hass, entry, section, choice)
    await hass.config_entries.async_unload(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], submitted)
    assert result["reason"] == "integration_not_loaded"
    assert all(write.await_count == 0 for write in writes)


async def test_removed_tracker_or_unloaded_entry_cannot_save(hass, tracker_entry):
    entry, _, writes = tracker_entry
    result = await editor(hass, entry, "audio", {"setting": "ringtone"})
    entry.runtime_data.async_set_updated_data({})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"value": "1"})
    assert result["reason"] == "tracker_removed"
    assert all(write.await_count == 0 for write in writes)
    await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "tracker"})
    assert result["reason"] == "integration_not_loaded"


@pytest.mark.parametrize("failure,expected", [(MykiError("private-sentinel"), "cannot_connect"), (MykiAuthError("private-sentinel"), "invalid_auth")])
async def test_snapshot_failure_aborts_without_disclosing_errors(hass, tracker_entry, failure, expected):
    entry, _, writes = tracker_entry
    entry.runtime_data.client.app_data.side_effect = failure
    result = await editor(hass, entry, "audio", {"setting": "ringtone"}, expected_type=FlowResultType.ABORT)
    assert result["reason"] == expected
    assert "private-sentinel" not in str(result)
    assert all(write.await_count == 0 for write in writes)
    assert entry.data == {"email": "test@example.com", "password": "test-password"}
    if expected == "invalid_auth":
        await hass.async_block_till_done()
        assert hass.config_entries.flow.async_progress_by_handler("myki")


async def test_auth_failure_during_save_starts_reauth_without_retry(hass, tracker_entry):
    entry, _, writes = tracker_entry
    result = await editor(hass, entry, "audio", {"setting": "ringtone"})
    writes[0].side_effect = MykiAuthError("private-sentinel")
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"value": "1"})
    assert result["reason"] == "invalid_auth"
    assert writes[0].await_count == 1
    assert "private-sentinel" not in str(result)
    await hass.async_block_till_done()
    assert hass.config_entries.flow.async_progress_by_handler("myki")


@pytest.mark.parametrize("value", [True, 0, 7, 1.5, float("nan"), "2"])
async def test_volume_boundary_rejects_invalid_values_without_write(tracker_entry, value):
    entry, _, writes = tracker_entry
    with pytest.raises(MykiError, match="invalid volume"):
        await entry.runtime_data.async_set_volume("test-0", "volume_call", value, 6)
    assert all(write.await_count == 0 for write in writes)


async def test_noop_volume_and_snapshot_are_not_aliases(tracker_entry):
    entry, cloud, writes = tracker_entry
    snapshot = await entry.runtime_data.async_settings_snapshot("test-0")
    snapshot["commands"]["volume_ring"] = "1"
    assert cloud["test-0"]["commands"]["volume_ring"] == "4"
    assert entry.runtime_data.data["test-0"]["app"]["commands"]["volume_ring"] == "4"
    await entry.runtime_data.async_set_volume("test-0", "volume_ring", 4, 4)
    assert all(write.await_count == 0 for write in writes)


async def test_empty_zone_is_created_only_on_explicit_save(hass, tracker_entry):
    entry, cloud, writes = tracker_entry
    del cloud["test-0"]["settings"]["safe_zone_2"]
    result = await editor(hass, entry, "zones", {"zone": "safe_zone_2"})
    assert suggested(result) == {}
    assert all(write.await_count == 0 for write in writes)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {
        "name": "Example zone", "location": {"latitude": 11, "longitude": 21, "radius": 200}, "enabled": True, "ring_mode": "2",
    })
    assert result["reason"] == "settings_saved"
    assert json.loads(cloud["test-0"]["settings"]["safe_zone_2"]) == {"name": "Example zone", "lat": 11, "lon": 21, "radius": 0.2, "active": 1, "profile": 2}
    assert entry.options == {"scan_interval": 120}


async def test_reload_keeps_settings_in_cloud_not_ha_options(hass, tracker_entry):
    entry, cloud, writes = tracker_entry
    result = await editor(hass, entry, "audio", {"setting": "ringtone"})
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"value": "2"})
    assert result["reason"] == "settings_saved"
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert cloud["test-0"]["commands"]["ringtone"] == "2"
    result = await editor(hass, entry, "audio", {"setting": "ringtone"})
    assert suggested(result) == {"value": "2"}
    assert entry.options == {"scan_interval": 120}
    assert writes[0].await_count == 1
    assert hass.states.get("select.tracker_0_ringtone") is None


async def test_cleanup_removes_retired_controls_without_recreating_them(hass, tracker_entry):
    entry, cloud, writes = tracker_entry
    before = deepcopy(cloud)
    other = MockConfigEntry(domain="myki", data={})
    other.add_to_hass(hass)
    registry = er.async_get(hass)
    retired = []
    for domain, suffix in [("number", "volume_ring"), ("select", "ringtone"), ("switch", "status_led"), ("switch", "battery_save_mode"), ("text", "sos_1"), ("text", "whitelist_7"), ("text", "tracker_nickname"), ("text", "sim_phone")]:
        for wid in ("test-0", "removed-tracker"):
            entity = registry.async_get_or_create(domain, "myki", f"{wid}_{suffix}", config_entry=entry, disabled_by=er.RegistryEntryDisabler.USER)
            renamed = f"{domain}.renamed_{wid.replace('-', '_')}_{suffix}"
            registry.async_update_entity(entity.entity_id, name="Customized", new_entity_id=renamed)
            retired.append(renamed)
    flashlight = registry.async_get("switch.tracker_0_flashlight")
    untouched = registry.async_get_or_create("text", "myki", "another_sos_1", config_entry=other)
    for _ in range(2):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert all(registry.async_get(entity_id) is None for entity_id in retired)
        assert all(hass.states.get(entity_id) is None for entity_id in retired)
        assert registry.async_get(flashlight.entity_id) is not None
        assert registry.async_get(untouched.entity_id) is untouched
        assert not any(entity.domain in ("number", "select", "text") for entity in er.async_entries_for_config_entry(registry, entry.entry_id))
    assert cloud == before
    assert all(write.await_count == 0 for write in writes)
