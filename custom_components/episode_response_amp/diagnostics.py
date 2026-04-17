"""Diagnostics support for Episode Response DSP Amplifier."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, __version__ as HA_VERSION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.redact import async_redact_data

from .const import INTEGRATION_VERSION
from .coordinator import EpisodeResponseData

TO_REDACT = {CONF_PASSWORD, CONF_USERNAME}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: EpisodeResponseData = entry.runtime_data
    client = data.client

    return {
        "integration_version": INTEGRATION_VERSION,
        "home_assistant_version": HA_VERSION,
        "config_entry": {
            "title": entry.title,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "amplifier_state": client.state.to_dict(),
        "connection": {
            "host": client.host,
            "port": client.port,
            "connected": client.connected,
            "uptime_seconds": client.connection_uptime,
            "last_successful_command": (
                client.last_successful_command.isoformat()
                if client.last_successful_command
                else None
            ),
            "consecutive_failures": client.consecutive_failures,
            "total_reconnects": client.total_reconnects,
        },
    }
