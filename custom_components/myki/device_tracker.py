"""device_tracker entities: GPS position of each tracker, plus the find/call services."""

import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
import voluptuous as vol

from .api import MykiError
from .const import ATTR_PHONE, SERVICE_FIND, SERVICE_MAKE_CALL
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity
from .utils import authorized_phones, get_position, get_zone

_LOGGER = logging.getLogger(__name__)

MAKE_CALL_SCHEMA = {vol.Required(ATTR_PHONE): str}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MykiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    platform = async_get_current_platform()
    platform.async_register_entity_service(SERVICE_FIND, None, "async_find")
    platform.async_register_entity_service(SERVICE_MAKE_CALL, MAKE_CALL_SCHEMA, "async_make_call")
    async_add_entities(MykiTrackerEntity(coordinator, wid) for wid in coordinator.data)


class MykiTrackerEntity(MykiEntity, TrackerEntity):
    """A MyKi tracker as a device tracker (named after its device)."""

    _attr_name = None
    _attr_icon = "mdi:crosshairs-gps"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_tracker"

    async def async_find(self) -> None:
        """Entity service `myki.find`: ring the tracker."""
        try:
            await self.coordinator.client.find(self.watch_id)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi find failed: {err}") from err

    async def async_make_call(self, phone: str) -> None:
        """Entity service `myki.make_call`: the tracker calls the given number."""
        if phone not in authorized_phones(self.app_data):
            # the device refuses numbers outside SOS/whitelist
            _LOGGER.warning(
                "%s is not in the tracker's SOS/whitelist; the call may be refused", phone
            )
        try:
            await self.coordinator.client.make_call(self.watch_id, phone)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi call failed: {err}") from err

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        pos = get_position(self.app_data)
        return pos[0] if pos else None

    @property
    def longitude(self) -> float | None:
        pos = get_position(self.app_data)
        return pos[1] if pos else None

    @property
    def location_accuracy(self) -> int:
        pos = get_position(self.app_data)
        return pos[2] if pos else 0

    @property
    def extra_state_attributes(self) -> dict:
        pos = get_position(self.app_data)
        current = self.app_data.get("current") or {}
        settings = self.app_data.get("settings") or {}
        return {
            "zone": get_zone(self.app_data),
            "position_type": pos[3] if pos else None,  # GPS / WiFi / LBS
            "last_fix": current.get("takenat"),
            "gps_satellites": current.get("gpsSatelites"),
            "base_stations": current.get("baseStations"),
            "wifi_networks": len(current.get("wifi") or []),
            "speed": current.get("speed"),
            "direction": current.get("direction"),
            "steps_all": (current.get("steps") or {}).get("allSteps"),
            "mode": settings.get("mode"),
            "phone": settings.get("msisdn"),
            "operator": settings.get("mcc_mnc"),
        }
