"""Switch entity for each plug."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PlugConfigEntry
from .alcs import AlcsError
from .const import DOMAIN
from .coordinator import PlugCoordinator


def _mac(device_name: str) -> str | None:
    dn = device_name.lower()
    if len(dn) == 12 and all(c in "0123456789abcdef" for c in dn):
        return ":".join(dn[i:i + 2] for i in range(0, 12, 2))
    return None


async def async_setup_entry(
    hass: HomeAssistant, entry: PlugConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    async_add_entities([PlugSwitch(entry.runtime_data)])


class PlugSwitch(CoordinatorEntity[PlugCoordinator], SwitchEntity):
    """The plug's relay."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(self, coordinator: PlugCoordinator) -> None:
        super().__init__(coordinator)
        plug = coordinator.plug
        entry = coordinator.config_entry
        self._attr_unique_id = f"{plug.pk}_{plug.dn}"
        mac = _mac(plug.dn)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{plug.pk}_{plug.dn}")},
            connections={(CONNECTION_NETWORK_MAC, mac)} if mac else set(),
            name=entry.title,
            manufacturer="Cloud Intelligence (Alibaba IoT)",
            model="Smart Plug",
            model_id=plug.pk,
        )

    @property
    def is_on(self) -> bool | None:
        return self.coordinator.data

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"ip_address": self.coordinator.plug.host}

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        try:
            await self.coordinator.async_set_power(on)
        except AlcsError as err:
            raise HomeAssistantError(f"{self.coordinator.config_entry.title}: {err}") from err
