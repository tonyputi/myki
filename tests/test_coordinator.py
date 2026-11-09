"""Authentication must not be hidden by optional event-log failures."""

from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
import pytest

from custom_components.myki.api import MykiAuthError, MykiClient, MykiError
from custom_components.myki.coordinator import MykiCoordinator


@pytest.mark.parametrize("method", ["watches", "app_data", "events"])
async def test_auth_failure_requires_reauthentication(hass: HomeAssistant, method: str) -> None:
    client = AsyncMock(spec=MykiClient)
    client.watches.return_value = [{"id": "test-tracker"}]
    client.app_data.return_value = {}
    client.events.return_value = []
    getattr(client, method).side_effect = MykiAuthError("unauthorized")
    coordinator = MykiCoordinator(hass, client, 60)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_optional_events_failure_keeps_tracker_data(hass: HomeAssistant) -> None:
    client = AsyncMock(spec=MykiClient)
    client.watches.return_value = [{"id": "test-tracker"}]
    client.app_data.return_value = {"current": {"battery": "80"}}
    client.events.side_effect = MykiError("service unavailable")
    coordinator = MykiCoordinator(hass, client, 60)

    result = await coordinator._async_update_data()

    assert result["test-tracker"]["app"] == {"current": {"battery": "80"}}
    assert result["test-tracker"]["events"] == []


async def test_required_data_failure_marks_update_failed(hass: HomeAssistant) -> None:
    client = AsyncMock(spec=MykiClient)
    client.watches.return_value = [{"id": "test-tracker"}]
    client.app_data.side_effect = MykiError("service unavailable")
    coordinator = MykiCoordinator(hass, client, 60)

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
