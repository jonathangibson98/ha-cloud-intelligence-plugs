"""Polls one plug for its on/off state."""
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .alcs import AlcsAuthError, AlcsError, AlcsPlug, AlcsTimeout, discover
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PlugCoordinator(DataUpdateCoordinator[bool]):
    """Holds the plug's power state."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, plug: AlcsPlug) -> None:
        interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(seconds=interval),
        )
        self.plug = plug
        self._misses = 0

    async def _async_update_data(self) -> bool:
        try:
            state = await self.hass.async_add_executor_job(self.plug.get_power)
        except AlcsAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except AlcsTimeout as err:
            self._misses += 1
            # Every few misses, check whether the plug moved to a new IP.
            if self._misses % 3 == 0 and await self._async_relocate():
                try:
                    state = await self.hass.async_add_executor_job(self.plug.get_power)
                except AlcsError as err2:
                    raise UpdateFailed(str(err2)) from err2
            else:
                raise UpdateFailed(f"{self.config_entry.title} not responding") from err
        except AlcsError as err:
            raise UpdateFailed(str(err)) from err
        self._misses = 0
        return state

    async def _async_relocate(self) -> bool:
        found = await self.hass.async_add_executor_job(discover)
        new_ip = found.get(self.plug.dn)
        if not new_ip or new_ip == self.plug.host:
            return False
        _LOGGER.info("%s moved from %s to %s", self.config_entry.title, self.plug.host, new_ip)
        await self.hass.async_add_executor_job(self.plug.close)
        self.plug.host = new_ip
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={**self.config_entry.data, CONF_HOST: new_ip}
        )
        return True

    async def async_set_power(self, on: bool) -> None:
        await self.hass.async_add_executor_job(self.plug.set_power, on)
        self.async_set_updated_data(on)
