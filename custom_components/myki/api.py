"""Thin async client for the MyKi (Allterco) cloud API used by the MyKi Spot app."""

import json
import re
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

from .const import PERSONALIZATION_OPTIONS
from .settings import validate_group, validate_zone

BASE_URL = "https://spot.myki.pet:6020/api"
_TIMEOUT = aiohttp.ClientTimeout(total=10)


class MykiError(Exception):
    """API request failed."""


class MykiAuthError(MykiError):
    """Wrong credentials (HTTP 401)."""


class MykiClient:
    """Thin client; every call returns the payload's `data` object."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._headers = {
            "Authorization": aiohttp.encode_basic_auth(email, password, encoding="latin1")
        }

    async def _request(self, path: str, *, body: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            async with self._session.request("POST" if body is not None else "GET", BASE_URL + path, json=body, headers=self._headers, timeout=_TIMEOUT) as resp:
                if resp.status == 401:
                    raise MykiAuthError("unauthorized")
                if resp.status >= 400:
                    raise MykiError(f"HTTP {resp.status}")
                try:
                    payload = await resp.json(content_type=None)
                except ValueError:  # HTML or malformed JSON from gateways
                    raise MykiError("invalid JSON response") from None
        except TimeoutError:
            raise MykiError("request timed out") from None
        except aiohttp.ClientError:
            raise MykiError("request failed") from None
        if not isinstance(payload, dict) or payload.get("isok") is not True:
            raise MykiError("request rejected")
        data = payload.get("data") or {}
        if not isinstance(data, dict):
            raise MykiError("invalid response data")
        return data

    async def watches(self) -> list[dict[str, Any]]:
        """All trackers on the account: [{id, nickname, api}]."""
        watches = (await self._request("/watch")).get("allw") or []
        if not isinstance(watches, list) or any(
            not isinstance(watch, dict)
            or not isinstance(watch.get("id"), str)
            or not watch["id"]
            or (watch.get("nickname") is not None and not isinstance(watch["nickname"], str))
            for watch in watches
        ):
            raise MykiError("invalid tracker list")
        return watches

    async def app_data(self, watch_id: str) -> dict[str, Any]:
        """Full state of one tracker: {current, settings, commands}."""
        data = await self._request(f"/watch/app-data?id={quote(watch_id, safe='')}")
        for key in ("current", "settings", "commands"):
            if data.get(key) is not None and not isinstance(data[key], dict):
                raise MykiError("invalid tracker data")
        current = data.get("current") or {}
        for key, expected in (("position", dict), ("steps", dict), ("wifi", list)):
            if current.get(key) is not None and not isinstance(current[key], expected):
                raise MykiError("invalid tracker data")
        return data

    async def events(self, watch_id: str) -> list[dict[str, Any]]:
        """Device event log: [{event_name, timestamp}]."""
        events = (await self._request(f"/watch/history/events?id={quote(watch_id, safe='')}")).get("events") or []
        if not isinstance(events, list):
            raise MykiError("invalid event list")
        return events

    async def find(self, watch_id: str) -> None:
        """Make the tracker ring."""
        await self._request(f"/watch/find?id={quote(watch_id, safe='')}")

    async def make_call(self, watch_id: str, phone: str) -> None:
        """Make the tracker call the given phone number."""
        if not re.fullmatch(r"\+?[0-9]+", phone):
            raise MykiError("invalid phone number")
        await self._request(f"/watch/call?id={quote(watch_id, safe='')}&phone={quote(phone, safe='')}")

    async def set_sos_number(self, watch_id: str, slot: int, phone: str) -> None:
        """Write one SOS slot using the app endpoint."""
        if slot not in (1, 2, 3) or not re.fullmatch(r"[0-9]*", phone):
            raise MykiError("invalid SOS contact")
        await self._request("/watch/sos?" + urlencode({"id": watch_id, "num": slot, "phone": phone}))

    async def set_whitelist(self, watch_id: str, group: int, phones: list[str]) -> None:
        """Write a complete five-slot group, preserving untouched entries."""
        if group not in (1, 2) or len(phones) != 5 or any(
            not isinstance(phone, str) or not re.fullmatch(r"\+?[0-9]*", phone) or phone == "+"
            for phone in phones
        ):
            raise MykiError("invalid whitelist contacts")
        query = {"id": watch_id, "whitelist": group}
        query.update({f"phone{i}": phone for i, phone in enumerate(phones, start=1)})
        await self._request("/watch/whitelist?" + urlencode(query))

    async def set_personalization(self, watch_id: str, key: str, value: str) -> None:
        """Write one allowlisted app setting, including the explicit flashlight command."""
        if (
            not isinstance(key, str) or key not in PERSONALIZATION_OPTIONS
            or not isinstance(value, str) or value not in PERSONALIZATION_OPTIONS[key]
        ):
            raise MykiError("invalid personalization setting")
        if key == "battery_save_mode":
            await self._request("/watch/save-settings?" + urlencode({"id": watch_id, "key": key, "val": value}))
            return
        endpoint = "led" if key == "flashlight" else key
        parameter = "status" if endpoint == "led" else endpoint
        await self._request(f"/watch/{endpoint}?" + urlencode({"id": watch_id, parameter: value}))

    async def set_setting_group(self, watch_id: str, key: str, value: dict | list[str]) -> None:
        """Write one validated zone, all DND periods or all three alarm slots."""
        try:
            if key in ("safe_zone_1", "safe_zone_2"):
                validate_zone(value)
                encoded = json.dumps(value, allow_nan=False, separators=(",", ":"))
                endpoint = "save-settings"
                params = {"key": key, "val": encoded}
            else:
                validate_group(key, value)
                endpoint = "silencetime" if key == "silencetime" else "remind"
                prefix = "period" if key == "silencetime" else "alarm"
                params = {f"{prefix}{i}": item for i, item in enumerate(value, 1)}
        except (ValueError, TypeError, OverflowError):
            raise MykiError("invalid tracker setting") from None
        await self._request(f"/watch/{endpoint}?" + urlencode({"id": watch_id, **params}))

    async def set_tracker_details(self, watch_id: str, name: str, phone: str) -> None:
        """The app writes nickname and SIM number together; callers preserve siblings."""
        if not isinstance(name, str) or not name.strip() or len(name) > 255 or not isinstance(phone, str) or len(phone) > 32 or not re.fullmatch(r"\+?[0-9]+", phone):
            raise MykiError("invalid tracker details")
        await self._request("/watch/edit", body={"watchId": watch_id, "watchName": name, "watchPhone": phone})

    async def device_command(self, watch_id: str, command: str) -> None:
        """Only explicit shutdown/restart requests; factory reset/deletion stay app-only."""
        if command not in ("poweroff", "reset"):
            raise MykiError("unsupported device command")
        await self._request(f"/watch/{command}?" + urlencode({"id": watch_id}))

    async def start_rtt(self, watch_id: str, duration_minutes: int = 10) -> None:
        """Start real-time tracking (device reports at high frequency)."""
        await self._request(f"/watch/rtt?id={quote(watch_id, safe='')}&duration={duration_minutes}")

    async def set_ring_volume(self, watch_id: str, level: int) -> None:
        """Set the ringtone volume (1-4, layout-verified in the vendor app)."""
        await self._request(f"/watch/ringvolset?id={quote(watch_id, safe='')}&volume={level}")

    async def set_call_volume(self, watch_id: str, level: int) -> None:
        """Set the call volume (1-6, layout-verified in the vendor app)."""
        await self._request(f"/watch/callvolset?id={quote(watch_id, safe='')}&volume={level}")
