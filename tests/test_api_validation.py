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



async def test_contact_endpoints_preserve_empty_and_encoded_values(client, aioclient_mock):
    aioclient_mock.get(f"{BASE_URL}/watch/sos?id=test%26tracker&num=2&phone=", json={"isok": True})
    aioclient_mock.get(f"{BASE_URL}/watch/whitelist?id=test%26tracker&whitelist=2&phone1=%2B15555550100&phone2=&phone3=0015555550102&phone4=&phone5=", json={"isok": True})
    await client.set_sos_number("test&tracker", 2, "")
    await client.set_whitelist("test&tracker", 2, ["+15555550100", "", "0015555550102", "", ""])
    assert len(aioclient_mock.mock_calls) == 2


@pytest.mark.parametrize("key,value,parameter", [
    ("profile", str(value), "profile") for value in (1, 2, 3, 4)
] + [
    ("ringtone", str(value), "ringtone") for value in (0, 1, 2)
] + [("led", "0", "status"), ("led", "1", "status")])
async def test_personalization_endpoints(client, aioclient_mock, key, value, parameter):
    aioclient_mock.get(
        f"{BASE_URL}/watch/{key}?id=test%26tracker&{parameter}={value}",
        json={"isok": True},
    )
    await client.set_personalization("test&tracker", key, value)
    assert len(aioclient_mock.mock_calls) == 1


@pytest.mark.parametrize("key,value", [
    ("profile", "0"), ("profile", "5"), ("ringtone", "3"), ("led", "2"),
    ("unknown", "1"), ("../reset", "1"), ("profile", "1&extra=1"),
    ("profile", 1), ("profile", None), ("profile", []), ([], "1"),
])
async def test_invalid_personalization_never_reaches_cloud(client, aioclient_mock, key, value):
    with pytest.raises(MykiError, match="invalid personalization"):
        await client.set_personalization("test-tracker", key, value)
    assert not aioclient_mock.mock_calls



@pytest.mark.parametrize("slot,phone", [(0, "123"), (4, "123"), (1, "123&x=1"), (2, "+123")])
async def test_invalid_sos_write_makes_no_request(client, aioclient_mock, slot, phone):
    with pytest.raises(MykiError):
        await client.set_sos_number("test-tracker", slot, phone)
    assert not aioclient_mock.mock_calls


@pytest.mark.parametrize("group,phones", [(0, [""] * 5), (3, [""] * 5), (1, [""]), (2, ["invalid"] * 5)])
async def test_invalid_whitelist_write_makes_no_request(client, aioclient_mock, group, phones):
    with pytest.raises(MykiError):
        await client.set_whitelist("test-tracker", group, phones)
    assert not aioclient_mock.mock_calls
