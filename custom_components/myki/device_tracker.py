"""device_tracker entities: GPS position of each tracker, plus the find/call services."""

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
import voluptuous as vol

from .api import MykiError
from .const import SERVICE_FIND, SERVICE_MAKE_CALL
from .contacts import CONTACT_SLOTS
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity
from .settings import WEEKDAYS, read_group
from .utils import get_position, get_zone

MAKE_CALL_SCHEMA = {
    vol.Required("contact"): vol.In(CONTACT_SLOTS),
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MykiConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    platform = async_get_current_platform()
    platform.async_register_entity_service(SERVICE_FIND, None, "async_find")
    platform.async_register_entity_service(SERVICE_MAKE_CALL, MAKE_CALL_SCHEMA, "async_make_call")
    platform.async_register_entity_service("set_safe_zone", {
        vol.Required("zone"): vol.In(("safe_zone_1", "safe_zone_2")),
        vol.Optional("name"): str,
        vol.Optional("latitude"): vol.Coerce(float),
        vol.Optional("longitude"): vol.Coerce(float),
        vol.Optional("radius"): vol.Coerce(float),
        vol.Optional("enabled"): bool,
        vol.Optional("ring_mode"): vol.In(("1", "2", "3", "4")),
    }, "async_set_safe_zone")
    platform.async_register_entity_service("set_dnd", {
        vol.Required("enabled"): bool,
        vol.Optional("start"): str,
        vol.Optional("end"): str,
    }, "async_set_dnd")
    platform.async_register_entity_service("set_alarm", {
        vol.Required("alarm"): vol.In(("alarm_1", "alarm_2", "alarm_3")),
        vol.Optional("enabled"): bool,
        vol.Optional("time"): str,
        vol.Optional("weekdays"): [vol.In(WEEKDAYS)],
    }, "async_set_alarm")
    for service, method in (("power_off", "async_power_off"), ("restart", "async_restart")):
        platform.async_register_entity_service(service, {vol.Required("confirm"): bool}, method)
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

    async def async_make_call(self, contact: str) -> None:
        """Call the selected shared slot using its current cloud number."""
        try:
            await self.coordinator.async_call_contact(self.watch_id, contact)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi call failed: {err}") from err

    async def async_power_off(self, confirm: bool) -> None:
        await self._async_device_command("poweroff", confirm)

    async def async_restart(self, confirm: bool) -> None:
        await self._async_device_command("reset", confirm)

    async def _async_device_command(self, command: str, confirm: bool) -> None:
        try:
            await self.coordinator.async_device_command(self.watch_id, command, confirm)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi device command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    async def async_set_safe_zone(self, zone: str, **changes) -> None:
        await self._async_edit_group(zone, changes)

    async def async_set_dnd(self, enabled: bool, **changes) -> None:
        await self._async_edit_group("silencetime", {"enabled": enabled, **changes}, 0)

    async def async_set_alarm(self, alarm: str, **changes) -> None:
        await self._async_edit_group("remind", changes, int(alarm[-1]) - 1)

    async def _async_edit_group(self, key: str, changes: dict, index: int | None = None) -> None:
        try:
            cached = read_group(self.app_data, key)
            expected = cached[index] if index is not None else cached
            await self.coordinator.async_edit_setting_group(self.watch_id, key, changes, expected, index)
        except (MykiError, ValueError) as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi setting update failed: {err}") from err

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
