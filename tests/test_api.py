"""Authentication stays request-scoped without deprecated aiohttp objects."""

import base64

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from custom_components.myki.api import BASE_URL, MykiAuthError, MykiClient


@pytest.mark.parametrize("password", ["test-password", "test-pässword"])
@pytest.mark.filterwarnings("error:BasicAuth is deprecated:DeprecationWarning")
async def test_request_authentication(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, password: str
) -> None:
    session = async_get_clientsession(hass)
    original_headers = dict(session.headers)
    client = MykiClient(session, "test@example.com", password)
    aioclient_mock.get(f"{BASE_URL}/watch", json={"isok": True, "data": {"allw": []}})

    assert await client.watches() == []

    expected = base64.b64encode(f"test@example.com:{password}".encode("latin1")).decode()
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == f"Basic {expected}"
    assert dict(session.headers) == original_headers


async def test_unauthorized_response(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    client = MykiClient(async_get_clientsession(hass), "test@example.com", "test-password")
    aioclient_mock.get(f"{BASE_URL}/watch", status=401)

    with pytest.raises(MykiAuthError):
        await client.watches()
