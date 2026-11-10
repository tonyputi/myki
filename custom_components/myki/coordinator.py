"""DataUpdateCoordinator polling every tracker on the MyKi account."""

from asyncio import Lock
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MykiAuthError, MykiClient, MykiError
from .contacts import CONTACT_SLOTS, contact_numbers, normalize_phone

_LOGGER = logging.getLogger(__name__)

type MykiData = dict[str, dict[str, Any]]
type MykiConfigEntry = ConfigEntry[MykiCoordinator]


class MykiCoordinator(DataUpdateCoordinator[MykiData]):
    """data = {watch_id: {"watch": {id, nickname}, "app": {current, settings, commands}, "events": [...]}}."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: MykiClient,
        scan_interval: int,
        *,
        config_entry: MykiConfigEntry,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="MyKi",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self._contact_lock = Lock()

    async def _async_fetch(self) -> MykiData:
        data: MykiData = {}
        for w in await self.client.watches():
            watch_id = w["id"]
            app = await self.client.app_data(watch_id)
            try:
                events = await self.client.events(watch_id)
            except MykiAuthError:
                raise
            except MykiError as err:  # events are non-critical
                _LOGGER.debug("Could not fetch event history: %s", err)
                events = []
            data[watch_id] = {"watch": w, "app": app, "events": events}
        return data

    async def async_set_contact(self, watch_id: str, slot: str, value: str, expected: str) -> None:
        """Read/modify/write one slot; reject stale edits and verify cloud readback."""
        if slot not in CONTACT_SLOTS:
            raise MykiError("invalid contact slot")
        normalized = normalize_phone(value)
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            contacts = contact_numbers(app)
            if contacts[slot] != expected:
                self._publish_contacts(watch_id, app)
                raise MykiError("contact changed in MyKi; refresh and try again")
            if normalize_phone(contacts[slot]) == normalized:
                self._publish_contacts(watch_id, app)
                return
            if str((app.get("settings") or {}).get("online")) != "1":
                raise MykiError("tracker is offline; contact was not changed")
            affected = [slot]
            if slot.startswith("sos_"):
                await self.client.set_sos_number(watch_id, int(slot.removeprefix("sos_")), normalized)
            else:
                index = int(slot.removeprefix("whitelist_"))
                group = (index - 1) // 5 + 1
                if f"whitelist_{group}" not in (app.get("commands") or {}):
                    raise MykiError("contact group is missing; refresh before editing")
                affected = [f"whitelist_{i}" for i in range((group - 1) * 5 + 1, group * 5 + 1)]
                phones = [contacts[key] for key in affected]
                phones[(index - 1) % 5] = normalized
                await self.client.set_whitelist(watch_id, group, phones)
            confirmed = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, confirmed)
            readback = contact_numbers(confirmed)
            if any(normalize_phone(readback[key]) != (normalized if key == slot else normalize_phone(contacts[key])) for key in affected):
                raise MykiError("contact update was not confirmed by MyKi; refresh before retrying")

    def _publish_contacts(self, watch_id: str, app: dict[str, Any]) -> None:
        """Publish cloud data, never the requested value optimistically."""
        if watch_id in self.data:
            self.async_set_updated_data({**self.data, watch_id: {**self.data[watch_id], "app": app}})

    async def async_call_contact(self, watch_id: str, slot: str | None = None, *, phone: str | None = None) -> None:
        """Resolve the slot again immediately before calling; never cache its number."""
        if slot is not None and slot not in CONTACT_SLOTS:
            raise MykiError("invalid contact slot")
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, app)
            contacts = contact_numbers(app)
            if slot is None and phone:
                normalized = normalize_phone(phone)
                slot = next((key for key in CONTACT_SLOTS if normalize_phone(contacts[key]) == normalized), None)
            if slot is None:
                raise MykiError("choose an existing shared contact")
            number = contacts[slot]
            if not number:
                raise MykiError("contact slot is empty")
            await self.client.make_call(watch_id, number)

    async def _async_update_data(self) -> MykiData:
        try:
            async with self._contact_lock:
                return await self._async_fetch()
        except MykiAuthError as err:
            raise ConfigEntryAuthFailed() from err
        except MykiError as err:
            raise UpdateFailed(str(err)) from err
