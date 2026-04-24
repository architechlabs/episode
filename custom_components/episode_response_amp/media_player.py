"""Media player platform for Episode Response DSP Amplifier.

Creates one media_player entity per zone (6 total). Each entity supports:
- Volume control (level + mute)
- Source selection (6 analog inputs)
- Power on/off (zone enable)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from homeassistant.const import ATTR_ENTITY_ID

from .const import DOMAIN, NUM_ZONES, SOURCE_MAP
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .entity import EpisodeResponseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Episode Response media player entities."""
    data: EpisodeResponseData = entry.runtime_data
    coordinator = data.coordinator

    entities = [
        EpisodeResponseZonePlayer(coordinator, zone_index)
        for zone_index in range(NUM_ZONES)
    ]
    async_add_entities(entities)


class EpisodeResponseZonePlayer(EpisodeResponseEntity, MediaPlayerEntity):
    """Media player entity for a single amplifier zone."""

    _attr_device_class = MediaPlayerDeviceClass.RECEIVER
    _attr_icon = "mdi:amplifier"
    _attr_supported_features = (
        MediaPlayerEntityFeature.VOLUME_SET
        | MediaPlayerEntityFeature.VOLUME_MUTE
        | MediaPlayerEntityFeature.VOLUME_STEP
        | MediaPlayerEntityFeature.SELECT_SOURCE
        | MediaPlayerEntityFeature.TURN_ON
        | MediaPlayerEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: EpisodeResponseCoordinator,
        zone_index: int,
    ) -> None:
        """Initialize the zone media player."""
        super().__init__(coordinator, zone_index=zone_index, key="player")
        self._zone_index = zone_index

        # Build the source list from the state (will update dynamically)
        self._source_list: list[str] = list(SOURCE_MAP.values())
        self._source_reverse: dict[str, int] = {v: k for k, v in SOURCE_MAP.items()}

    @property
    def _zone(self):
        """Shortcut to the zone state object."""
        return self.coordinator.client.state.zones[self._zone_index]

    @property
    def _linked_player_entity_id(self) -> str | None:
        """Return a linked HA media_player entity_id for this zone, if configured."""
        hass = self.hass
        if hass is None:
            return None
        domain_data = hass.data.get(DOMAIN, {})
        entry_data = domain_data.get(self.coordinator.config_entry.entry_id, {})
        links: dict[int, str] = entry_data.get("zone_links", {})
        entity_id = links.get(self._zone_index)
        if isinstance(entity_id, str) and entity_id.startswith("media_player."):
            return entity_id
        return None

    @property
    def _linked_state(self):
        """Return the HA State object for the linked player, if available."""
        entity_id = self._linked_player_entity_id
        if not entity_id or self.hass is None:
            return None
        return self.hass.states.get(entity_id)

    @property
    def name(self) -> str:
        """Return the zone name."""
        zone_name = self._zone.name
        if zone_name:
            return zone_name
        return f"Zone {self._zone_index + 1}"

    @property
    def state(self) -> MediaPlayerState:
        """Return the zone power state."""
        amp_state = self.coordinator.client.state
        if amp_state.standby:
            return MediaPlayerState.OFF
        if not self._zone.enabled:
            return MediaPlayerState.OFF

        linked = self._linked_state
        if linked is not None:
            # Mirror linked player's state where possible.
            if linked.state == "playing":
                return MediaPlayerState.PLAYING
            if linked.state == "paused":
                return MediaPlayerState.PAUSED
            if linked.state in {"idle", "standby", "on"}:
                return MediaPlayerState.IDLE
            if linked.state == "off":
                return MediaPlayerState.IDLE

        if self._zone.muted:
            return MediaPlayerState.IDLE
        return MediaPlayerState.ON

    @property
    def volume_level(self) -> float | None:
        """Return the volume as a float 0..1."""
        return self._zone.volume_percent

    @property
    def is_volume_muted(self) -> bool | None:
        """Return True if the zone is muted."""
        return self._zone.muted

    @property
    def source(self) -> str | None:
        """Return the current source name."""
        source_idx = self._zone.source1
        # Try to use the input name from the amp state
        input_state = self.coordinator.client.state.inputs.get(source_idx)
        if input_state and input_state.name:
            return input_state.name
        return SOURCE_MAP.get(source_idx, f"Input {source_idx + 1}")

    @property
    def source_list(self) -> list[str]:
        """Return the list of available sources."""
        sources = []
        for i in range(6):
            input_state = self.coordinator.client.state.inputs.get(i)
            if input_state and input_state.name:
                sources.append(input_state.name)
            else:
                sources.append(SOURCE_MAP.get(i, f"Input {i + 1}"))
        return sources

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes for the zone."""
        zone = self._zone
        attrs: dict[str, Any] = {
            "zone_index": self._zone_index,
            "volume_db": zone.volume_db,
            "source_index": zone.source1,
            "source2_index": zone.source2,
            "bass": zone.bass,
            "treble": zone.treble,
            "balance": zone.balance,
            "loudness": zone.loudness,
            "delay_ms": zone.delay,
            "limiter": zone.limiter,
            "bridge_mode": zone.bridge,
            "zone_enabled": zone.enabled,
        }
        linked_id = self._linked_player_entity_id
        if linked_id:
            attrs["linked_player"] = linked_id
        return attrs

    @property
    def supported_features(self) -> int:
        """Dynamically add transport features when linked."""
        base = int(self._attr_supported_features)
        if self._linked_player_entity_id:
            base |= (
                MediaPlayerEntityFeature.PLAY
                | MediaPlayerEntityFeature.PAUSE
                | MediaPlayerEntityFeature.STOP
                | MediaPlayerEntityFeature.NEXT_TRACK
                | MediaPlayerEntityFeature.PREVIOUS_TRACK
                | MediaPlayerEntityFeature.PLAY_MEDIA
            )
        return base

    @property
    def media_title(self) -> str | None:
        linked = self._linked_state
        if linked is None:
            return None
        return linked.attributes.get("media_title")

    @property
    def media_artist(self) -> str | None:
        linked = self._linked_state
        if linked is None:
            return None
        return linked.attributes.get("media_artist")

    @property
    def media_album_name(self) -> str | None:
        linked = self._linked_state
        if linked is None:
            return None
        return linked.attributes.get("media_album_name")

    @property
    def media_image_url(self) -> str | None:
        linked = self._linked_state
        if linked is None:
            return None
        return linked.attributes.get("entity_picture")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_set_volume_level(self, volume: float) -> None:
        """Set the volume level (0..1)."""
        volume_db = int(round(volume * 80 - 80))
        volume_db = max(-80, min(0, volume_db))
        await self.coordinator.client.set_zone_volume(self._zone_index, volume_db)
        self._zone.volume_db = volume_db
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        """Increase volume by 1 dB."""
        new_vol = min(0, self._zone.volume_db + 1)
        await self.coordinator.client.set_zone_volume(self._zone_index, new_vol)
        self._zone.volume_db = new_vol
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        """Decrease volume by 1 dB."""
        new_vol = max(-80, self._zone.volume_db - 1)
        await self.coordinator.client.set_zone_volume(self._zone_index, new_vol)
        self._zone.volume_db = new_vol
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute or unmute the zone."""
        await self.coordinator.client.set_zone_mute(self._zone_index, mute)
        self._zone.muted = mute
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_select_source(self, source: str) -> None:
        """Select an input source by name."""
        # Try to match by input name first
        for i in range(6):
            input_state = self.coordinator.client.state.inputs.get(i)
            if input_state and input_state.name == source:
                await self.coordinator.client.set_zone_source(self._zone_index, i)
                self._zone.source1 = i
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return

        # Fall back to default source map
        if source in self._source_reverse:
            idx = self._source_reverse[source]
            await self.coordinator.client.set_zone_source(self._zone_index, idx)
            self._zone.source1 = idx
            self.async_write_ha_state()
            await self.coordinator.async_request_refresh()
            return

        _LOGGER.warning("Unknown source '%s' for zone %d", source, self._zone_index)

    async def async_turn_on(self) -> None:
        """Turn on the zone (enable + wake from standby if needed)."""
        amp_state = self.coordinator.client.state
        if amp_state.standby:
            await self.coordinator.client.set_standby(False)
            amp_state.standby = False

        if not self._zone.enabled:
            await self.coordinator.client.set_zone_enable(self._zone_index, True)
            self._zone.enabled = True

        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self) -> None:
        """Turn off the zone (disable output)."""
        await self.coordinator.client.set_zone_enable(self._zone_index, False)
        self._zone.enabled = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_play_media(self, media_type: str, media_id: str, **kwargs: Any) -> None:
        """Forward play_media to the linked player if configured."""
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            raise ValueError("No linked media player configured for this zone")
        await self.hass.services.async_call(
            "media_player",
            "play_media",
            {
                ATTR_ENTITY_ID: linked,
                "media_content_type": media_type,
                "media_content_id": media_id,
                **kwargs,
            },
            blocking=True,
        )

    async def async_media_play(self) -> None:
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            return
        await self.hass.services.async_call(
            "media_player", "media_play", {ATTR_ENTITY_ID: linked}, blocking=True
        )

    async def async_media_pause(self) -> None:
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            return
        await self.hass.services.async_call(
            "media_player", "media_pause", {ATTR_ENTITY_ID: linked}, blocking=True
        )

    async def async_media_stop(self) -> None:
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            return
        await self.hass.services.async_call(
            "media_player", "media_stop", {ATTR_ENTITY_ID: linked}, blocking=True
        )

    async def async_media_next_track(self) -> None:
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            return
        await self.hass.services.async_call(
            "media_player", "media_next_track", {ATTR_ENTITY_ID: linked}, blocking=True
        )

    async def async_media_previous_track(self) -> None:
        linked = self._linked_player_entity_id
        if not linked or self.hass is None:
            return
        await self.hass.services.async_call(
            "media_player", "media_previous_track", {ATTR_ENTITY_ID: linked}, blocking=True
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
