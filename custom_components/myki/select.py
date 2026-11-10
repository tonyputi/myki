"""Global ring mode and ringtone shared with the MyKi app."""

from homeassistant.components.select import SelectEntity
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
        MykiPersonalizationSelect(entry.runtime_data, wid, key)
        for wid in entry.runtime_data.data for key in ("profile", "ringtone", "mode")
    )


class MykiPersonalizationSelect(MykiEntity, SelectEntity):
    """A cloud setting, with no restored or locally configured selection."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: MykiCoordinator, watch_id: str, key: str) -> None:
        super().__init__(coordinator, watch_id)
        self.key = key
        self._attr_translation_key = "ring_mode" if key == "profile" else key
        self._attr_unique_id = f"{watch_id}_{self._attr_translation_key}"
        self._attr_options = list(PERSONALIZATION_OPTIONS[key].values())

    @property
    def current_option(self) -> str | None:
        value = scalar_setting(self.app_data, self.key)
        return PERSONALIZATION_OPTIONS[self.key].get(value)

    async def async_select_option(self, option: str) -> None:
        value = next((key for key, name in PERSONALIZATION_OPTIONS[self.key].items() if name == option), None)
        if value is None:
            raise HomeAssistantError("Invalid MyKi personalization option")
        expected = scalar_setting(self.app_data, self.key)
        try:
            await self.coordinator.async_set_personalization(self.watch_id, self.key, value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi personalization update failed: {err}") from err
