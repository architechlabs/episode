"""Config flow for Episode Response DSP Amplifier."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithConfigEntry,
)
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import callback

from .client import EpisodeResponseClient
from .const import (
    CONF_POLL_INTERVAL,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DOMAIN,
    INTEGRATION_TITLE,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
)
from .errors import AuthenticationFailed, ConnectionFailed

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.Coerce(int),
        vol.Required(CONF_USERNAME, default="admin"): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

STEP_REAUTH_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class EpisodeResponseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Episode Response DSP Amplifier."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._host: str = ""
        self._port: int = DEFAULT_PORT
        self._username: str = ""
        self._password: str = ""
        self._amp_name: str = ""
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlowWithConfigEntry:
        """Get the options flow handler."""
        return EpisodeResponseOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user configuration step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._host = user_input[CONF_HOST].strip()
            self._port = user_input[CONF_PORT]
            self._username = user_input[CONF_USERNAME].strip()
            self._password = user_input[CONF_PASSWORD]

            # Basic host validation
            if not self._host:
                errors["base"] = "invalid_host"
            elif self._port < 1 or self._port > 65535:
                errors["base"] = "invalid_port"
            else:
                # Test the connection
                result = await EpisodeResponseClient.test_connection(
                    self._host, self._port, self._username, self._password
                )

                if result.get("success"):
                    self._amp_name = result.get("name", "")

                    # Check for duplicate entries
                    await self.async_set_unique_id(
                        f"{self._host}:{self._port}"
                    )
                    self._abort_if_unique_id_configured()

                    title = self._amp_name or f"{INTEGRATION_TITLE} ({self._host})"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_HOST: self._host,
                            CONF_PORT: self._port,
                            CONF_USERNAME: self._username,
                            CONF_PASSWORD: self._password,
                        },
                        options={
                            CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                        },
                    )

                # Determine error type
                error_msg = result.get("error", "")
                if "password" in error_msg.lower() or "authentication" in error_msg.lower():
                    errors["base"] = "invalid_auth"
                elif "locked" in error_msg.lower():
                    errors["base"] = "account_locked"
                elif "default password" in error_msg.lower():
                    errors["base"] = "default_password"
                elif "connect" in error_msg.lower() or "timeout" in error_msg.lower():
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "unknown"

                _LOGGER.warning("Config flow connection test failed: %s", error_msg)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_port": str(DEFAULT_PORT),
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication flow."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle re-auth credential confirmation."""
        errors: dict[str, str] = {}

        if user_input is not None and self._reauth_entry is not None:
            host = self._reauth_entry.data[CONF_HOST]
            port = self._reauth_entry.data[CONF_PORT]
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]

            result = await EpisodeResponseClient.test_connection(
                host, port, username, password
            )

            if result.get("success"):
                self.hass.config_entries.async_update_entry(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )
                await self.hass.config_entries.async_reload(
                    self._reauth_entry.entry_id
                )
                return self.async_abort(reason="reauth_successful")

            error_msg = result.get("error", "")
            if "password" in error_msg.lower() or "authentication" in error_msg.lower():
                errors["base"] = "invalid_auth"
            else:
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_DATA_SCHEMA,
            errors=errors,
        )


class EpisodeResponseOptionsFlow(OptionsFlowWithConfigEntry):
    """Handle options for Episode Response DSP Amplifier."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=current_interval,
                    ): vol.All(
                        vol.Coerce(int),
                        vol.Range(min=MIN_POLL_INTERVAL, max=MAX_POLL_INTERVAL),
                    ),
                }
            ),
        )
