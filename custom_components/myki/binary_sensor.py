"""Binary sensors: watch connectivity."""

import time

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity
from .utils import is_online


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
            MykiOnlineSensor(coordinator, wid),
            MykiFreshDataSensor(coordinator, wid),
        )
    )


class MykiOnlineSensor(MykiEntity, BinarySensorEntity):
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_online"

    @property
    def is_on(self) -> bool | None:
        return is_online(self.app_data)


class MykiFreshDataSensor(MykiEntity, BinarySensorEntity):
    """On while the device has reported to the cloud recently (30 min heuristic)."""

    _attr_translation_key = "fresh_data"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:cloud-check"

    FRESH_MAX_AGE_S = 30 * 60

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_fresh_data"

    @property
    def is_on(self) -> bool | None:
        try:
            last = int((self.app_data.get("settings") or {}).get("last_data_package"))
        except (TypeError, ValueError):
            return None
        return (time.time() - last) <= self.FRESH_MAX_AGE_S

    @property
    def extra_state_attributes(self) -> dict:
        raw = (self.app_data.get("settings") or {}).get("last_data_package")
        return {"last_data_package": raw}
