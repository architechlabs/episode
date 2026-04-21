"""Base entity for Episode Response DSP Amplifier."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import EpisodeResponseCoordinator


class EpisodeResponseEntity(CoordinatorEntity[EpisodeResponseCoordinator]):
    """Base entity for all Episode Response amplifier entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EpisodeResponseCoordinator,
        zone_index: int | None = None,
        key: str = "",
    ) -> None:
        """Initialize the base entity."""
        super().__init__(coordinator)
        self._zone_index = zone_index
        self._key = key

        client = coordinator.client
        amp_id = client.state.mac_address or f"{client.host}:{client.port}"

        if zone_index is not None:
            self._attr_unique_id = f"{amp_id}_zone{zone_index}_{key}"
        else:
            self._attr_unique_id = f"{amp_id}_{key}"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, amp_id)},
            manufacturer=MANUFACTURER,
            model=DEFAULT_MODEL,
            name=client.state.name or f"Episode Response Amp ({client.host})",
            sw_version=client.state.firmware or None,
            configuration_url=f"http://{client.host}",
        )

    @property
    def available(self) -> bool:
        """Return True when the coordinator has fresh data from the amplifier.

        CoordinatorEntity.available already returns False when the last update
        failed, so there is no need to additionally gate on the client's
        transport-level connected flag (which can be transiently False between
        polls even while data is stale-but-valid).
        """
        return super().available
