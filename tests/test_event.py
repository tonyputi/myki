"""Regression tests for event-log polling without replaying historical alarms."""

from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
import pytest

from custom_components.myki.api import MykiClient
from custom_components.myki.coordinator import MykiCoordinator
from custom_components.myki.event import MykiEventEntity, parse_events

WATCH_ID = "test-tracker"


def event(timestamp: int, name: str = "sos_alarm") -> dict:
    return {"event_name": name, "timestamp": str(timestamp)}


@pytest.fixture
async def event_entity(hass: HomeAssistant):
    coordinator = MykiCoordinator(hass, AsyncMock(spec=MykiClient), 60)
    coordinator.data = {
        WATCH_ID: {"watch": {"nickname": "Test tracker"}, "app": {}, "events": [event(90)]}
    }
    with patch("custom_components.myki.event.time.time", return_value=100):
        entity = MykiEventEntity(coordinator, WATCH_ID)
    entity._swallow_backlog()
    with (
        patch.object(entity, "_trigger_event", wraps=entity._trigger_event) as trigger,
        patch.object(entity, "async_write_ha_state") as write,
    ):
        yield entity, coordinator, trigger, write


def update(entity, coordinator, events):
    coordinator.data[WATCH_ID]["events"] = events
    entity._handle_coordinator_update()


async def test_startup_does_not_replay_history(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [event(90)])
    trigger.assert_not_called()


async def test_empty_startup_accepts_only_new_events(event_entity):
    entity, coordinator, trigger, _ = event_entity
    entity._last_seen = None
    update(entity, coordinator, [event(99), event(101)])
    assert [call.args[1]["timestamp"] for call in trigger.call_args_list] == ["101"]


async def test_multiple_events_written_individually_and_not_repeated(event_entity):
    entity, coordinator, trigger, write = event_entity
    events = [event(120, "low_battery"), event(90), event(110)]
    update(entity, coordinator, events)
    assert [call.args[0] for call in trigger.call_args_list] == ["sos_alarm", "low_battery"]
    assert write.call_count == 2
    update(entity, coordinator, events)
    assert trigger.call_count == 2


async def test_repeated_sos_with_distinct_timestamps(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [event(90), event(110), event(120)])
    assert [call.args[1]["timestamp"] for call in trigger.call_args_list] == ["110", "120"]


async def test_empty_fetch_keeps_marker(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [])
    update(entity, coordinator, [event(90), event(110)])
    assert [call.args[1]["timestamp"] for call in trigger.call_args_list] == ["110"]


async def test_rotated_window_keeps_new_events_without_replaying_old(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [event(80), event(110), event(120, "low_battery")])
    assert [call.args[1]["timestamp"] for call in trigger.call_args_list] == ["110", "120"]
    update(entity, coordinator, [event(110), event(120, "low_battery")])
    assert trigger.call_count == 2


async def test_older_snapshot_does_not_move_marker_backwards(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [event(80)])
    update(entity, coordinator, [event(90), event(110)])
    assert [call.args[1]["timestamp"] for call in trigger.call_args_list] == ["110"]


async def test_reload_swallows_existing_history(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [event(90), event(110)])
    trigger.reset_mock()
    reloaded = MykiEventEntity(coordinator, WATCH_ID)
    reloaded._swallow_backlog()
    with (
        patch.object(reloaded, "_trigger_event", wraps=reloaded._trigger_event) as new_trigger,
        patch.object(reloaded, "async_write_ha_state"),
    ):
        update(reloaded, coordinator, [event(90), event(110)])
        new_trigger.assert_not_called()
        update(reloaded, coordinator, [event(90), event(110), event(120)])
        assert [call.args[1]["timestamp"] for call in new_trigger.call_args_list] == ["120"]


async def test_unordered_rotated_events_are_not_replayed(event_entity):
    entity, coordinator, trigger, _ = event_entity
    update(entity, coordinator, [{"event_name": "sos_alarm", "timestamp": "unverified-format"}])
    trigger.assert_not_called()
    update(entity, coordinator, [event(110)])
    assert trigger.call_args.args[1]["timestamp"] == "110"


async def test_removed_tracker_becomes_unavailable(event_entity):
    entity, coordinator, trigger, write = event_entity
    coordinator.data = {}
    entity._handle_coordinator_update()
    assert not entity.available
    assert entity.event_types == []
    trigger.assert_not_called()
    write.assert_called_once()


def test_malformed_records_are_ignored():
    assert parse_events([None, [], {}, {"event_name": None, "timestamp": "110"},
                         {"event_name": "sos_alarm"}, {"event_name": "", "timestamp": "110"},
                         {"event_name": "sos_alarm", "timestamp": []}, event(120), event(110)]) == [
        ("sos_alarm", "110"), ("sos_alarm", "120")
    ]
