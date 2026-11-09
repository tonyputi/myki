"""The MyKi integration: Allterco MyKi GPS trackers in Home Assistant."""

import logging

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MykiClient, MykiError
from .const import (
    CONF_CALL_CONTACTS,
    CONF_CALL_ME_NUMBER,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
)
from .contacts import CONTACT_SLOTS, contact_numbers, normalize_phone
from .coordinator import MykiConfigEntry, MykiCoordinator

PLATFORMS = ("binary_sensor", "button", "device_tracker", "event", "number", "select", "sensor", "text")
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: MykiConfigEntry) -> None:
    client = MykiClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = MykiCoordinator(
        hass,
        client,
        entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        config_entry=entry,
    )
    await coordinator.async_config_entry_first_refresh()

    if CONF_CALL_ME_NUMBER in entry.options:
        options = dict(entry.options)
        legacy = options.pop(CONF_CALL_ME_NUMBER)
        targets = dict(options.get(CONF_CALL_CONTACTS, {}))
        for wid, data in coordinator.data.items():
            if wid in targets:
                continue
            try:
                numbers = contact_numbers(data["app"])
                match = next((slot for slot in CONTACT_SLOTS if legacy and normalize_phone(numbers[slot]) == normalize_phone(legacy)), None)
            except MykiError:
                match = None
            if match:
                targets[wid] = match
            elif legacy:
                _LOGGER.warning("Legacy Call me number has no matching shared contact; choose a contact slot on the device")
        options[CONF_CALL_CONTACTS] = targets
        hass.config_entries.async_update_entry(entry, options=options)

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: MykiConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MykiConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
