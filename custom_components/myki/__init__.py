"""The MyKi integration: Allterco MyKi GPS trackers in Home Assistant."""

from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import MykiClient
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .coordinator import MykiConfigEntry, MykiCoordinator

PLATFORMS = ("binary_sensor", "button", "device_tracker", "event", "number", "select", "sensor", "switch", "text")


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

    # Remove retired HA-only calling preferences and entities, never cloud contacts.
    options = {key: value for key, value in entry.options.items() if key not in ("call_me_number", "call_contacts")}
    if options != entry.options:
        hass.config_entries.async_update_entry(entry, options=options)
    registry = er.async_get(hass)
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        if entity.platform == "myki" and (
            (entity.domain == "select" and entity.unique_id.endswith("_call_contact"))
            or (entity.domain == "button" and entity.unique_id.endswith("_call_me"))
        ):
            registry.async_remove(entity.entity_id)

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def _async_reload_entry(hass: HomeAssistant, entry: MykiConfigEntry) -> None:
    """Reload the entry when its options change (e.g. scan interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MykiConfigEntry) -> None:
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
