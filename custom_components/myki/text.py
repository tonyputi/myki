"""Shared SOS and whitelist slots, stored only in the MyKi cloud."""

import re

from homeassistant.components.text import TextEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .contacts import CONTACT_SLOTS, contact_numbers
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MykiConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        MykiContact(entry.runtime_data, wid, slot)
        for wid in entry.runtime_data.data for slot in CONTACT_SLOTS
    )
    async_add_entities(
        MykiTrackerDetail(entry.runtime_data, wid, key)
        for wid in entry.runtime_data.data for key in ("nickname", "msisdn")
    )


class MykiTrackerDetail(MykiEntity, TextEntity):
    """Nickname or SIM number from the app's paired tracker-details write."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_native_min = 1

    def __init__(self, coordinator: MykiCoordinator, watch_id: str, key: str) -> None:
        super().__init__(coordinator, watch_id)
        self.key = key
        self._attr_translation_key = "tracker_nickname" if key == "nickname" else "sim_phone"
        self._attr_unique_id = f"{watch_id}_{self._attr_translation_key}"
        self._attr_native_max = 255 if key == "nickname" else 32
        if key == "msisdn":
            self._attr_pattern = r"\+?[0-9]+"

    @property
    def native_value(self) -> str | None:
        value = (self.app_data.get("settings") or {}).get(self.key)
        if not isinstance(value, str) or not value.strip() or len(value) > self._attr_native_max:
            return None
        if self.key == "msisdn" and not re.fullmatch(self._attr_pattern, value):
            return None
        return value

    async def async_set_value(self, value: str) -> None:
        expected = self.native_value
        if expected is None:
            raise HomeAssistantError("MyKi tracker details are invalid; refresh before editing")
        try:
            await self.coordinator.async_set_tracker_detail(self.watch_id, self.key, value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi tracker details update failed: {err}") from err


class MykiContact(MykiEntity, TextEntity):
    """One app-visible contact slot; no optimistic or restored phone numbers."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_native_min = 0
    _attr_native_max = 32
    _attr_pattern = r"\+?[0-9]*"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str, slot: str) -> None:
        super().__init__(coordinator, watch_id)
        self.slot = slot
        self._attr_unique_id = f"{watch_id}_{slot}"
        self._attr_translation_key = slot

    @property
    def native_value(self) -> str | None:
        try:
            return contact_numbers(self.app_data)[self.slot]
        except MykiError:
            return None

    async def async_set_value(self, value: str) -> None:
        expected = self.native_value
        if expected is None:
            raise HomeAssistantError("MyKi contact data is invalid; refresh before editing")
        try:
            await self.coordinator.async_set_contact(self.watch_id, self.slot, value, expected)
        except MykiError as err:
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"MyKi contact update failed: {err}") from err
