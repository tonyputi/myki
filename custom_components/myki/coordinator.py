"""DataUpdateCoordinator polling every tracker on the MyKi account."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MykiAuthError, MykiClient, MykiError

_LOGGER = logging.getLogger(__name__)

type MykiData = dict[str, dict[str, Any]]


class MykiCoordinator(DataUpdateCoordinator[MykiData]):
    """data = {watch_id: {"watch": {id, nickname}, "app": {current, settings, commands}, "events": [...]}}."""

    def __init__(self, hass: HomeAssistant, client: MykiClient, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="MyKi",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_fetch(self) -> MykiData:
        data: MykiData = {}
        for w in await self.client.watches():
            if not w.get("id"):
                continue
            watch_id = w["id"]
            app = await self.client.app_data(watch_id)
            try:
                events = await self.client.events(watch_id)
            except MykiError as err:  # events are non-critical
                _LOGGER.debug("Could not fetch events for %s: %s", watch_id, err)
                events = []
            data[watch_id] = {"watch": w, "app": app, "events": events}
        return data

    async def _async_update_data(self) -> MykiData:
        try:
            return await self._async_fetch()
        except MykiAuthError as err:
            raise ConfigEntryAuthFailed() from err
        except MykiError as err:
            raise UpdateFailed(str(err)) from err
