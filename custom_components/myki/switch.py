"""Temporary flashlight command; persistent settings live in the configuration flow."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity
from .settings import scalar_setting


async def async_setup_entry(
    hass: HomeAssistant, entry: MykiConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(MykiFlashlight(entry.runtime_data, wid) for wid in entry.runtime_data.data)


class MykiFlashlight(MykiEntity, SwitchEntity):
    """The app's temporary LED command, not a second editor for status LED preferences."""

    _attr_translation_key = "flashlight"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_flashlight"

    @property
    def is_on(self) -> bool | None:
        value = scalar_setting(self.app_data, "flashlight")
        return value == "2" if value in ("0", "1", "2") else None

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_status("2")

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_status("1")

    async def _async_set_status(self, value: str) -> None:
        expected = scalar_setting(self.app_data, "flashlight")
        try:
            await self.coordinator.async_set_personalization(self.watch_id, "flashlight", value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi flashlight command failed: {err}") from err
