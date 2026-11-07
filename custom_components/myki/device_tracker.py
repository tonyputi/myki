"""device_tracker entities: GPS position and battery per watch."""

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity
from .utils import get_position, get_zone


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: MykiCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(MykiTrackerEntity(coordinator, wid) for wid in coordinator.data)


class MykiTrackerEntity(MykiEntity, TrackerEntity):
    """A MyKi tracker as a device tracker (named after its device)."""

    _attr_name = None

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_tracker"

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
    def battery_level(self) -> int | None:
        from .utils import get_battery

        return get_battery(self.app_data)

    @property
    def extra_state_attributes(self) -> dict:
        pos = get_position(self.app_data)
        current = self.app_data.get("current") or {}
        return {
            "zone": get_zone(self.app_data),
            "position_type": pos[3] if pos else None,  # GPS / WiFi / LBS
            "last_fix": current.get("takenat"),
        }
