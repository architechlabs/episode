"""Data models for the Episode Response DSP Amplifier integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ZoneState:
    """Represents the state of a single amplifier zone (output pair)."""

    index: int
    name: str = ""
    volume_db: int = -80
    muted: bool = False
    enabled: bool = True
    source1: int = 0
    source2: int = 0
    dsp_preset: int = 0
    bass: int = 0
    treble: int = 0
    balance: int = 0
    loudness: bool = False
    delay: int = 0
    limiter: bool = False
    bridge: bool = False

    @property
    def volume_percent(self) -> float:
        """Convert dB volume (-80..0) to 0..1 percentage."""
        return max(0.0, min(1.0, (self.volume_db + 80) / 80.0))

    @volume_percent.setter
    def volume_percent(self, value: float) -> None:
        """Set volume from 0..1 percentage to dB."""
        self.volume_db = int(round(value * 80 - 80))


@dataclass
class InputState:
    """Represents the state of an input source."""

    index: int
    name: str = ""
    gain: int = 0


@dataclass
class AmplifierState:
    """Full state snapshot of an Episode Response amplifier."""

    # Identification
    name: str = ""
    firmware: str = ""
    mac_address: str = ""
    serial_number: str = ""
    ip_address: str = ""

    # Operating state
    mode: int = 0  # 0=On, 1=Standby, 2=VTrigger, 3=AudioSense
    temperature: float | None = None
    standby: bool = False

    # Zones (6 stereo output pairs)
    zones: dict[int, ZoneState] = field(default_factory=dict)

    # Inputs (6 analog sources)
    inputs: dict[int, InputState] = field(default_factory=dict)

    # Connection state (not from API — tracked locally)
    connected: bool = False
    last_status_code: int = 0
    last_error: str = ""

    def __post_init__(self) -> None:
        """Initialize zone & input dicts if empty."""
        if not self.zones:
            self.zones = {i: ZoneState(index=i) for i in range(6)}
        if not self.inputs:
            self.inputs = {i: InputState(index=i) for i in range(6)}

    @property
    def is_on(self) -> bool:
        """True if the amplifier is not in standby."""
        return not self.standby and self.mode == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize full state to a dictionary (for diagnostics)."""
        return {
            "name": self.name,
            "firmware": self.firmware,
            "mac_address": self.mac_address,
            "serial_number": self.serial_number,
            "ip_address": self.ip_address,
            "mode": self.mode,
            "temperature": self.temperature,
            "standby": self.standby,
            "connected": self.connected,
            "last_status_code": self.last_status_code,
            "last_error": self.last_error,
            "zones": {
                i: {
                    "name": z.name,
                    "volume_db": z.volume_db,
                    "muted": z.muted,
                    "enabled": z.enabled,
                    "source1": z.source1,
                    "source2": z.source2,
                    "dsp_preset": z.dsp_preset,
                    "bass": z.bass,
                    "treble": z.treble,
                    "balance": z.balance,
                    "loudness": z.loudness,
                    "delay": z.delay,
                    "limiter": z.limiter,
                    "bridge": z.bridge,
                }
                for i, z in self.zones.items()
            },
            "inputs": {
                i: {"name": inp.name, "gain": inp.gain}
                for i, inp in self.inputs.items()
            },
        }
