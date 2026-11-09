"""Event entities: SOS, low battery, safe zone enter/exit from the device log."""

import logging
import time
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity

_LOGGER = logging.getLogger(__name__)


def _epoch(timestamp: str) -> int | None:
    try:
        return int(timestamp)
    except (TypeError, ValueError):
        return None


def parse_events(raw_events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return [(event_name, timestamp)] oldest-first (best effort by timestamp)."""
    events = []
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        name = event.get("event_name")
        timestamp = event.get("timestamp")
        if not isinstance(name, str) or not name.strip() or type(timestamp) not in (str, int):
            continue
        if not str(timestamp).strip():
            continue
        events.append((name, str(timestamp)))
    try:
        return sorted(events, key=lambda ev: int(ev[1]))
    except (ValueError, TypeError):
        return events


class MykiEventEntity(MykiEntity, EventEntity):
    """Fires an HA event whenever a new device event appears in the log."""

    _attr_translation_key = "events"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_events"
        self._initialized = False
        self._last_seen: tuple[str, str] | None = None
        self._started_epoch = time.time()

    @property
    def event_types(self) -> list[str]:
        """Known names plus every name currently in the log (open set)."""
        events = self.coordinator.data.get(self.watch_id, {}).get("events", [])
        return sorted({name for name, _ in parse_events(events)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._swallow_backlog()

    def _swallow_backlog(self) -> None:
        """Mark the existing history as seen: only future events fire."""
        events = parse_events(self.coordinator.data[self.watch_id]["events"])
        if events:
            self._last_seen = events[-1]
        self._initialized = True

    def _handle_coordinator_update(self) -> None:
        if self.watch_id not in self.coordinator.data:
            self.async_write_ha_state()
            return
        events = parse_events(self.coordinator.data[self.watch_id]["events"])
        if not self._initialized:
            self._swallow_backlog()
            self.async_write_ha_state()
            return
        if not events:  # transient fetch failure: keep the marker, fire nothing
            self.async_write_ha_state()
            return
        if self._last_seen is not None and self._last_seen in events:
            fresh = events[events.index(self._last_seen) + 1:]
        elif self._last_seen is None:
            # history was empty at startup: only events newer than our start count
            fresh = [
                ev for ev in events
                if _epoch(ev[1]) is None or _epoch(ev[1]) > self._started_epoch
            ]
        else:
            # shortcut: tied/non-numeric timestamps cannot be ordered after rotation;
            # require a verified vendor event ID/format before handling those cases.
            last_epoch = _epoch(self._last_seen[1])
            fresh = [
                ev for ev in events
                if last_epoch is not None
                and (epoch := _epoch(ev[1])) is not None
                and epoch > last_epoch
            ]
            _LOGGER.debug("Event log rotated past the last seen marker")
        for name, timestamp in fresh:
            try:
                triggered_at = dt_util.utc_from_timestamp(int(timestamp))
            except (ValueError, TypeError, OverflowError, OSError):
                triggered_at = None
            self._trigger_event(name, {"timestamp": timestamp, "triggered_at": triggered_at})
            # write per event: every event produces its own state transition
            self.async_write_ha_state()
        if fresh:
            self._last_seen = fresh[-1]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MykiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(MykiEventEntity(coordinator, wid) for wid in coordinator.data)
