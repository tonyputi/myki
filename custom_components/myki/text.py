"""Shared SOS and whitelist slots, stored only in the MyKi cloud."""

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


class MykiContact(MykiEntity, TextEntity):
    """One app-visible contact slot; no optimistic or restored phone numbers."""

    _attr_entity_category = EntityCategory.CONFIG
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
