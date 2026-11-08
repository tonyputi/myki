"""Config entities: ring and call volume sliders."""

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .const import DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity


def _volume(app_data: dict, key: str) -> int | None:
    try:
        return int((app_data.get("commands") or {}).get(key))
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        entity
        for wid in coordinator.data
        for entity in (
            MykiRingVolume(coordinator, wid),
            MykiCallVolume(coordinator, wid),
        )
    )


class MykiVolumeEntity(MykiEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.SLIDER
    _attr_native_step = 1

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_{self._volume_key}"

    @property
    def native_value(self) -> int | None:
        return _volume(self.app_data, self._volume_key)


class MykiRingVolume(MykiVolumeEntity):
    _attr_translation_key = "ring_volume"
    _attr_native_min_value = 1
    _attr_native_max_value = 4  # vendor app seekbar max 3 + 1
    _volume_key = "volume_ring"

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_ring_volume(self.watch_id, int(value))
        except MykiError as err:
            raise HomeAssistantError(f"MyKi ring volume failed: {err}") from err
        await self.coordinator.async_request_refresh()


class MykiCallVolume(MykiVolumeEntity):
    _attr_translation_key = "call_volume"
    _attr_native_min_value = 1
    _attr_native_max_value = 6  # vendor app seekbar max 5 + 1
    _volume_key = "volume_call"

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_call_volume(self.watch_id, int(value))
        except MykiError as err:
            raise HomeAssistantError(f"MyKi call volume failed: {err}") from err
        await self.coordinator.async_request_refresh()
