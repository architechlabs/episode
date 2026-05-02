"""DataUpdateCoordinator for Episode Response DSP Amplifier.

Manages polling, state caching, and entity update orchestration.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import EpisodeResponseClient
from .const import DEFAULT_POLL_INTERVAL, DOMAIN
from .errors import AuthenticationFailed, ConnectionFailed, EpisodeAmpError
from .models import AmplifierState

_LOGGER = logging.getLogger(__name__)

type EpisodeConfigEntry = ConfigEntry[EpisodeResponseData]


class EpisodeResponseData:
    """Runtime data stored in the config entry."""

    def __init__(
        self,
        client: EpisodeResponseClient,
        coordinator: EpisodeResponseCoordinator,
    ) -> None:
        self.client = client
        self.coordinator = coordinator


class EpisodeResponseCoordinator(DataUpdateCoordinator[AmplifierState]):
    """Coordinator that polls the Episode Response amplifier for state updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: EpisodeResponseClient,
        entry: ConfigEntry,
        poll_interval: int = DEFAULT_POLL_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.client = client

        try:
            super().__init__(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_{entry.entry_id}",
                update_interval=timedelta(seconds=poll_interval),
                config_entry=entry,
            )
        except TypeError:
            # Older Home Assistant cores did not accept config_entry in the
            # DataUpdateCoordinator constructor.
            super().__init__(
                hass,
                _LOGGER,
                name=f"{DOMAIN}_{entry.entry_id}",
                update_interval=timedelta(seconds=poll_interval),
            )
            self.config_entry = entry

    @property
    def amp_state(self) -> AmplifierState:
        """Return the current amplifier state (shortcut)."""
        return self.client.state

    async def _async_update_data(self) -> AmplifierState:
        """Fetch the latest state from the amplifier.

        Called automatically on the poll interval by HA's DataUpdateCoordinator.

        If the connection was lost since the last poll, reconnects inline before
        polling.  This gives fast recovery (within the next poll interval, default
        5 s) without the long exponential-back-off delays of a background reconnect
        loop that can leave entities unavailable for minutes.
        """
        # Reconnect inline if the connection was lost since the last poll.
        if not self.client.connected:
            try:
                _LOGGER.debug("Amplifier not connected — reconnecting before poll")
                await self.client.reconnect()
            except AuthenticationFailed as err:
                raise ConfigEntryAuthFailed(
                    f"Authentication failed during reconnect: {err}"
                ) from err
            except Exception as err:  # noqa: BLE001
                raise UpdateFailed(f"Cannot reconnect to amplifier: {err}") from err

        try:
            state = await self.client.poll_full_state()
            return state
        except AuthenticationFailed as err:
            # Trigger HA's reauth flow so the user can fix credentials
            raise ConfigEntryAuthFailed(
                f"Authentication failed: {err}"
            ) from err
        except ConnectionFailed as err:
            _LOGGER.warning("Connection lost during poll: %s", err)
            raise UpdateFailed(f"Connection failed: {err}") from err
        except EpisodeAmpError as err:
            _LOGGER.warning("Error polling amplifier: %s", err)
            raise UpdateFailed(f"Poll error: {err}") from err

    async def async_send_command(
        self, command: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command to the amplifier and trigger a state refresh."""
        result = await self.client.send_command(command)
        # Request an immediate data refresh after a command
        await self.async_request_refresh()
        return result
