"""Thin async client for the MyKi (Allterco) cloud API used by the MyKi Spot app."""

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
        self._auth = aiohttp.BasicAuth(email, password)

    async def _get(self, path: str) -> dict[str, Any]:
        try:
            async with self._session.get(BASE_URL + path, auth=self._auth, timeout=_TIMEOUT) as resp:
                if resp.status == 401:
                    raise MykiAuthError("unauthorized")
                try:
                    payload = await resp.json(content_type=None)
                except ValueError as err:  # HTML or malformed JSON from gateways
                    raise MykiError(f"bad response: {err}") from err
        except TimeoutError as err:
            raise MykiError(f"timeout: {err}") from err
        except aiohttp.ClientError as err:
            raise MykiError(f"request failed: {err}") from err
        if not isinstance(payload, dict) or not payload.get("isok"):
            err = payload.get("err", "unknown error") if isinstance(payload, dict) else "bad response"
            raise MykiError(str(err))
        return payload.get("data") or {}

    async def watches(self) -> list[dict[str, Any]]:
        """All trackers on the account: [{id, nickname, api}]."""
        return (await self._get("/watch")).get("allw") or []

    async def app_data(self, watch_id: str) -> dict[str, Any]:
        """Full state of one tracker: {current, settings, commands}."""
        return await self._get(f"/watch/app-data?id={watch_id}")

    async def events(self, watch_id: str) -> list[dict[str, Any]]:
        """Device event log: [{event_name, timestamp}]."""
        return (await self._get(f"/watch/history/events?id={watch_id}")).get("events") or []

    async def find(self, watch_id: str) -> None:
        """Make the tracker ring."""
        await self._get(f"/watch/find?id={watch_id}")

    async def make_call(self, watch_id: str, phone: str) -> None:
        """Make the tracker call the given phone number."""
        await self._get(f"/watch/call?id={watch_id}&phone={quote(phone)}")

    async def start_rtt(self, watch_id: str, duration_minutes: int = 10) -> None:
        """Start real-time tracking (device reports at high frequency)."""
        await self._get(f"/watch/rtt?id={watch_id}&duration={duration_minutes}")

    async def set_ring_volume(self, watch_id: str, level: int) -> None:
        """Set the ringtone volume (1-4, layout-verified in the vendor app)."""
        await self._get(f"/watch/ringvolset?id={watch_id}&volume={level}")

    async def set_call_volume(self, watch_id: str, level: int) -> None:
        """Set the call volume (1-6, layout-verified in the vendor app)."""
        await self._get(f"/watch/callvolset?id={watch_id}&volume={level}")
