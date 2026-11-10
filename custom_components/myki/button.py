"""Buttons on the device page: find (ring) and live tracking."""

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MykiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        entity
        for wid in coordinator.data
        for entity in (
            MykiFindButton(coordinator, wid),
            MykiLiveTrackingButton(coordinator, wid),
        )
    )


class MykiFindButton(MykiEntity, ButtonEntity):
    _attr_translation_key = "find"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_find"

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.find(self.watch_id)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi find failed: {err}") from err


class MykiLiveTrackingButton(MykiEntity, ButtonEntity):
    """Starts a 10-minute real-time tracking window (device reports faster)."""

    _attr_translation_key = "live_tracking"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_live_tracking"

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.start_rtt(self.watch_id, 10)
            await self.coordinator.async_request_refresh()
        except MykiError as err:
            raise HomeAssistantError(f"MyKi live tracking failed: {err}") from err
