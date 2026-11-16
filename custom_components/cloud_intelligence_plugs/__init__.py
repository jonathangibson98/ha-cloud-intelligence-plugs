"""Cloud Intelligence Plugs — local control of Alibaba IoT Living smart plugs."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .alcs import AlcsPlug
from .const import CONF_ACCESS_KEY, CONF_ACCESS_TOKEN, CONF_DEVICE_NAME, CONF_PRODUCT_KEY
from .coordinator import PlugCoordinator

PLATFORMS = [Platform.SWITCH]

type PlugConfigEntry = ConfigEntry[PlugCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: PlugConfigEntry) -> bool:
    d = entry.data
    plug = AlcsPlug(
        d[CONF_HOST], d[CONF_PRODUCT_KEY], d[CONF_DEVICE_NAME],
        d[CONF_ACCESS_KEY], d[CONF_ACCESS_TOKEN],
    )
    coordinator = PlugCoordinator(hass, entry, plug)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PlugConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await hass.async_add_executor_job(entry.runtime_data.plug.close)
    return ok


async def _async_reload(hass: HomeAssistant, entry: PlugConfigEntry) -> None:
    # Only options changes need a reload; IP updates are applied live.
    if entry.runtime_data.update_interval.total_seconds() != entry.options.get(
        "scan_interval", entry.runtime_data.update_interval.total_seconds()
    ):
        await hass.config_entries.async_reload(entry.entry_id)
