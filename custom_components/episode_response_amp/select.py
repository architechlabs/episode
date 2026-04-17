"""Select platform for Episode Response DSP Amplifier.

Provides:
- Per-zone DSP preset selector
- Per-zone source selector (alternative to media_player source)
- Amplifier operating mode selector
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AMP_MODES, DOMAIN, DSP_PRESETS, NUM_ZONES, SOURCE_MAP
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .entity import EpisodeResponseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Episode Response select entities."""
    data: EpisodeResponseData = entry.runtime_data
    coordinator = data.coordinator

    entities: list[SelectEntity] = []

    # Per-zone DSP preset & source selectors
    for zone_idx in range(NUM_ZONES):
        entities.append(EpisodeResponseDspPresetSelect(coordinator, zone_idx))
        entities.append(EpisodeResponseSourceSelect(coordinator, zone_idx))

    # Amplifier operating mode
    entities.append(EpisodeResponseModeSelect(coordinator))

    async_add_entities(entities)


class EpisodeResponseDspPresetSelect(EpisodeResponseEntity, SelectEntity):
    """DSP preset selector for a zone."""

    _attr_icon = "mdi:equalizer"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="dsp_preset")
        self._zone_index = zone_index
        self._attr_options = list(DSP_PRESETS.values())
        self._attr_translation_key = "dsp_preset"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} DSP Preset"

    @property
    def current_option(self) -> str | None:
        preset_idx = self.coordinator.client.state.zones[self._zone_index].dsp_preset
        return DSP_PRESETS.get(preset_idx, "Flat")

    async def async_select_option(self, option: str) -> None:
        """Set the DSP preset."""
        # Reverse lookup
        for idx, name in DSP_PRESETS.items():
            if name == option:
                await self.coordinator.client.set_zone_dsp_preset(self._zone_index, idx)
                self.coordinator.client.state.zones[self._zone_index].dsp_preset = idx
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
        _LOGGER.warning("Unknown DSP preset: %s", option)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseSourceSelect(EpisodeResponseEntity, SelectEntity):
    """Source input selector for a zone."""

    _attr_icon = "mdi:audio-input-stereo-minijack"

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="source_select")
        self._zone_index = zone_index
        self._attr_translation_key = "source"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Source"

    @property
    def options(self) -> list[str]:
        """Build options dynamically from input names."""
        sources = []
        for i in range(6):
            inp = self.coordinator.client.state.inputs.get(i)
            if inp and inp.name:
                sources.append(inp.name)
            else:
                sources.append(SOURCE_MAP.get(i, f"Input {i + 1}"))
        return sources

    @property
    def current_option(self) -> str | None:
        source_idx = self.coordinator.client.state.zones[self._zone_index].source1
        inp = self.coordinator.client.state.inputs.get(source_idx)
        if inp and inp.name:
            return inp.name
        return SOURCE_MAP.get(source_idx, f"Input {source_idx + 1}")

    async def async_select_option(self, option: str) -> None:
        """Set the source input."""
        for i in range(6):
            inp = self.coordinator.client.state.inputs.get(i)
            if inp and inp.name == option:
                await self.coordinator.client.set_zone_source(self._zone_index, i)
                self.coordinator.client.state.zones[self._zone_index].source1 = i
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
        # Fallback to default map
        for idx, name in SOURCE_MAP.items():
            if name == option:
                await self.coordinator.client.set_zone_source(self._zone_index, idx)
                self.coordinator.client.state.zones[self._zone_index].source1 = idx
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
        _LOGGER.warning("Unknown source: %s", option)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseModeSelect(EpisodeResponseEntity, SelectEntity):
    """Amplifier operating mode selector."""

    _attr_icon = "mdi:power-settings"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: EpisodeResponseCoordinator) -> None:
        super().__init__(coordinator, key="amp_mode")
        self._attr_options = list(AMP_MODES.values())
        self._attr_translation_key = "amp_mode"

    @property
    def name(self) -> str:
        return "Operating Mode"

    @property
    def current_option(self) -> str | None:
        mode = self.coordinator.client.state.mode
        return AMP_MODES.get(mode, "On")

    async def async_select_option(self, option: str) -> None:
        """Set the amplifier operating mode."""
        for code, name in AMP_MODES.items():
            if name == option:
                await self.coordinator.client.set_mode(code)
                self.coordinator.client.state.mode = code
                self.async_write_ha_state()
                await self.coordinator.async_request_refresh()
                return
        _LOGGER.warning("Unknown mode: %s", option)

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
