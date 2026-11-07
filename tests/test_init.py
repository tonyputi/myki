"""Integration tests: config entry setup against a mocked MyKi cloud.

These would have caught the platform setup signature bug found in the field.
"""

import json

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.myki.api import BASE_URL
from custom_components.myki.const import DOMAIN

WATCH_ID = "3747004238"
NICK = "TestKid"

WATCHES = {"isok": True, "data": {"allw": [{"id": WATCH_ID, "nickname": NICK, "api": 2}]}}

ZONES = {
    "safe_zone_1": json.dumps(
        {"name": "Home", "lat": 35.92414, "lon": 14.45332, "radius": 0.212, "active": 1, "profile": 1}
    ),
    "safe_zone_2": json.dumps(
        {"name": "School", "lat": 35.90756, "lon": 14.49165, "radius": 0.127, "active": 1, "profile": 1}
    ),
}

APP_DATA = {
    "isok": True,
    "id": WATCH_ID,
    "data": {
        "current": {
            "takenat": "2026-11-07 12:37:29",
            "position": {"type": "WiFi", "latitude": 35.92417, "longitude": 14.45502, "accuracy": 25},
            "battery": "85",
            "steps": {"allSteps": 1353915, "todaySteps": 4321},
        },
        "settings": {"online": "1", "nickname": NICK, **ZONES},
        "commands": {"sos_phone_1": "0035679248232", "whitelist_1": "0035679248232,0035699859524", "volume_ring": "4", "volume_call": "6"},
    },
}


def _mock_cloud(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.get(f"{BASE_URL}/watch", json=WATCHES)
    aioclient_mock.get(f"{BASE_URL}/watch/app-data?id={WATCH_ID}", json=APP_DATA)


async def _setup(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> MockConfigEntry:
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    assert entry.state is ConfigEntryState.LOADED

    tracker = hass.states.get(f"device_tracker.{NICK.lower()}")
    assert tracker is not None
    assert tracker.attributes["latitude"] == 35.92417
    assert tracker.attributes["longitude"] == 14.45502
    assert tracker.attributes["battery_level"] == 85
    assert tracker.attributes["zone"] == "Home"

    assert hass.states.get(f"sensor.{NICK.lower()}_battery").state == "85"
    assert hass.states.get(f"sensor.{NICK.lower()}_zone").state == "Home"
    assert hass.states.get(f"sensor.{NICK.lower()}_steps_today").state == "4321"
    assert hass.states.get(f"binary_sensor.{NICK.lower()}_online").state == "on"


async def test_find_service(hass: HomeAssistant, aioclient_mock) -> None:
    await _setup(hass, aioclient_mock)
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})

    await hass.services.async_call(
        DOMAIN, "find", {"entity_id": f"device_tracker.{NICK.lower()}"}, blocking=True
    )
    urls = [str(url) for method, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/find" in url for url in urls)


async def test_unload(hass: HomeAssistant, aioclient_mock) -> None:
    entry = await _setup(hass, aioclient_mock)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED




async def test_device_page_entities(hass: HomeAssistant, aioclient_mock) -> None:
    _mock_cloud(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_EMAIL: "test@example.com", CONF_PASSWORD: "secret"},
        options={"call_me_number": "+35679060465"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    aioclient_mock.get(f"{BASE_URL}/watch/find?id={WATCH_ID}", json={"isok": True})
    aioclient_mock.get(
        f"{BASE_URL}/watch/call?id={WATCH_ID}&phone=%2B35679060465", json={"isok": True}
    )
    aioclient_mock.get(
        f"{BASE_URL}/watch/callvolset?id={WATCH_ID}&volume=5", json={"isok": True}
    )
    # buttons exist; call_me available only with the option set
    assert hass.states.get(f"button.{NICK.lower()}_find").state == "unknown"
    assert hass.states.get(f"button.{NICK.lower()}_call_me").state == "unknown"

    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{NICK.lower()}_find"}, blocking=True
    )
    await hass.services.async_call(
        "button", "press", {"entity_id": f"button.{NICK.lower()}_call_me"}, blocking=True
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("watch/find" in u for u in urls)
    assert any("watch/call" in u and "phone=%2B35679060465" in u for u in urls)

    # volume sliders reflect the payload and can be set
    assert hass.states.get(f"number.{NICK.lower()}_ring_volume").state == "4"
    assert hass.states.get(f"number.{NICK.lower()}_call_volume").state == "6"
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{NICK.lower()}_call_volume", "value": 5},
        blocking=True,
    )
    urls = [str(url) for _, url, *_ in aioclient_mock.mock_calls]
    assert any("callvolset" in u and "volume=5" in u for u in urls)
