"""Shared MyKi entity base: device info + coordinator link."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MykiCoordinator
from .utils import get_model

# Keep established entity IDs independent of translated display-name group prefixes.
_ENTITY_OBJECT_NAMES = {
    "safe_zone_1": "Safe zone 1",
    "safe_zone_2": "Safe zone 2",
    "dnd": "Do not disturb",
    "alarm_1": "Alarm 1",
    "alarm_2": "Alarm 2",
    "alarm_3": "Alarm 3",
    "gsm_signal": "GSM signal",
    "gps_satellites": "GPS satellites",
    "wifi_networks": "WiFi networks",
    "base_stations": "Cell towers",
    "rtt_seconds_left": "Live tracking seconds left",
    "fresh_data": "Fresh data",
    "online": "Online",
    "flashlight": "Flashlight",
}


class MykiEntity(CoordinatorEntity[MykiCoordinator]):
    """Base entity for one MyKi tracker."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator)
        self.watch_id = watch_id
        data = coordinator.data[watch_id]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, watch_id)},
            name=data["watch"].get("nickname") or watch_id,
            manufacturer="Allterco",
            model=get_model(data["app"]),
            sw_version=(data["app"].get("settings") or {}).get("fw"),
        )

    @property
    def suggested_object_id(self) -> str | None:
        """Keep the original object-name base when regrouping display names."""
        return _ENTITY_OBJECT_NAMES.get(self.translation_key, super().suggested_object_id)

    @property
    def app_data(self) -> dict[str, Any]:
        """The tracker's app-data payload ({current, settings, commands})."""
        return self.coordinator.data.get(self.watch_id, {}).get("app", {})

    @property
    def available(self) -> bool:
        """Unavailable once the tracker disappears from the account."""
        return super().available and self.watch_id in self.coordinator.data
