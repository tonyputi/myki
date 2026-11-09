"""Thin async client for the MyKi (Allterco) cloud API used by the MyKi Spot app."""

import re
from typing import Any
from urllib.parse import quote

import aiohttp

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

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(BASE_URL + path, headers=self._headers, timeout=_TIMEOUT) as resp:
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
        watches = (await self._get("/watch")).get("allw") or []
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
        data = await self._get(f"/watch/app-data?id={quote(watch_id, safe='')}")
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
        events = (await self._get(f"/watch/history/events?id={quote(watch_id, safe='')}")).get("events") or []
        if not isinstance(events, list):
            raise MykiError("invalid event list")
        return events

    async def find(self, watch_id: str) -> None:
        """Make the tracker ring."""
        await self._get(f"/watch/find?id={quote(watch_id, safe='')}")

    async def make_call(self, watch_id: str, phone: str) -> None:
        """Make the tracker call the given phone number."""
        if not re.fullmatch(r"\+?[0-9]+", phone):
            raise MykiError("invalid phone number")
        await self._get(f"/watch/call?id={quote(watch_id, safe='')}&phone={quote(phone, safe='')}")

    async def start_rtt(self, watch_id: str, duration_minutes: int = 10) -> None:
        """Start real-time tracking (device reports at high frequency)."""
        await self._get(f"/watch/rtt?id={quote(watch_id, safe='')}&duration={duration_minutes}")

    async def set_ring_volume(self, watch_id: str, level: int) -> None:
        """Set the ringtone volume (1-4, layout-verified in the vendor app)."""
        await self._get(f"/watch/ringvolset?id={quote(watch_id, safe='')}&volume={level}")

    async def set_call_volume(self, watch_id: str, level: int) -> None:
        """Set the call volume (1-6, layout-verified in the vendor app)."""
        await self._get(f"/watch/callvolset?id={quote(watch_id, safe='')}&volume={level}")
