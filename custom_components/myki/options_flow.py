"""Native tracker settings forms; only polling preferences are stored in HA."""

from collections.abc import Awaitable, Callable
from copy import deepcopy
from datetime import time
import re
from typing import Any

from homeassistant.config_entries import ConfigEntryState, ConfigFlowResult, OptionsFlow
from homeassistant.helpers import selector
from homeassistant.helpers.translation import async_get_translations
import voluptuous as vol

from .api import MykiAuthError, MykiError
from .const import (
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    PERSONALIZATION_OPTIONS,
)
from .contacts import CONTACT_SLOTS, contact_numbers, normalize_phone
from .settings import DISABLED_PERIOD, WEEKDAYS, edit_group, read_group, scalar_setting


class MykiOptionsFlow(OptionsFlow):
    """Choose a tracker once, then edit its cloud settings using native forms."""

    _watch_id: str
    _watch_name: str
    _app: dict[str, Any]
    _key: str

    async def async_step_init(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["tracker", "polling"])

    async def async_step_polling(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data={**self.config_entry.options, **user_input})
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        return self.async_show_form(step_id="polling", data_schema=vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL)),
        }))

    async def async_step_tracker(self, user_input=None) -> ConfigFlowResult:
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="integration_not_loaded")
        if user_input is not None:
            self._watch_id = user_input["tracker"]
            if self._watch_id not in self.config_entry.runtime_data.data:
                return self.async_abort(reason="tracker_removed")
            return await self.async_step_tracker_menu()
        choices = [
            {"value": wid, "label": item["watch"].get("nickname") or wid}
            for wid, item in self.config_entry.runtime_data.data.items()
        ]
        if not choices:
            return self.async_abort(reason="tracker_removed")
        return self.async_show_form(step_id="tracker", data_schema=vol.Schema({
            vol.Required("tracker"): selector.SelectSelector({"options": choices}),
        }))

    async def async_step_tracker_menu(self, user_input=None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="tracker_menu", menu_options=["contacts", "audio", "device", "zones", "schedules"], description_placeholders={
            "tracker": self.config_entry.runtime_data.data[self._watch_id]["watch"].get("nickname") or self._watch_id,
        })

    async def _snapshot(self) -> ConfigFlowResult | None:
        """Fetch on opening an editor, never manufacture missing cloud data."""
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="integration_not_loaded")
        coordinator = self.config_entry.runtime_data
        if self._watch_id not in coordinator.data:
            return self.async_abort(reason="tracker_removed")
        self._watch_name = coordinator.data[self._watch_id]["watch"].get("nickname") or self._watch_id
        try:
            self._app = await coordinator.async_settings_snapshot(self._watch_id)
        except MykiAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return self.async_abort(reason="invalid_auth")
        except MykiError:
            return self.async_abort(reason="cannot_connect")
        return None

    async def _save(self, operation: Callable[[], Awaitable[None]]) -> ConfigFlowResult:
        """An uncertain save closes the draft: reopening reads fresh values, not retries."""
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(reason="integration_not_loaded")
        if self._watch_id not in self.config_entry.runtime_data.data:
            return self.async_abort(reason="tracker_removed")
        try:
            await operation()
        except MykiAuthError:
            self.config_entry.async_start_reauth(self.hass)
            return self.async_abort(reason="invalid_auth")
        except MykiError:
            return self.async_abort(reason="write_failed")
        return self.async_abort(reason="settings_saved")

    async def _context_labels(self, group: str) -> dict[str, str]:
        """Keep the selected tracker and field visible in every final editor."""
        translations = await async_get_translations(
            self.hass, self.context.get("language", self.hass.config.language), "selector", {DOMAIN},
        )
        return {
            "tracker": self._watch_name,
            "setting": translations.get(f"component.{DOMAIN}.selector.{group}.options.{self._key}", self._key),
        }

    async def async_step_contacts(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._key = user_input["contact"]
            return await self.async_step_contact()
        return self.async_show_form(step_id="contacts", data_schema=vol.Schema({
            vol.Required("contact"): selector.SelectSelector({
                "options": list(CONTACT_SLOTS), "translation_key": "contacts",
            }),
        }))

    async def async_step_contact(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is None:
            if result := await self._snapshot():
                return result
        try:
            current = contact_numbers(self._app)[self._key]
            if user_input is not None:
                if len(user_input.get("value", "")) > 32:
                    raise MykiError("invalid contact number")
                normalize_phone(user_input.get("value", ""))
        except MykiError:
            if user_input is None:
                return self.async_abort(reason="invalid_settings")
            errors["base"] = "invalid_input"
        if user_input is not None and not errors:
            return await self._save(lambda: self.config_entry.runtime_data.async_set_contact(
                self._watch_id, self._key, user_input.get("value", ""), current,
            ))
        schema = vol.Schema({vol.Optional("value"): selector.TextSelector({"type": selector.TextSelectorType.TEL})})
        return self.async_show_form(step_id="contact", data_schema=self.add_suggested_values_to_schema(
            schema, user_input if user_input is not None else {"value": current},
        ), errors=errors, last_step=True, description_placeholders=await self._context_labels("contacts"))

    async def async_step_audio(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._key = user_input["setting"]
            return await self.async_step_setting()
        return self._setting_menu("audio", ["profile", "ringtone", "volume_ring", "volume_call", "led"])

    async def async_step_device(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._key = user_input["setting"]
            return await self.async_step_setting()
        return self._setting_menu("device", ["mode", "battery_save_mode", "nickname", "msisdn"])

    def _setting_menu(self, step, keys) -> ConfigFlowResult:
        return self.async_show_form(step_id=step, data_schema=vol.Schema({
            vol.Required("setting"): selector.SelectSelector({"options": keys, "translation_key": "settings"}),
        }))

    async def async_step_setting(self, user_input=None) -> ConfigFlowResult:
        errors = {}
        if user_input is None:
            if result := await self._snapshot():
                return result
        key = self._key
        current = scalar_setting(self._app, key)
        if key in ("nickname", "msisdn"):
            current = (self._app.get("settings") or {}).get(key)
            sibling = "msisdn" if key == "nickname" else "nickname"
            paired = (self._app.get("settings") or {}).get(sibling)
            if not isinstance(current, str) or not current.strip() or not isinstance(paired, str) or not paired.strip():
                return self.async_abort(reason="invalid_settings")
            field = selector.TextSelector({"type": selector.TextSelectorType.TEL if key == "msisdn" else selector.TextSelectorType.TEXT})
        elif key in ("volume_ring", "volume_call"):
            maximum = 4 if key == "volume_ring" else 6
            if current not in {str(i) for i in range(1, maximum + 1)}:
                return self.async_abort(reason="invalid_settings")
            current = int(current)
            field = selector.NumberSelector({"min": 1, "max": maximum, "step": 1, "mode": selector.NumberSelectorMode.SLIDER})
        else:
            if current not in PERSONALIZATION_OPTIONS[key] and not (key == "led" and current == "2"):
                return self.async_abort(reason="invalid_settings")
            field = selector.SelectSelector({"options": list(PERSONALIZATION_OPTIONS[key]), "translation_key": key})
        if user_input is not None:
            value = user_input["value"]
            if key in ("nickname", "msisdn"):
                if not value.strip() or len(value) > (255 if key == "nickname" else 32):
                    errors["base"] = "invalid_input"
                elif key == "msisdn":
                    if not re.fullmatch(r"\+?[0-9]+", value):
                        errors["base"] = "invalid_input"
                if not errors:
                    return await self._save(lambda: self.config_entry.runtime_data.async_set_tracker_detail(self._watch_id, key, value, current))
            elif key in ("volume_ring", "volume_call"):
                return await self._save(lambda: self.config_entry.runtime_data.async_set_volume(self._watch_id, key, value, current))
            else:
                return await self._save(lambda: self.config_entry.runtime_data.async_set_personalization(self._watch_id, key, value, current))
        marker = vol.Required("value", description={"suggested_value": current}) if not (key == "led" and current == "2") else vol.Required("value")
        schema = vol.Schema({marker: field})
        if user_input is not None:
            schema = self.add_suggested_values_to_schema(schema, user_input)
        return self.async_show_form(step_id="setting", data_schema=schema, errors=errors, last_step=True, description_placeholders=await self._context_labels("settings"))

    async def async_step_zones(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._key = user_input["zone"]
            return await self.async_step_zone()
        return self.async_show_form(step_id="zones", data_schema=vol.Schema({
            vol.Required("zone"): selector.SelectSelector({"options": ["safe_zone_1", "safe_zone_2"], "translation_key": "zones"}),
        }))

    async def async_step_zone(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            if result := await self._snapshot():
                return result
        try:
            current = read_group(self._app, self._key)
        except ValueError:
            return self.async_abort(reason="invalid_settings")
        errors = {}
        if user_input is not None:
            changes = {key: value for key, value in user_input.items() if key != "location"}
            changes.update(user_input["location"])
            try:
                edit_group(self._key, current, changes, None)
            except (ValueError, TypeError, OverflowError):
                errors["base"] = "invalid_input"
            else:
                return await self._save(lambda: self.config_entry.runtime_data.async_edit_setting_group(self._watch_id, self._key, changes, current))
        values = {
            "name": current.get("name"), "enabled": str(current.get("active")) == "1",
            "ring_mode": str(current.get("profile")),
        } if current else {}
        if current:
            values["location"] = {"latitude": float(current["lat"]), "longitude": float(current["lon"]), "radius": float(current["radius"]) * 1000}
        schema = vol.Schema({
            vol.Required("name"): selector.TextSelector(),
            vol.Required("location"): selector.LocationSelector({"radius": True}),
            vol.Required("enabled"): selector.BooleanSelector(),
            vol.Required("ring_mode"): selector.SelectSelector({"options": ["1", "2", "3", "4"], "translation_key": "profile"}),
        })
        return self.async_show_form(step_id="zone", data_schema=self.add_suggested_values_to_schema(schema, user_input if user_input is not None else values), errors=errors, last_step=True, description_placeholders=await self._context_labels("zones"))

    async def async_step_schedules(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            self._key = user_input["schedule"]
            return await self.async_step_schedule()
        return self.async_show_form(step_id="schedules", data_schema=vol.Schema({
            vol.Required("schedule"): selector.SelectSelector({"options": ["dnd", "alarm_1", "alarm_2", "alarm_3"], "translation_key": "schedules"}),
        }))

    async def async_step_schedule(self, user_input=None) -> ConfigFlowResult:
        if user_input is None:
            if result := await self._snapshot():
                return result
        key = "silencetime" if self._key == "dnd" else "remind"
        index = 0 if self._key == "dnd" else int(self._key[-1]) - 1
        try:
            current = read_group(self._app, key)[index]
        except ValueError:
            return self.async_abort(reason="invalid_settings")
        errors = {}
        if user_input is not None:
            changes = deepcopy(user_input)
            try:
                for field in ("start", "end", "time"):
                    if field in changes:
                        parsed = time.fromisoformat(changes[field])
                        if parsed.second or parsed.microsecond or parsed.tzinfo:
                            raise ValueError("minute precision required")
                        changes[field] = parsed.strftime("%H:%M")
                edit_group(key, read_group(self._app, key), changes, index)
            except (ValueError, TypeError, OverflowError):
                errors["base"] = "invalid_input"
            else:
                return await self._save(lambda: self.config_entry.runtime_data.async_edit_setting_group(self._watch_id, key, changes, current, index))
        if key == "silencetime":
            start, end = current.split("-")
            values = {"enabled": current != DISABLED_PERIOD, "start": start, "end": end}
            fields = {vol.Required("enabled"): selector.BooleanSelector(), vol.Required("start"): selector.TimeSelector(), vol.Required("end"): selector.TimeSelector()}
            step = "dnd"
        else:
            values = {"enabled": current[6] == "1", "time": current[:5], "weekdays": [day for day, bit in zip(WEEKDAYS, current[10:17], strict=True) if bit == "1"]}
            fields = {vol.Required("enabled"): selector.BooleanSelector(), vol.Required("time"): selector.TimeSelector(), vol.Required("weekdays"): selector.SelectSelector({"options": list(WEEKDAYS), "multiple": True, "translation_key": "weekdays"})}
            step = "alarm"
        return self.async_show_form(step_id=step, data_schema=self.add_suggested_values_to_schema(vol.Schema(fields), user_input if user_input is not None else values), errors=errors, last_step=True, description_placeholders=await self._context_labels("schedules"))

    async def async_step_dnd(self, user_input=None) -> ConfigFlowResult:
        return await self.async_step_schedule(user_input)

    async def async_step_alarm(self, user_input=None) -> ConfigFlowResult:
        return await self.async_step_schedule(user_input)
