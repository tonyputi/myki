"""The MyKi integration: Allterco MyKi GPS trackers in Home Assistant."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service import async_extract_entity_ids
import voluptuous as vol

from .api import MykiClient, MykiError
from .const import (
    ATTR_PHONE,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_FIND,
    SERVICE_MAKE_CALL,
)
from .coordinator import MykiCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ("binary_sensor", "button", "device_tracker", "event", "number", "sensor")

MAKE_CALL_SCHEMA = vol.Schema({vol.Required(ATTR_PHONE): str})


def _resolve_watch(hass: HomeAssistant, entity_id: str) -> tuple[MykiCoordinator, str] | None:
    """Return (coordinator, watch_id) for an entity (unique_id: <watch_id>_<suffix>)."""
    entry = er.async_get(hass).async_get(entity_id)
    if entry is None or not entry.unique_id:
        return None
    watch_id = entry.unique_id.rsplit("_", 1)[0]
    for coordinator in hass.data[DOMAIN].values():
        if watch_id in coordinator.data:
            return coordinator, watch_id
    return None


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_FIND):
        return

    async def handle_find(call: ServiceCall) -> None:
        for entity_id in await async_extract_entity_ids(hass, call):
            resolved = _resolve_watch(hass, entity_id)
            if resolved is not None:
                coordinator, watch_id = resolved
                await coordinator.client.find(watch_id)

    async def handle_make_call(call: ServiceCall) -> None:
        phone = call.data[ATTR_PHONE]
        for entity_id in await async_extract_entity_ids(hass, call):
            resolved = _resolve_watch(hass, entity_id)
            if resolved is None:
                continue
            coordinator, watch_id = resolved
            from .utils import authorized_phones

            if phone not in authorized_phones(coordinator.data[watch_id]["app"]):
                _LOGGER.warning(
                    "%s is not in the watch's SOS/whitelist; the call may be refused",
                    phone,
                )
            await coordinator.client.make_call(watch_id, phone)

    hass.services.async_register(DOMAIN, SERVICE_FIND, handle_find)
    hass.services.async_register(DOMAIN, SERVICE_MAKE_CALL, handle_make_call, schema=MAKE_CALL_SCHEMA)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    client = MykiClient(
        async_get_clientsession(hass), entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD]
    )
    coordinator = MykiCoordinator(
        hass, client, entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except MykiError as err:
        raise ConfigEntryNotReady(f"MyKi setup failed: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    _register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded
