"""Cloud failures and malformed payloads stop at the API boundary."""

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import pytest

from custom_components.myki.api import BASE_URL, MykiClient, MykiError


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock):
    return MykiClient(async_get_clientsession(hass), "test@example.com", "test-password")


@pytest.mark.parametrize("payload", [
    [], "invalid", {"isok": False, "err": "private-sentinel"},
    {"isok": True, "data": [1]},
    {"isok": True, "data": {"allw": "invalid"}},
    {"isok": True, "data": {"allw": [None]}},
    {"isok": True, "data": {"allw": [{"nickname": "Test"}]}},
])
async def test_invalid_tracker_payload(client, aioclient_mock, payload):
    aioclient_mock.get(f"{BASE_URL}/watch", json=payload)
    with pytest.raises(MykiError) as error:
        await client.watches()
    assert "private-sentinel" not in str(error.value)


async def test_http_failure_cannot_claim_success(client, aioclient_mock):
    aioclient_mock.get(f"{BASE_URL}/watch", status=503, json={"isok": True})
    with pytest.raises(MykiError):
        await client.watches()


async def test_bad_json(client, aioclient_mock):
    aioclient_mock.get(f"{BASE_URL}/watch", text="<html>private-sentinel</html>")
    with pytest.raises(MykiError) as error:
        await client.watches()
    assert "private-sentinel" not in str(error.value)


@pytest.mark.parametrize("exception", [TimeoutError("private-sentinel"), aiohttp.ClientError("private-sentinel")])
async def test_transport_errors_do_not_expose_details(client, aioclient_mock, exception):
    aioclient_mock.get(f"{BASE_URL}/watch", exc=exception)
    with pytest.raises(MykiError) as error:
        await client.watches()
    assert "private-sentinel" not in str(error.value)
    assert error.value.__suppress_context__


@pytest.mark.parametrize("data", [
    {"current": [1]}, {"settings": "invalid"}, {"commands": [1]},
    {"current": {"steps": [1]}}, {"current": {"wifi": 5}},
])
async def test_invalid_app_sections(client, aioclient_mock, data):
    aioclient_mock.get(f"{BASE_URL}/watch/app-data?id=test-tracker", json={"isok": True, "data": data})
    with pytest.raises(MykiError):
        await client.app_data("test-tracker")


async def test_invalid_event_container(client, aioclient_mock):
    aioclient_mock.get(f"{BASE_URL}/watch/history/events?id=test-tracker", json={"isok": True, "data": {"events": "invalid"}})
    with pytest.raises(MykiError):
        await client.events("test-tracker")


@pytest.mark.parametrize("phone", ["", "not-a-number", "+1555&extra=1", "++15555550100"])
async def test_invalid_call_number_is_rejected_before_request(client, aioclient_mock, phone):
    with pytest.raises(MykiError, match="invalid phone number"):
        await client.make_call("test-tracker", phone)
    assert not aioclient_mock.mock_calls
