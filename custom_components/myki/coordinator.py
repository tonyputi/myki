"""DataUpdateCoordinator polling every watch on the MyKi account."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import MykiAuthError, MykiClient, MykiError

_LOGGER = logging.getLogger(__name__)

type MykiData = dict[str, dict[str, Any]]


class MykiCoordinator(DataUpdateCoordinator[MykiData]):
    """data = {watch_id: {"watch": {id, nickname}, "app": {current, settings, commands}}}."""

    def __init__(self, hass: HomeAssistant, client: MykiClient, scan_interval: int) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="MyKi",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client

    async def _async_update_data(self) -> MykiData:
        try:
            watches = await self.client.watches()
        except MykiAuthError as err:
            raise ConfigEntryAuthFailed() from err
        data: MykiData = {}
        for w in watches:
            if not w.get("id"):
                continue
            app = await self.client.app_data(w["id"])
            try:
                events = await self.client.events(w["id"])
            except MykiError as err:  # events are non-critical
                _LOGGER.debug("Could not fetch events for %s: %s", w["id"], err)
                events = []
            data[w["id"]] = {"watch": w, "app": app, "events": events}
        return data
