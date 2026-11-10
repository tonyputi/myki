"""Choose a shared contact slot for the existing Call me button."""

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_CALL_CONTACTS
from .contacts import CONTACT_SLOTS
from .coordinator import MykiConfigEntry, MykiCoordinator
from .entity import MykiEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: MykiConfigEntry, async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(MykiCallContact(entry.runtime_data, wid) for wid in entry.runtime_data.data)


class MykiCallContact(MykiEntity, SelectEntity):
    """Persist a slot reference, never a second copy of a contact number."""

    _attr_translation_key = "call_contact"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = ["none", *CONTACT_SLOTS]

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_call_contact"

    @property
    def current_option(self) -> str:
        return self.coordinator.config_entry.options.get(CONF_CALL_CONTACTS, {}).get(self.watch_id, "none")

    async def async_select_option(self, option: str) -> None:
        entry = self.coordinator.config_entry
        contacts = {**entry.options.get(CONF_CALL_CONTACTS, {}), self.watch_id: option}
        self.hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_CALL_CONTACTS: contacts})
