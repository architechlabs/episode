"""Sensor platform for Episode Response DSP Amplifier.

Provides:
- Amplifier temperature sensor
- Amplifier status sensor (mode)
- Per-zone volume (dB) sensor
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AMP_MODES, DOMAIN, NUM_ZONES, STATUS_CODE_MAP
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .entity import EpisodeResponseEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Episode Response sensor entities."""
    data: EpisodeResponseData = entry.runtime_data
    coordinator = data.coordinator

    entities: list[SensorEntity] = [
        EpisodeResponseTemperatureSensor(coordinator),
        EpisodeResponseStatusSensor(coordinator),
        EpisodeResponseFirmwareSensor(coordinator),
    ]

    # Per-zone volume dB sensors
    for zone_idx in range(NUM_ZONES):
        entities.append(EpisodeResponseVolumeDbSensor(coordinator, zone_idx))

    async_add_entities(entities)


class EpisodeResponseTemperatureSensor(EpisodeResponseEntity, SensorEntity):
    """Amplifier internal temperature sensor."""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_icon = "mdi:thermometer"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: EpisodeResponseCoordinator) -> None:
        super().__init__(coordinator, key="temperature")
        self._attr_translation_key = "temperature"

    @property
    def name(self) -> str:
        return "Temperature"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.client.state.temperature

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseStatusSensor(EpisodeResponseEntity, SensorEntity):
    """Amplifier operating mode / status sensor."""

    _attr_icon = "mdi:information-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: EpisodeResponseCoordinator) -> None:
        super().__init__(coordinator, key="status")
        self._attr_translation_key = "status"

    @property
    def name(self) -> str:
        return "Status"

    @property
    def native_value(self) -> str:
        state = self.coordinator.client.state
        if not state.connected:
            return "Disconnected"
        if state.standby:
            return "Standby"
        return AMP_MODES.get(state.mode, "Unknown")

    @property
    def extra_state_attributes(self) -> dict:
        state = self.coordinator.client.state
        attrs = {
            "mode_code": state.mode,
            "standby": state.standby,
            "connected": state.connected,
            "last_status_code": state.last_status_code,
        }
        if state.last_status_code in STATUS_CODE_MAP:
            attrs["last_status_message"] = STATUS_CODE_MAP[state.last_status_code]
        return attrs

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseFirmwareSensor(EpisodeResponseEntity, SensorEntity):
    """Amplifier firmware version sensor."""

    _attr_icon = "mdi:chip"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: EpisodeResponseCoordinator) -> None:
        super().__init__(coordinator, key="firmware")
        self._attr_translation_key = "firmware"

    @property
    def name(self) -> str:
        return "Firmware"

    @property
    def native_value(self) -> str | None:
        return self.coordinator.client.state.firmware or None

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()


class EpisodeResponseVolumeDbSensor(EpisodeResponseEntity, SensorEntity):
    """Per-zone volume in dB sensor (read-only informational)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "dB"
    _attr_icon = "mdi:volume-high"
    _attr_entity_registry_enabled_default = False

    def __init__(
        self, coordinator: EpisodeResponseCoordinator, zone_index: int
    ) -> None:
        super().__init__(coordinator, zone_index=zone_index, key="volume_db")
        self._zone_index = zone_index
        self._attr_translation_key = "volume_db"

    @property
    def name(self) -> str:
        zone = self.coordinator.client.state.zones[self._zone_index]
        zone_name = zone.name or f"Zone {self._zone_index + 1}"
        return f"{zone_name} Volume dB"

    @property
    def native_value(self) -> int:
        return self.coordinator.client.state.zones[self._zone_index].volume_db

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
