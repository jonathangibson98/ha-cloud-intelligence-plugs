"""Config flow: one entry per plug."""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.core import callback

from .alcs import AlcsAuthError, AlcsError, AlcsPlug, AlcsTimeout, discover
from .const import (
    CONF_ACCESS_KEY,
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_NAME,
    CONF_PRODUCT_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_PRODUCT_KEY,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)


class CloudPlugsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a plug using its local keys."""

    VERSION = 1

    async def _async_validate(self, data: dict[str, Any]) -> tuple[dict[str, str], str | None]:
        """Return (errors, host). Finds the IP by discovery when host is blank."""
        host = (data.get(CONF_HOST) or "").strip()
        if not host:
            found = await self.hass.async_add_executor_job(discover)
            host = found.get(data[CONF_DEVICE_NAME])
            if not host:
                return {"base": "not_found"}, None
        plug = AlcsPlug(host, data[CONF_PRODUCT_KEY], data[CONF_DEVICE_NAME],
                        data[CONF_ACCESS_KEY], data[CONF_ACCESS_TOKEN])
        try:
            await self.hass.async_add_executor_job(plug.test)
        except AlcsAuthError:
            return {"base": "invalid_auth"}, None
        except AlcsTimeout:
            return {"base": "cannot_connect"}, None
        except AlcsError:
            return {"base": "unknown"}, None
        finally:
            await self.hass.async_add_executor_job(plug.close)
        return {}, host

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_DEVICE_NAME] = user_input[CONF_DEVICE_NAME].strip().lower()
            await self.async_set_unique_id(
                f"{user_input[CONF_PRODUCT_KEY]}_{user_input[CONF_DEVICE_NAME]}"
            )
            self._abort_if_unique_id_configured()
            errors, host = await self._async_validate(user_input)
            if not errors:
                name = user_input.pop(CONF_NAME)
                user_input[CONF_HOST] = host
                return self.async_create_entry(title=name, data=user_input)

        defaults = user_input or {}
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
            vol.Required(CONF_DEVICE_NAME, default=defaults.get(CONF_DEVICE_NAME, "")): str,
            vol.Required(CONF_ACCESS_KEY, default=defaults.get(CONF_ACCESS_KEY, "")): str,
            vol.Required(CONF_ACCESS_TOKEN, default=defaults.get(CONF_ACCESS_TOKEN, "")): str,
            vol.Optional(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PRODUCT_KEY,
                         default=defaults.get(CONF_PRODUCT_KEY, DEFAULT_PRODUCT_KEY)): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **user_input}
            errors, host = await self._async_validate(data)
            if not errors:
                data[CONF_HOST] = host
                return self.async_update_reload_and_abort(entry, data=data)
        schema = vol.Schema({
            vol.Required(CONF_ACCESS_KEY, default=entry.data[CONF_ACCESS_KEY]): str,
            vol.Required(CONF_ACCESS_TOKEN): str,
        })
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors,
            description_placeholders={"name": entry.title},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PlugOptionsFlow()


class PlugOptionsFlow(OptionsFlow):
    """Polling interval."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        schema = vol.Schema({
            vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                vol.Coerce(int), vol.Range(min=3, max=300)
            ),
        })
        return self.async_show_form(step_id="init", data_schema=schema)
