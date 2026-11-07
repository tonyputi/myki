"""DataUpdateCoordinator polling every watch on the MyKi account."""

from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import MykiAuthError, MykiClient

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
            return {
                w["id"]: {"watch": w, "app": await self.client.app_data(w["id"])}
                for w in watches
                if w.get("id")
            }
        except MykiAuthError as err:
            raise ConfigEntryAuthFailed() from err
