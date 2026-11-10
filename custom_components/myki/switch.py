"""Cloud-backed status LED, flashlight and battery saving switches."""

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .const import PERSONALIZATION_OPTIONS
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity
from .settings import scalar_setting


async def async_setup_entry(
    hass: HomeAssistant, entry: MykiConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        MykiSettingSwitch(entry.runtime_data, wid, key)
        for wid in entry.runtime_data.data for key in ("led", "flashlight", "battery_save_mode")
    )


class MykiSettingSwitch(MykiEntity, SwitchEntity):
    """One existing app setting, never a restored or optimistic preference."""

    def __init__(self, coordinator: MykiCoordinator, watch_id: str, key: str) -> None:
        super().__init__(coordinator, watch_id)
        self.key = key
        self._attr_translation_key = "status_led" if key == "led" else key
        self._attr_unique_id = f"{watch_id}_{self._attr_translation_key}"
        if key != "flashlight":
            self._attr_entity_category = EntityCategory.CONFIG
            self._attr_entity_registry_enabled_default = False

    @property
    def is_on(self) -> bool | None:
        value = scalar_setting(self.app_data, self.key)
        if self.key == "flashlight" and value == "0":
            return False
        state = PERSONALIZATION_OPTIONS[self.key].get(value)
        return None if state is None else state == "on"

    async def async_turn_on(self, **kwargs) -> None:
        await self._async_set_status("on")

    async def async_turn_off(self, **kwargs) -> None:
        await self._async_set_status("off")

    async def _async_set_status(self, state: str) -> None:
        value = next(raw for raw, name in PERSONALIZATION_OPTIONS[self.key].items() if name == state)
        expected = scalar_setting(self.app_data, self.key)
        try:
            await self.coordinator.async_set_personalization(self.watch_id, self.key, value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi setting update failed: {err}") from err
