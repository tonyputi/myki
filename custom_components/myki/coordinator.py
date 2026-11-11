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
from .const import PERSONALIZATION_OPTIONS
from .contacts import CONTACT_SLOTS, contact_numbers, normalize_phone
from .settings import edit_group, read_group, scalar_setting

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

    async def async_set_personalization(self, watch_id: str, key: str, value: str, expected: str) -> None:
        """Write one shared app setting and require matching cloud readback."""
        if key not in PERSONALIZATION_OPTIONS or value not in PERSONALIZATION_OPTIONS[key]:
            raise MykiError("invalid personalization setting")
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, app)
            current = scalar_setting(app, key)
            if current not in PERSONALIZATION_OPTIONS[key] and not (
                (key == "led" and current == "2") or (key == "flashlight" and current == "0")
            ):
                raise MykiError("personalization data is invalid; refresh before editing")
            if current != expected:
                raise MykiError("setting changed in MyKi; refresh and try again")
            if current == value or (key == "flashlight" and value == "1" and current == "0"):
                return
            if str((app.get("settings") or {}).get("online")) != "1":
                raise MykiError("tracker is offline; setting was not changed")
            protected = {
                (section, field): val
                for section in ("settings", "commands")
                for field, val in (app.get(section) or {}).items()
                if field.startswith(("safe_zone_", "sos_phone_", "whitelist_"))
                or field in ("silencetime", "remind", "profile", "ringtone", "volume_ring", "volume_call", "led", "battery_save_mode", "nickname", "msisdn")
            } if key == "mode" else {}
            await self.client.set_personalization(watch_id, key, value)
            confirmed = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, confirmed)
            if scalar_setting(confirmed, key) != value:
                raise MykiError("setting update was not confirmed by MyKi; refresh before retrying")
            if any((confirmed.get(section) or {}).get(field) != val for (section, field), val in protected.items()):
                raise MykiError("mode changed other configuration; inspect MyKi before continuing")

    async def async_edit_setting_group(
        self, watch_id: str, key: str, changes: dict, expected: dict | str,
        index: int | None = None,
    ) -> None:
        """Read/modify/write one app setting; preserve freshly read sibling slots."""
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, app)
            try:
                current = read_group(app, key)
                if index is not None and (isinstance(index, bool) or not isinstance(index, int) or not isinstance(current, list) or not 0 <= index < len(current)):
                    raise ValueError("invalid schedule slot")
                selected = current[index] if index is not None else current
                if selected != expected:
                    raise ValueError("setting changed in MyKi; refresh and try again")
                requested = edit_group(key, current, changes, index)
            except (ValueError, TypeError, OverflowError) as err:
                raise MykiError(str(err)) from None
            if requested == current:
                return
            if str((app.get("settings") or {}).get("online")) != "1":
                raise MykiError("tracker is offline; setting was not changed")
            await self.client.set_setting_group(watch_id, key, requested)
            confirmed = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, confirmed)
            try:
                readback = read_group(confirmed, key)
            except ValueError:
                raise MykiError("setting readback is invalid; refresh before retrying") from None
            if readback != requested:
                raise MykiError("setting update was not confirmed by MyKi; refresh before retrying")

    async def async_set_tracker_detail(self, watch_id: str, key: str, value: str, expected: str) -> None:
        """Edit one cloud metadata field, preserving the freshly read paired field."""
        if key not in ("nickname", "msisdn"):
            raise MykiError("invalid tracker detail")
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, app)
            settings = app.get("settings") or {}
            details = {field: settings.get(field) for field in ("nickname", "msisdn")}
            if details[key] != expected:
                raise MykiError("tracker details changed in MyKi; refresh and try again")
            if details[key] == value:
                return
            if str(settings.get("online")) != "1":
                raise MykiError("tracker is offline; details were not changed")
            details[key] = value
            await self.client.set_tracker_details(watch_id, details["nickname"], details["msisdn"])
            confirmed = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, confirmed)
            if any((confirmed.get("settings") or {}).get(field) != requested for field, requested in details.items()):
                raise MykiError("tracker details were not confirmed by MyKi; refresh before retrying")

    async def async_device_command(self, watch_id: str, command: str, confirm: bool) -> None:
        """Require explicit acknowledgement; API acceptance is not hardware completion."""
        if confirm is not True or command not in ("poweroff", "reset"):
            raise MykiError("explicit confirmation is required for this device command")
        async with self._contact_lock:
            app = await self.client.app_data(watch_id)
            self._publish_contacts(watch_id, app)
            if str((app.get("settings") or {}).get("online")) != "1":
                raise MykiError("tracker is offline; command was not sent")
            await self.client.device_command(watch_id, command)

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
