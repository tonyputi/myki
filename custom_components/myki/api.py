"""Async client for the MyKi (Allterco) cloud API used by the MyKi Spot watch app."""

import logging
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://spot.myki.pet:6020/api"


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
            async with self._session.get(BASE_URL + path, auth=self._auth) as resp:
                if resp.status == 401:
                    raise MykiAuthError("unauthorized")
                payload = await resp.json(content_type=None)
        except TimeoutError as err:
            raise MykiError(f"timeout: {err}") from err
        except aiohttp.ClientError as err:
            raise MykiError(f"request failed: {err}") from err
        if not isinstance(payload, dict) or not payload.get("isok"):
            err = payload.get("err", "unknown error") if isinstance(payload, dict) else "bad response"
            raise MykiError(str(err))
        return payload.get("data") or {}

    async def watches(self) -> list[dict[str, Any]]:
        """All watches on the account: [{id, nickname, api}]."""
        return (await self._get("/watch")).get("allw") or []

    async def app_data(self, watch_id: str) -> dict[str, Any]:
        """Full state of one watch: {current, settings, commands}."""
        return await self._get(f"/watch/app-data?id={watch_id}")

    async def find(self, watch_id: str) -> None:
        """Make the watch ring."""
        await self._get(f"/watch/find?id={watch_id}")

    async def make_call(self, watch_id: str, phone: str) -> None:
        """Make the watch call the given phone number."""
        from urllib.parse import quote

        await self._get(f"/watch/call?id={watch_id}&phone={quote(phone)}")
