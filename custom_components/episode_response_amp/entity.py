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

        # Stable unique-id anchor: prefer MAC (populated after first identity
        # fetch), fall back to host:port.  We cache the raw anchor at init
        # time so the unique-id never changes even if MAC is fetched later.
        client = coordinator.client
        self._amp_id: str = (
            client.state.mac_address or f"{client.host}:{client.port}"
        )

        if zone_index is not None:
            self._attr_unique_id = f"{self._amp_id}_zone{zone_index}_{key}"
        else:
            self._attr_unique_id = f"{self._amp_id}_{key}"

    # ------------------------------------------------------------------
    # Device info is a live property so it automatically reflects identity
    # data (firmware, name, serial) once the coordinator fetches it.
    # ------------------------------------------------------------------

    @property
    def device_info(self) -> DeviceInfo:
        """Return up-to-date device info, including any fetched identity data."""
        client = self.coordinator.client
        state = client.state

        # Prefer the real MAC/serial as identifier once available.
        amp_id = state.mac_address or self._amp_id

        return DeviceInfo(
            identifiers={(DOMAIN, amp_id)},
            manufacturer=MANUFACTURER,
            # DEFAULT_MODEL is the actual hardware part number; if the device
            # exposes a model string in the future we can slot it in here.
            model=DEFAULT_MODEL,
            serial_number=state.serial_number or None,
            name=state.name or f"Episode Response Amp ({client.host})",
            sw_version=state.firmware or None,
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
