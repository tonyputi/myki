"""Buttons on the device page: find (ring) and call me."""

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import MykiError
from .const import CONF_CALL_ME_NUMBER, DOMAIN
from .coordinator import MykiCoordinator
from .entity import MykiEntity


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
            MykiFindButton(coordinator, wid),
            MykiCallMeButton(coordinator, wid),
        )
    )


class MykiFindButton(MykiEntity, ButtonEntity):
    _attr_translation_key = "find"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_find"

    async def async_press(self) -> None:
        try:
            await self.coordinator.client.find(self.watch_id)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi find failed: {err}") from err


class MykiCallMeButton(MykiEntity, ButtonEntity):
    """Makes the tracker call the number configured in the integration options."""

    _attr_translation_key = "call_me"

    def __init__(self, coordinator: MykiCoordinator, watch_id: str) -> None:
        super().__init__(coordinator, watch_id)
        self._attr_unique_id = f"{watch_id}_call_me"

    @property
    def available(self) -> bool:
        return (
            super().available
            and bool(self.coordinator.config_entry.options.get(CONF_CALL_ME_NUMBER))
        )

    async def async_press(self) -> None:
        phone = self.coordinator.config_entry.options.get(CONF_CALL_ME_NUMBER)
        if not phone:
            raise HomeAssistantError("No 'call me' number configured in the integration options")
        try:
            await self.coordinator.client.make_call(self.watch_id, phone)
        except MykiError as err:
            raise HomeAssistantError(f"MyKi call failed: {err}") from err
