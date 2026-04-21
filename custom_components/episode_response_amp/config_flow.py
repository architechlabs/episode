"""Config flow for Episode Response DSP Amplifier."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import network
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

_LOGGER = logging.getLogger(__name__)

MAX_DISCOVERY_HOSTS = 512
MAX_DISCOVERY_VALIDATIONS = 12
DISCOVERY_PROBE_TIMEOUT = 0.8
DISCOVERY_PROBE_CONCURRENCY = 48
DISCOVERY_VALIDATE_CONCURRENCY = 6

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_HOST, default=""): str,
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
        self._discovered_hosts: list[dict[str, str]] = []
        self._reauth_entry: ConfigEntry | None = None

    @staticmethod
    def _error_key_from_message(error_msg: str) -> str:
        """Map low-level connection errors to user-facing config flow errors."""
        lowered = error_msg.lower()

        if "password" in lowered or "authentication" in lowered:
            return "invalid_auth"
        if "locked" in lowered:
            return "account_locked"
        if "default password" in lowered:
            return "default_password"
        if (
            "connect" in lowered
            or "timeout" in lowered
            or "timed out" in lowered
            or "refused" in lowered
            or "not connected" in lowered
        ):
            return "cannot_connect"
        return "unknown"

    async def _async_create_amp_entry(self) -> ConfigFlowResult:
        """Create the config entry for the currently stored host details."""
        await self.async_set_unique_id(f"{self._host}:{self._port}")
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

    async def _async_candidate_hosts(self) -> list[str]:
        """Build candidate local-network hosts for discovery."""
        try:
            adapters = await network.async_get_adapters(self.hass)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("Unable to query network adapters for discovery: %s", err)
            return []

        candidates: set[str] = set()

        for adapter in adapters:
            for ip4 in adapter.get("ipv4", []):
                address = ip4.get("address")
                prefix = ip4.get("network_prefix")
                if not address or prefix is None:
                    continue

                try:
                    local_ip = ipaddress.ip_address(address)
                except ValueError:
                    continue

                if local_ip.is_loopback or local_ip.is_link_local:
                    continue

                # Avoid scanning huge subnets; cap to /24 when network is broader.
                scan_prefix = prefix if prefix >= 24 else 24
                try:
                    subnet = ipaddress.ip_network(
                        f"{address}/{scan_prefix}", strict=False
                    )
                except ValueError:
                    continue

                for host in subnet.hosts():
                    if host == local_ip:
                        continue
                    candidates.add(str(host))
                    if len(candidates) >= MAX_DISCOVERY_HOSTS:
                        break

                if len(candidates) >= MAX_DISCOVERY_HOSTS:
                    break

            if len(candidates) >= MAX_DISCOVERY_HOSTS:
                break

        return sorted(candidates)

    async def _async_discover_amplifiers(self) -> list[dict[str, str]]:
        """Discover amplifiers on local subnets by probing port + credentials."""
        candidate_hosts = await self._async_candidate_hosts()
        if not candidate_hosts:
            return []

        _LOGGER.debug(
            "Discovery scanning %d candidate hosts on port %d",
            len(candidate_hosts),
            self._port,
        )

        open_hosts: list[str] = []
        probe_sem = asyncio.Semaphore(DISCOVERY_PROBE_CONCURRENCY)

        async def _probe(host: str) -> None:
            async with probe_sem:
                if await EpisodeResponseClient.probe_port(
                    host,
                    self._port,
                    timeout=DISCOVERY_PROBE_TIMEOUT,
                ):
                    open_hosts.append(host)

        await asyncio.gather(*(_probe(host) for host in candidate_hosts))

        if not open_hosts:
            _LOGGER.debug("Discovery found no hosts with open TCP port %d", self._port)
            return []

        # Keep discovery snappy even on busy subnets.
        hosts_to_validate = sorted(open_hosts)[:MAX_DISCOVERY_VALIDATIONS]
        discovered: list[dict[str, str]] = []
        validate_sem = asyncio.Semaphore(DISCOVERY_VALIDATE_CONCURRENCY)

        async def _validate(host: str) -> None:
            async with validate_sem:
                result = await EpisodeResponseClient.test_connection(
                    host,
                    self._port,
                    self._username,
                    self._password,
                    attempts=1,
                )
                if result.get("success"):
                    discovered.append(
                        {
                            "host": host,
                            "name": str(result.get("name", "") or "").strip(),
                        }
                    )

        await asyncio.gather(*(_validate(host) for host in hosts_to_validate))

        return sorted(discovered, key=lambda item: item["host"])

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

            # Basic port validation
            if self._port < 1 or self._port > 65535:
                errors["base"] = "invalid_port"
            else:
                if self._host:
                    # Test explicit host
                    result = await EpisodeResponseClient.test_connection(
                        self._host,
                        self._port,
                        self._username,
                        self._password,
                    )

                    if result.get("success"):
                        self._amp_name = str(result.get("name", "") or "").strip()
                        return await self._async_create_amp_entry()

                    error_msg = str(result.get("error", "") or "")
                    errors["base"] = self._error_key_from_message(error_msg)
                    _LOGGER.warning(
                        "Config flow connection test failed for %s:%s: %s",
                        self._host,
                        self._port,
                        error_msg,
                    )
                else:
                    # Auto-discovery path (host left blank)
                    self._discovered_hosts = await self._async_discover_amplifiers()

                    if not self._discovered_hosts:
                        errors["base"] = "cannot_discover"
                    elif len(self._discovered_hosts) == 1:
                        only = self._discovered_hosts[0]
                        self._host = only["host"]
                        self._amp_name = only.get("name", "")
                        return await self._async_create_amp_entry()
                    else:
                        return await self.async_step_select_host()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={
                "default_port": str(DEFAULT_PORT),
            },
        )

    async def async_step_select_host(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user choose a discovered amplifier when multiple are found."""
        errors: dict[str, str] = {}

        if not self._discovered_hosts:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_DATA_SCHEMA,
                errors={"base": "cannot_discover"},
                description_placeholders={
                    "default_port": str(DEFAULT_PORT),
                },
            )

        if user_input is not None:
            selected_host = str(user_input[CONF_HOST]).strip()
            selected = next(
                (item for item in self._discovered_hosts if item["host"] == selected_host),
                None,
            )
            if selected is None:
                errors["base"] = "invalid_host"
            else:
                self._host = selected_host
                self._amp_name = selected.get("name", "")
                return await self._async_create_amp_entry()

        options = {
            item["host"]: (
                f"{item['host']} ({item['name']})" if item.get("name") else item["host"]
            )
            for item in self._discovered_hosts
        }

        return self.async_show_form(
            step_id="select_host",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): vol.In(options),
                }
            ),
            errors=errors,
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

            error_msg = str(result.get("error", "") or "")
            errors["base"] = self._error_key_from_message(error_msg)

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
