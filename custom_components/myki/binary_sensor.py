"""Binary sensors: watch connectivity."""

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity
from .utils import is_online


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(MykiOnlineSensor(coordinator, wid) for wid in coordinator.data)


class MykiOnlineSensor(MykiEntity, BinarySensorEntity):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_online"

    @property
    def is_on(self) -> bool | None:
        return is_online(self.app_data)
