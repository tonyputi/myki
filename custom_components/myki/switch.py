"""Status LED configuration shared with the MyKi app."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MykiConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(MykiStatusLed(entry.runtime_data, wid) for wid in entry.runtime_data.data)


class MykiStatusLed(MykiEntity, SwitchEntity):
    """Enable default status indication, not the temporary LED-party mode."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "status_led"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_status_led"

    @property
    def is_on(self) -> bool | None:
        value = str((self.app_data.get("commands") or {}).get("led"))
        return {"0": False, "1": True}.get(value)

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_status("1")

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_status("0")

    async def _async_set_status(self, value: str) -> None:
        expected = str((self.app_data.get("commands") or {}).get("led"))
        try:
            await self.coordinator.async_set_personalization(self.watch_id, "led", value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi status LED update failed: {err}") from err
