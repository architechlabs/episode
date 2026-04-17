"""Number platform for Episode Response DSP Amplifier.

Provides per-zone number entities for:
- Bass (-12..12 dB)
- Treble (-12..12 dB)
- Balance (-20..20)
- Delay (0..1000 ms)
- Input gain (-12..12 dB) per input
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, NUM_SOURCES, NUM_ZONES, BASS_MIN, BASS_MAX, TREBLE_MIN, TREBLE_MAX, BALANCE_MIN, BALANCE_MAX, DELAY_MIN, DELAY_MAX, GAIN_MIN, GAIN_MAX
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .entity import EpisodeResponseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Episode Response number entities."""
    data: EpisodeResponseData = entry.runtime_data
    coordinator = data.coordinator

    entities: list[NumberEntity] = []

    for zone_idx in range(NUM_ZONES):
        entities.append(EpisodeResponseBassNumber(coordinator, zone_idx))
        entities.append(EpisodeResponseTrebleNumber(coordinator, zone_idx))
        entities.append(EpisodeResponseBalanceNumber(coordinator, zone_idx))
        entities.append(EpisodeResponseDelayNumber(coordinator, zone_idx))

    for input_idx in range(NUM_SOURCES):
        entities.append(EpisodeResponseInputGainNumber(coordinator, input_idx))

    async_add_entities(entities)


class EpisodeResponseBassNumber(EpisodeResponseEntity, NumberEntity):
    """Zone bass control (-12..12 dB)."""

    _attr_icon = "mdi:music-note"
    _attr_native_min_value = BASS_MIN
    _attr_native_max_value = BASS_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="bass")
        self._zone_index = zone_index
        self._attr_translation_key = "bass"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Bass"

    @property
    def native_value(self) -> float:
        return self.coordinator.client.state.zones[self._zone_index].bass

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_zone_bass(self._zone_index, int(value))
        self.coordinator.client.state.zones[self._zone_index].bass = int(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseTrebleNumber(EpisodeResponseEntity, NumberEntity):
    """Zone treble control (-12..12 dB)."""

    _attr_icon = "mdi:music-clef-treble"
    _attr_native_min_value = TREBLE_MIN
    _attr_native_max_value = TREBLE_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="treble")
        self._zone_index = zone_index
        self._attr_translation_key = "treble"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Treble"

    @property
    def native_value(self) -> float:
        return self.coordinator.client.state.zones[self._zone_index].treble

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_zone_treble(self._zone_index, int(value))
        self.coordinator.client.state.zones[self._zone_index].treble = int(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseBalanceNumber(EpisodeResponseEntity, NumberEntity):
    """Zone balance control (-20..20)."""

    _attr_icon = "mdi:arrow-left-right"
    _attr_native_min_value = BALANCE_MIN
    _attr_native_max_value = BALANCE_MAX
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="balance")
        self._zone_index = zone_index
        self._attr_translation_key = "balance"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Balance"

    @property
    def native_value(self) -> float:
        return self.coordinator.client.state.zones[self._zone_index].balance

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_zone_balance(self._zone_index, int(value))
        self.coordinator.client.state.zones[self._zone_index].balance = int(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseDelayNumber(EpisodeResponseEntity, NumberEntity):
    """Zone delay control (0..1000 ms)."""

    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = DELAY_MIN
    _attr_native_max_value = DELAY_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "ms"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="delay")
        self._zone_index = zone_index
        self._attr_translation_key = "delay"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Delay"

    @property
    def native_value(self) -> float:
        return self.coordinator.client.state.zones[self._zone_index].delay

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_zone_delay(self._zone_index, int(value))
        self.coordinator.client.state.zones[self._zone_index].delay = int(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseInputGainNumber(EpisodeResponseEntity, NumberEntity):
    """Input gain control (-12..12 dB)."""

    _attr_icon = "mdi:knob"
    _attr_native_min_value = GAIN_MIN
    _attr_native_max_value = GAIN_MAX
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "dB"
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, input_index: int
    ) -> None:
        super().__init__(coordinator, key=f"input{input_index}_gain")
        self._input_index = input_index
        self._attr_translation_key = "input_gain"

    @property
    def name(self) -> str:
        inp = self.coordinator.client.state.inputs.get(self._input_index)
        inp_name = inp.name if inp and inp.name else f"Input {self._input_index + 1}"
        return f"{inp_name} Gain"

    @property
    def native_value(self) -> float:
        inp = self.coordinator.client.state.inputs.get(self._input_index)
        return inp.gain if inp else 0

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.client.set_input_gain(self._input_index, int(value))
        inp = self.coordinator.client.state.inputs.get(self._input_index)
        if inp:
            inp.gain = int(value)
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
