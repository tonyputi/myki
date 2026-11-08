"""Event entities: SOS, low battery, safe zone enter/exit from the device log."""

import logging
import time
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity

_LOGGER = logging.getLogger(__name__)


def _epoch(timestamp: str) -> int | None:
    try:
        return int(timestamp)
    except (TypeError, ValueError):
        return None


def parse_events(raw_events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return [(event_name, timestamp)] oldest-first (best effort by timestamp)."""
    events = [(str(e.get("event_name")), str(e.get("timestamp"))) for e in raw_events]
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
        return sorted({name for name, _ in parse_events(self.coordinator.data[self.watch_id]["events"])})

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
            # the log window rotated past our marker: never replay old alarms
            fresh = []
            _LOGGER.debug("Event log rotated past the last seen marker; skipping backlog")
        for name, timestamp in fresh:
            try:
                triggered_at = dt_util.utc_from_timestamp(int(timestamp))
            except (ValueError, TypeError, OverflowError, OSError):
                triggered_at = None
            self._trigger_event(name, {"timestamp": timestamp, "triggered_at": triggered_at})
            # write per event: every event produces its own state transition
            self.async_write_ha_state()
        self._last_seen = events[-1]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(MykiEventEntity(coordinator, wid) for wid in coordinator.data)
