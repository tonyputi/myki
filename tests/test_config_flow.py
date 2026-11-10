"""Config, reauthentication and options flows against the HA flow manager."""

from unittest.mock import patch

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant.common import MockConfigEntry
import voluptuous as vol

from custom_components.myki.api import MykiAuthError, MykiError
from custom_components.myki.const import DOMAIN

CREDENTIALS = {"email": "test@example.com", "password": "test-password"}


@pytest.fixture
async def cloud():
    with (
        patch("custom_components.myki.api.MykiClient.watches", return_value=[{"id": "test-tracker"}]) as watches,
        patch("custom_components.myki.async_setup_entry", return_value=None),
    ):
        yield watches


async def test_create_entry(hass: HomeAssistant, cloud):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == CREDENTIALS
    assert result["result"].unique_id == CREDENTIALS["email"]


async def test_duplicate_account(hass: HomeAssistant, cloud):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDENTIALS, unique_id=CREDENTIALS["email"])
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**CREDENTIALS, "email": "TEST@example.com"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("failure,expected", [
    (MykiAuthError("unauthorized"), "invalid_auth"),
    (MykiError("offline"), "cannot_connect"),
    (None, "no_watches"),
])
async def test_user_errors_and_retry(hass: HomeAssistant, cloud, failure, expected):
    cloud.side_effect = failure
    cloud.return_value = []
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    assert result["errors"] == {"base": expected}
    cloud.side_effect = None
    cloud.return_value = [{"id": "test-tracker"}]
    result = await hass.config_entries.flow.async_configure(result["flow_id"], CREDENTIALS)
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.parametrize("failure,expected", [
    (MykiAuthError("unauthorized"), "invalid_auth"),
    (MykiError("offline"), "cannot_connect"),
    (None, "no_watches"),
])
async def test_reauth_errors_keep_credentials(hass: HomeAssistant, cloud, failure, expected):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDENTIALS, unique_id=CREDENTIALS["email"])
    entry.add_to_hass(hass)
    cloud.side_effect = failure
    cloud.return_value = []
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new-password"})
    assert result["errors"] == {"base": expected}
    assert entry.data == CREDENTIALS


async def test_reauth_preserves_options_and_reloads(hass: HomeAssistant, cloud):
    entry = MockConfigEntry(
        domain=DOMAIN, data=CREDENTIALS, unique_id=CREDENTIALS["email"],
        options={"scan_interval": 120},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id}, data=entry.data
    )
    with patch.object(hass.config_entries, "async_reload", return_value=True) as reload_entry:
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"password": "new-password"})
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data == {**CREDENTIALS, "password": "new-password"}
    assert entry.options == {"scan_interval": 120}
    reload_entry.assert_awaited_once_with(entry.entry_id)


async def test_options_save(hass: HomeAssistant, cloud):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDENTIALS, options={"scan_interval": 60})
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "polling"})
    options = {"scan_interval": 120}
    result = await hass.config_entries.options.async_configure(result["flow_id"], options)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options


async def test_options_reject_short_interval(hass: HomeAssistant, cloud):
    entry = MockConfigEntry(domain=DOMAIN, data=CREDENTIALS)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"next_step_id": "polling"})
    with pytest.raises(vol.Invalid):
        await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 9})
    assert not entry.options
