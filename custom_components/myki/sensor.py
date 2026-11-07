"""Sensors: safe-zone state, battery and steps per watch."""

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity
from .utils import (
    AWAY,
    distance_meters,
    get_battery,
    get_gsm_signal,
    get_position,
    get_steps_today,
    get_zone,
)


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
            MykiZoneSensor(coordinator, wid),
            MykiBatterySensor(coordinator, wid),
            MykiStepsSensor(coordinator, wid),
            MykiGsmSignalSensor(coordinator, wid),
        )
    )


class MykiZoneSensor(MykiEntity, SensorEntity):
    """Which safe zone (from the watch configuration) the kid is in."""

    _attr_translation_key = "zone"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_icon = "mdi:map-marker-radius"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_zone"

    @property
    def native_value(self) -> str | None:
        return get_zone(self.app_data)

    @property
    def options(self) -> list[str] | None:
        zones = []
        settings = self.app_data.get("settings") or {}
        import json

        for key in sorted(k for k in settings if k.startswith("safe_zone")):
            try:
                zone = json.loads(settings[key])
                if int(zone.get("active", 0)):
                    zones.append(str(zone.get("name") or key).strip())
            except (ValueError, KeyError, TypeError):
                continue
        return [*zones, AWAY]

    @property
    def extra_state_attributes(self) -> dict:
        import json

        attrs: dict = {}
        pos = get_position(self.app_data)
        settings = self.app_data.get("settings") or {}
        for key in sorted(k for k in settings if k.startswith("safe_zone")):
            try:
                zone = json.loads(settings[key])
                name = str(zone.get("name") or key).strip()
                attrs[f"distance_to_{name}"] = round(
                    distance_meters(pos[0], pos[1], float(zone["lat"]), float(zone["lon"]))
                )
            except (ValueError, KeyError, TypeError):
                continue
        return attrs


class MykiBatterySensor(MykiEntity, SensorEntity):
    _attr_translation_key = "battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_battery"

    @property
    def native_value(self) -> int | None:
        return get_battery(self.app_data)


class MykiStepsSensor(MykiEntity, SensorEntity):
    _attr_translation_key = "steps_today"
    _attr_icon = "mdi:shoe-print"
    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_steps_today"

    @property
    def native_value(self) -> int | None:
        return get_steps_today(self.app_data)


class MykiGsmSignalSensor(MykiEntity, SensorEntity):
    _attr_translation_key = "gsm_signal"
    _attr_icon = "mdi:signal"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_gsm_signal"

    @property
    def native_value(self) -> int | None:
        return get_gsm_signal(self.app_data)
