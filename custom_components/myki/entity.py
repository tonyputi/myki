"""Shared MyKi entity base: device info + coordinator link."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MykiCoordinator


class MykiEntity(CoordinatorEntity[MykiCoordinator]):
    """Base entity for one MyKi watch."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator)
        self.watch_id = watch_id
        data = coordinator.data[watch_id]
        settings = data["app"].get("settings") or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, watch_id)},
            name=data["watch"].get("nickname") or watch_id,
            manufacturer="Allterco",
            model="MyKi Spot watch",
            sw_version=str(settings.get("fw") or None),
        )

    @property
    def app_data(self) -> dict[str, Any]:
        """The watch's app-data payload ({current, settings, commands})."""
        return self.coordinator.data[self.watch_id]["app"]

    @property
    def nickname(self) -> str:
        return self.coordinator.data[self.watch_id]["watch"].get("nickname") or self.watch_id
