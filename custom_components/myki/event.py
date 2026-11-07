"""Event entities: SOS, low battery, safe zone enter/exit from the device log."""

import logging
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

# Names observed in the vendor app payload; the platform may emit others —
# unknown names are logged and skipped rather than guessed.
KNOWN_EVENT_TYPES = {"sos_alarm", "low_battery"}


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
        self._last_seen: tuple[str, str] | None = None

    @property
    def event_types(self) -> list[str]:
        names = {name for name, _ in parse_events(self.coordinator.data[self.watch_id]["events"])}
        return sorted(KNOWN_EVENT_TYPES | names)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # swallow the history backlog: only events newer than startup fire
        events = parse_events(self.coordinator.data[self.watch_id]["events"])
        self._last_seen = events[-1] if events else None

    def _handle_coordinator_update(self) -> None:
        events = parse_events(self.coordinator.data[self.watch_id]["events"])
        if self._last_seen is None or self._last_seen not in events:
            # first poll, or the log window rotated past our marker: never
            # replay old alarms, just move the marker to the newest event
            self._last_seen = events[-1] if events else None
            self.async_write_ha_state()
            return
        for name, timestamp in events[events.index(self._last_seen) + 1:]:
            if name not in self.event_types:
                _LOGGER.warning("Unknown MyKi event type skipped: %s", name)
                continue
            try:
                triggered_at = dt_util.utc_from_timestamp(int(timestamp))
            except (ValueError, TypeError, OverflowError, OSError):
                triggered_at = None
            self._trigger_event(name, {"timestamp": timestamp, "triggered_at": triggered_at})
        self._last_seen = events[-1]
        self.async_write_ha_state()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(MykiEventEntity(coordinator, wid) for wid in coordinator.data)
