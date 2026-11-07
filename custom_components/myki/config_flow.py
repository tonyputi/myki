"""Config flow: email + password, validated against the MyKi cloud."""

from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import voluptuous as vol

from .api import MykiAuthError, MykiClient, MykiError
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN, MIN_SCAN_INTERVAL

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


async def _watches_ok(hass: Any, email: str, password: str) -> bool:
    """Return True if credentials work and the account has at least one watch."""
    client = MykiClient(async_get_clientsession(hass), email, password)
    return bool(await client.watches())


class MykiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the MyKi config flow."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return MykiOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input:
            try:
                ok = await _watches_ok(self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD])
            except MykiAuthError:
                errors["base"] = "invalid_auth"
            except MykiError:
                errors["base"] = "cannot_connect"
            else:
                if ok:
                    await self.async_set_unique_id(user_input[CONF_EMAIL].lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=f"MyKi ({user_input[CONF_EMAIL]})", data=user_input
                    )
                errors["base"] = "no_watches"
        return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input:
            try:
                ok = await _watches_ok(self.hass, entry.data[CONF_EMAIL], user_input[CONF_PASSWORD])
            except MykiError:
                ok = False
            if ok:
                self.hass.config_entries.async_update_reauth(
                    entry, {**entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
                return self.async_abort(reason="reauth_successful")
            errors["base"] = "invalid_auth"
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=REAUTH_SCHEMA, errors=errors
        )


class MykiOptionsFlow(OptionsFlow):
    """Options: polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=current,
                    description={"suggested_value": current},
                ): vol.All(vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL))
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
