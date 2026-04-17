"""Switch platform for Episode Response DSP Amplifier.

Provides per-zone switches for:
- Loudness compensation
- Limiter
- Bridge mode
- Zone enable/disable (power)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NUM_ZONES
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .entity import EpisodeResponseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Episode Response switch entities."""
    data: EpisodeResponseData = entry.runtime_data
    coordinator = data.coordinator

    entities: list[SwitchEntity] = []

    for zone_idx in range(NUM_ZONES):
        entities.append(EpisodeResponseLoudnessSwitch(coordinator, zone_idx))
        entities.append(EpisodeResponseLimiterSwitch(coordinator, zone_idx))
        entities.append(EpisodeResponseBridgeSwitch(coordinator, zone_idx))
        entities.append(EpisodeResponseZoneEnableSwitch(coordinator, zone_idx))

    # Amplifier standby switch
    entities.append(EpisodeResponseStandbySwitch(coordinator))

    async_add_entities(entities)


class EpisodeResponseLoudnessSwitch(EpisodeResponseEntity, SwitchEntity):
    """Loudness compensation switch for a zone."""

    _attr_icon = "mdi:volume-vibrate"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="loudness")
        self._zone_index = zone_index
        self._attr_translation_key = "loudness"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Loudness"

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.state.zones[self._zone_index].loudness

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_loudness(self._zone_index, True)
        self.coordinator.client.state.zones[self._zone_index].loudness = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_loudness(self._zone_index, False)
        self.coordinator.client.state.zones[self._zone_index].loudness = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseLimiterSwitch(EpisodeResponseEntity, SwitchEntity):
    """Limiter switch for a zone."""

    _attr_icon = "mdi:speedometer"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="limiter")
        self._zone_index = zone_index
        self._attr_translation_key = "limiter"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Limiter"

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.state.zones[self._zone_index].limiter

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_limiter(self._zone_index, True)
        self.coordinator.client.state.zones[self._zone_index].limiter = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_limiter(self._zone_index, False)
        self.coordinator.client.state.zones[self._zone_index].limiter = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseBridgeSwitch(EpisodeResponseEntity, SwitchEntity):
    """Bridge mode switch for a zone."""

    _attr_icon = "mdi:bridge"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False  # Advanced feature

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="bridge")
        self._zone_index = zone_index
        self._attr_translation_key = "bridge"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Bridge Mode"

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.state.zones[self._zone_index].bridge

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_bridge(self._zone_index, True)
        self.coordinator.client.state.zones[self._zone_index].bridge = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_bridge(self._zone_index, False)
        self.coordinator.client.state.zones[self._zone_index].bridge = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseZoneEnableSwitch(EpisodeResponseEntity, SwitchEntity):
    """Zone enable/disable (power) switch."""

    _attr_device_class = SwitchDeviceClass.SWITCH
    _attr_icon = "mdi:power"

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="zone_enable")
        self._zone_index = zone_index
        self._attr_translation_key = "zone_enable"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Enabled"

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.state.zones[self._zone_index].enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_enable(self._zone_index, True)
        self.coordinator.client.state.zones[self._zone_index].enabled = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.client.set_zone_enable(self._zone_index, False)
        self.coordinator.client.state.zones[self._zone_index].enabled = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseStandbySwitch(EpisodeResponseEntity, SwitchEntity):
    """Amplifier standby switch (on = in standby, off = active)."""

    _attr_icon = "mdi:power-standby"

    def __init__(self, coordinator: EpisodeResponseCoordinator) -> None:
        super().__init__(coordinator, key="standby")
        self._attr_translation_key = "standby"

    @property
    def name(self) -> str:
        return "Standby"

    @property
    def is_on(self) -> bool:
        return self.coordinator.client.state.standby

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enter standby."""
        await self.coordinator.client.set_standby(True)
        self.coordinator.client.state.standby = True
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Exit standby (wake up)."""
        await self.coordinator.client.set_standby(False)
        self.coordinator.client.state.standby = False
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
