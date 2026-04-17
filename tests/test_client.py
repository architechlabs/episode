"""Tests for the Episode Response DSP Amplifier client."""

from __future__ import annotations

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os

# Add repo root to path so custom_components package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from custom_components.episode_response_amp.client import EpisodeResponseClient  # noqa: E402
from custom_components.episode_response_amp.errors import (  # noqa: E402
    AuthenticationFailed,
    ConnectionFailed,
)
from custom_components.episode_response_amp.models import AmplifierState  # noqa: E402


class FakeStreamReader:
    """Fake asyncio.StreamReader for testing."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = responses
        self._idx = 0

    async def read(self, n: int) -> bytes:
        if self._idx >= len(self._responses):
            return b""
        resp = self._responses[self._idx]
        self._idx += 1
        return json.dumps(resp).encode("utf-8") + b"\x00"


class FakeStreamWriter:
    """Fake asyncio.StreamWriter for testing."""

    def __init__(self) -> None:
        self.written: list[bytes] = []
        self._closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass


@pytest.fixture
def amp_state() -> AmplifierState:
    """Create a fresh amplifier state."""
    return AmplifierState()


class TestAmplifierState:
    """Test AmplifierState model."""

    def test_default_zones(self, amp_state: AmplifierState) -> None:
        assert len(amp_state.zones) == 6
        assert len(amp_state.inputs) == 6

    def test_is_on_active(self, amp_state: AmplifierState) -> None:
        amp_state.standby = False
        amp_state.mode = 0
        assert amp_state.is_on is True

    def test_is_on_standby(self, amp_state: AmplifierState) -> None:
        amp_state.standby = True
        assert amp_state.is_on is False

    def test_volume_percent_conversion(self, amp_state: AmplifierState) -> None:
        zone = amp_state.zones[0]
        zone.volume_db = -40
        assert abs(zone.volume_percent - 0.5) < 0.02

        zone.volume_percent = 1.0
        assert zone.volume_db == 0

        zone.volume_percent = 0.0
        assert zone.volume_db == -80

    def test_to_dict(self, amp_state: AmplifierState) -> None:
        d = amp_state.to_dict()
        assert "zones" in d
        assert "inputs" in d
        assert len(d["zones"]) == 6
        assert len(d["inputs"]) == 6


class TestEpisodeResponseClient:
    """Test the TCP client."""

    @pytest.mark.asyncio
    async def test_test_connection_success(self) -> None:
        """Test the static test_connection helper."""
        login_resp = {"type": "login", "status": 200}
        amp_name_resp = {"type": "get_ampname", "status": 200, "value": "TestAmp"}
        fw_resp = {"type": "get_firmware", "status": 200, "value": "1.2.3"}
        mac_resp = {"type": "get_mac", "status": 200, "value": "AA:BB:CC:DD:EE:FF"}
        serial_resp = {"type": "get_serial", "status": 200, "value": "SN12345"}
        standby_resp = {"type": "get_standby", "status": 200, "value": 0}
        logout_resp = {"type": "logout", "status": 200}

        reader = FakeStreamReader([
            login_resp,
            amp_name_resp, fw_resp, mac_resp, serial_resp,
            amp_name_resp,
            standby_resp,  # heartbeat
            logout_resp,
        ])
        writer = FakeStreamWriter()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await EpisodeResponseClient.test_connection(
                "192.168.1.100", 8080, "admin", "password123"
            )

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_test_connection_auth_failure(self) -> None:
        """Test that auth failure is reported."""
        login_resp = {"type": "login", "status": 400}

        reader = FakeStreamReader([login_resp])
        writer = FakeStreamWriter()

        with patch("asyncio.open_connection", return_value=(reader, writer)):
            result = await EpisodeResponseClient.test_connection(
                "192.168.1.100", 8080, "admin", "wrong"
            )

        assert result["success"] is False
        assert "password" in result["error"].lower() or "authentication" in result["error"].lower()
