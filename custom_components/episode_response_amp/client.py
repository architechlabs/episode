"""Async TCP client for Episode Response DSP Amplifier JSON API.

This module implements the low-level persistent TCP connection to the
amplifier, handling:
  - NULL-terminated JSON message framing
  - Authentication on every connection
  - Exponential-backoff reconnect with jitter
  - Heartbeat / keep-alive
  - Thread-safe command serialization via asyncio.Lock
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
import time
from contextlib import suppress
from collections.abc import Callable
from typing import Any

from .const import (
    CMD_GET_AMP_NAME,
    CMD_GET_FIRMWARE,
    CMD_GET_MAC,
    CMD_GET_SERIAL,
    CMD_GET_TEMPERATURE,
    CMD_LOGIN,
    CMD_LOGOUT,
    COMMAND_TIMEOUT,
    CONNECTION_TIMEOUT,
    HEARTBEAT_INTERVAL,
    NULL_TERMINATOR,
    RECONNECT_BASE_DELAY,
    RECONNECT_JITTER,
    RECONNECT_MAX_DELAY,
    STATUS_AUTH_ERROR,
    STATUS_DEFAULT_PASSWORD,
    STATUS_LOCKED_OUT,
    STATUS_NOT_LOGGED_IN,
    STATUS_SUCCESS,
)
from .errors import (
    AuthenticationFailed,
    CommandTimeout,
    ConnectionFailed,
    EpisodeAmpError,
    exception_for_status,
)
from .models import AmplifierState

_LOGGER = logging.getLogger(__name__)

# Buffer size for reading from the TCP socket
READ_BUFFER_SIZE = 8192


# ---------------------------------------------------------------------------
# Response-parsing helpers
#
# The Episode firmware sends BULK responses: querying any indexed property
# (e.g. get_outputvol with index=0) returns ALL values as a list:
#   {"value": [{"index": 0, "value": -20}, {"index": 1, "value": -40}, …]}
# These helpers normalise both shapes so callers always receive a scalar.
# ---------------------------------------------------------------------------

def _extract_indexed(resp: dict[str, Any], index: int, default: Any) -> Any:
    """Return the value for a specific index from a bulk or scalar response."""
    value = resp.get("value", default)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("index") == index:
                return item.get("value", default)
        return default
    return value


def _extract_all_indexed(resp: dict[str, Any]) -> dict[int, Any]:
    """Return {index: value} for every entry in a bulk response.

    Returns an empty dict for scalar / non-list responses.
    """
    value = resp.get("value")
    if isinstance(value, list):
        return {
            item["index"]: item["value"]
            for item in value
            if isinstance(item, dict) and "index" in item and "value" in item
        }
    return {}


def _extract_scalar(resp: dict[str, Any], default: Any) -> Any:
    """Return a scalar value from a response that may be bulk-indexed.

    Some firmware versions return bulk lists even for non-indexed getters
    (e.g. standby/mode). In those cases, we prefer index 0 when present.
    """
    value = resp.get("value", default)
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("index") == 0:
                return item.get("value", default)
        # Fallback: first entry's value if shaped like [{"index":..,"value":..}]
        if value and isinstance(value[0], dict):
            return value[0].get("value", default)
        return default
    return value


class EpisodeResponseClient:
    """Persistent async TCP client for Episode Response amplifiers."""

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        state: AmplifierState | None = None,
        on_connected: Callable[[], None] | None = None,
        on_disconnected: Callable[[], None] | None = None,
        on_state_update: Callable[[AmplifierState], None] | None = None,
    ) -> None:
        """Initialize the client."""
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self.state = state or AmplifierState()

        # Callbacks
        self._on_connected = on_connected
        self._on_disconnected = on_disconnected
        self._on_state_update = on_state_update

        # Connection state
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False
        self._authenticated = False
        self._closing = False

        # Reconnect
        self._reconnect_task: asyncio.Task[None] | None = None
        self._reconnect_delay = RECONNECT_BASE_DELAY

        # Heartbeat
        self._heartbeat_task: asyncio.Task[None] | None = None

        # Command serialization
        self._cmd_lock = asyncio.Lock()

        # Buffer for partial reads
        self._read_buffer = b""
        self._line_terminator = NULL_TERMINATOR

        # Connection health tracking
        self._connected_since: float | None = None
        self._last_successful_command: float | None = None
        self._consecutive_failures: int = 0
        self._total_reconnects: int = 0

        # Identity fetch state — attempt at most once; some firmware revisions
        # do not implement identity commands and will never reply to them.
        self._identity_attempted: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def host(self) -> str:
        """Return the amplifier host."""
        return self._host

    @property
    def port(self) -> int:
        """Return the amplifier port."""
        return self._port

    @property
    def connected(self) -> bool:
        """Return True if the TCP connection is established and authenticated."""
        return self._connected and self._authenticated

    @property
    def connection_uptime(self) -> float | None:
        """Return seconds since the connection was established, or None."""
        if self._connected_since is None:
            return None
        return time.monotonic() - self._connected_since

    @property
    def last_successful_command(self) -> float | None:
        """Return the timestamp of the last successful command."""
        return self._last_successful_command

    @property
    def consecutive_failures(self) -> int:
        """Return the number of consecutive command failures."""
        return self._consecutive_failures

    @property
    def total_reconnects(self) -> int:
        """Return the total number of reconnect cycles."""
        return self._total_reconnects

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open TCP connection and authenticate."""
        self._closing = False
        try:
            _LOGGER.debug(
                "Connecting to Episode Response amp at %s:%s", self._host, self._port
            )
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port),
                timeout=CONNECTION_TIMEOUT,
            )
            self._connected = True
            self._read_buffer = b""
            self._reconnect_delay = RECONNECT_BASE_DELAY

            # Authenticate immediately
            await self._authenticate()
            self._authenticated = True
            self.state.connected = True
            self._connected_since = time.monotonic()
            self._consecutive_failures = 0

            _LOGGER.info(
                "Connected to Episode Response amp at %s:%s", self._host, self._port
            )

            if self._on_connected:
                self._on_connected()

        except AuthenticationFailed:
            self.state.connected = False
            await self._close_transport()
            raise
        except (OSError, asyncio.TimeoutError, ConnectionError) as err:
            self.state.connected = False
            await self._close_transport()
            raise ConnectionFailed(
                f"Cannot connect to {self._host}:{self._port}: {err}"
            ) from err

    async def disconnect(self) -> None:
        """Gracefully close the connection."""
        self._closing = True
        self._cancel_heartbeat()
        self._cancel_reconnect()

        if self._connected and self._authenticated:
            try:
                await self._send_raw({
                    "type": CMD_LOGOUT,
                })
            except Exception:  # noqa: BLE001
                pass

        await self._close_transport()
        self.state.connected = False
        self._connected_since = None
        _LOGGER.info("Disconnected from Episode Response amp at %s", self._host)

    async def reconnect(self) -> None:
        """Force a reconnect cycle."""
        await self._close_transport()
        self.state.connected = False
        self._connected = False
        self._authenticated = False
        if self._on_disconnected:
            self._on_disconnected()
        await self.connect()

    async def _close_transport(self) -> None:
        """Close the underlying TCP transport."""
        self._connected = False
        self._authenticated = False
        writer = self._writer
        self._writer = None
        self._reader = None
        if writer is not None:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def _authenticate(self) -> None:
        """Send login command and validate the response."""
        payload = {
            "type": CMD_LOGIN,
            "username": self._username,
            "password": self._password,
        }

        # Primary framing is NULL-terminated JSON per vendor docs.
        # Some firmware/control stacks may behave line-delimited; retry once.
        terminators = [self._line_terminator]
        if b"\n" not in terminators:
            terminators.append(b"\n")

        response: dict[str, Any] | None = None
        last_timeout: CommandTimeout | None = None

        for terminator in terminators:
            try:
                await self._send_raw(payload, terminator=terminator)
                response = await self._read_auth_response()
                if terminator != self._line_terminator:
                    _LOGGER.info(
                        "Switching message terminator to newline for %s:%s",
                        self._host,
                        self._port,
                    )
                    self._line_terminator = terminator
                break
            except CommandTimeout as err:
                last_timeout = err

        if response is None:
            if last_timeout is not None:
                raise last_timeout
            raise ConnectionFailed("No login response from amplifier")

        status = response.get("status", 0)
        if status == STATUS_AUTH_ERROR:
            raise AuthenticationFailed("Invalid username or password")
        if status == STATUS_DEFAULT_PASSWORD:
            raise AuthenticationFailed(
                "The default password is still in use. Please change it via the web UI first."
            )
        if status == STATUS_LOCKED_OUT:
            raise AuthenticationFailed(
                "Account is locked out due to too many failed attempts"
            )
        if status != STATUS_SUCCESS:
            exc = exception_for_status(status)
            if exc:
                raise exc
            raise ConnectionFailed(f"Login returned unexpected status {status}")

        _LOGGER.debug("Authenticated with Episode Response amp")

    async def _read_auth_response(self) -> dict[str, Any]:
        """Read login response, ignoring any non-status preamble messages."""
        for _ in range(3):
            response = await self._read_message()
            if "status" in response:
                return response
            _LOGGER.debug("Ignoring non-status pre-login message: %s", response)

        raise ConnectionFailed("Login response did not include a status field")

    # ------------------------------------------------------------------
    # Low-level TCP I/O
    # ------------------------------------------------------------------

    async def _send_raw(
        self,
        payload: dict[str, Any],
        *,
        terminator: bytes | None = None,
    ) -> None:
        """Serialize and send a JSON payload with NULL terminator."""
        if self._writer is None:
            raise ConnectionFailed("Not connected")
        payload_terminator = self._line_terminator if terminator is None else terminator
        data = (
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
            + payload_terminator
        )
        _LOGGER.debug("TX → %s: %s", self._host, payload)
        self._writer.write(data)
        await self._writer.drain()

    async def _read_message(self) -> dict[str, Any]:
        """Read a framed or unframed JSON message from the socket.

        Supports three framing styles used by Episode firmware:
          1. NULL-terminated  (\\x00 after JSON)  — vendor spec
          2. Newline-terminated (\\n after JSON)  — some builds
          3. Unframed — a complete JSON object sent as a single TCP segment
             with no trailing byte at all.  This is what current firmware does.

        The critical optimisation for style 3: after every successful read()
        we immediately attempt a JSON parse of the entire buffer.  Without
        this the loop would go back and call read() again, wait the full
        COMMAND_TIMEOUT for more bytes that never arrive, then finally parse
        on the TimeoutError path — costing ~8–23 s per command.
        """
        if self._reader is None:
            raise ConnectionFailed("Not connected")

        while True:
            # ------ 1. Check for a properly framed message in the buffer ------
            null_idx = self._read_buffer.find(NULL_TERMINATOR)
            newline_idx = self._read_buffer.find(b"\n")
            msg_end = -1

            if null_idx >= 0 and (newline_idx < 0 or null_idx < newline_idx):
                msg_end = null_idx
            elif newline_idx >= 0:
                msg_end = newline_idx

            if msg_end >= 0:
                msg_bytes = self._read_buffer[:msg_end]
                self._read_buffer = self._read_buffer[msg_end + 1:]
                msg_str = msg_bytes.decode("utf-8").strip()
                if msg_str:
                    if msg_str.startswith("HTTP/"):
                        raise ConnectionFailed(
                            "Configured port appears to be an HTTP service, not the Episode API"
                        )
                    try:
                        parsed = json.loads(msg_str)
                        _LOGGER.debug("RX ← %s: %s", self._host, parsed)
                        return parsed
                    except json.JSONDecodeError as err:
                        _LOGGER.warning(
                            "Invalid JSON from %s: %s (raw: %s)",
                            self._host,
                            err,
                            msg_str[:200],
                        )
                continue  # empty or unparseable, keep reading

            # ------ 2. Try to parse the buffer as unframed JSON ------
            # Do this BEFORE waiting for more data.  If the device sent a
            # complete, well-formed JSON object in one TCP segment (no
            # terminator), we get the answer here in <1 ms instead of
            # burning the full COMMAND_TIMEOUT waiting for bytes that will
            # never come.
            if self._read_buffer:
                candidate = self._read_buffer.decode("utf-8", errors="ignore").strip()
                if candidate:
                    if candidate.startswith("HTTP/"):
                        raise ConnectionFailed(
                            "Configured port appears to be an HTTP service, not the Episode API"
                        )
                    try:
                        parsed = json.loads(candidate)
                        self._read_buffer = b""
                        _LOGGER.debug("RX ← %s (no-terminator): %s", self._host, parsed)
                        return parsed
                    except json.JSONDecodeError:
                        pass  # incomplete payload — wait for more data

            # ------ 3. Need more data — read with timeout ------
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(READ_BUFFER_SIZE),
                    timeout=COMMAND_TIMEOUT + 2,
                )
            except asyncio.TimeoutError as err:
                # Last-resort: try whatever is buffered.
                buffered = self._read_buffer.decode("utf-8", errors="ignore").strip()
                if buffered:
                    if buffered.startswith("HTTP/"):
                        raise ConnectionFailed(
                            "Configured port appears to be an HTTP service, not the Episode API"
                        )
                    try:
                        parsed = json.loads(buffered)
                        self._read_buffer = b""
                        _LOGGER.debug("RX ← %s (timeout-flush): %s", self._host, parsed)
                        return parsed
                    except json.JSONDecodeError:
                        pass
                raise CommandTimeout("Timed out reading from amplifier") from err

            if not chunk:
                raise ConnectionFailed("Connection closed by amplifier")
            self._read_buffer += chunk
            # Loop back — step 2 will immediately try to parse the new data.

    async def _send_and_receive(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """Send a command and wait for the response (no lock — internal use)."""
        await self._send_raw(payload)
        return await self._read_message()

    # ------------------------------------------------------------------
    # Public command API (locked for concurrency safety)
    # ------------------------------------------------------------------

    async def send_command(
        self, payload: dict[str, Any], *, retry_auth: bool = True
    ) -> dict[str, Any]:
        """Send a command, handle auth-retry, and return the parsed response.

        This is the main public entry point for all commands. It uses an
        asyncio.Lock so only one command is in-flight at a time.
        """
        async with self._cmd_lock:
            # Outer wrapper: COMMAND_TIMEOUT + 4 s so it always fires after
            # the inner per-read timeout (COMMAND_TIMEOUT + 2) if needed.
            command_timeout = COMMAND_TIMEOUT + 4
            try:
                response = await asyncio.wait_for(
                    self._send_and_receive(payload),
                    timeout=command_timeout,
                )
            except asyncio.TimeoutError as err:
                timeout_err = CommandTimeout(
                    f"Command timed out after {command_timeout} seconds"
                )
                self._consecutive_failures += 1
                _LOGGER.debug(
                    "Command timed out (attempt %d): %s",
                    self._consecutive_failures,
                    timeout_err,
                )
                # Mark the connection dead so the coordinator will reconnect
                # on the next poll cycle instead of waiting for a background
                # reconnect loop with exponential back-off.
                self._connected = False
                self._authenticated = False
                await self._close_transport()
                raise timeout_err from err
            except (OSError, ConnectionError, CommandTimeout, ConnectionFailed) as err:
                self._consecutive_failures += 1
                _LOGGER.debug(
                    "Command failed (attempt %d): %s",
                    self._consecutive_failures,
                    err,
                )
                self._connected = False
                self._authenticated = False
                await self._close_transport()
                raise

            status = response.get("status", 200)

            # If the amp says "log in first", re-authenticate and retry once
            if status == STATUS_NOT_LOGGED_IN and retry_auth:
                _LOGGER.info("Session expired, re-authenticating…")
                try:
                    await self._authenticate()
                    self._authenticated = True
                except AuthenticationFailed:
                    raise
                except Exception as err:
                    _LOGGER.error("Re-authentication failed: %s", err)
                    self._schedule_reconnect()
                    raise ConnectionFailed("Re-authentication failed") from err

                # Retry the original command once
                try:
                    response = await asyncio.wait_for(
                        self._send_and_receive(payload),
                        timeout=command_timeout,
                    )
                except asyncio.TimeoutError as err:
                    self._connected = False
                    self._authenticated = False
                    await self._close_transport()
                    raise ConnectionFailed(
                        f"Retry after re-auth timed out after {command_timeout} seconds"
                    ) from err
                except Exception as err:
                    self._connected = False
                    self._authenticated = False
                    await self._close_transport()
                    raise ConnectionFailed("Retry after re-auth failed") from err

            # Update the state's last status code
            self.state.last_status_code = response.get("status", 200)
            self._last_successful_command = time.monotonic()
            self._consecutive_failures = 0
            return response

    # ------------------------------------------------------------------
    # High-level getters / setters
    # ------------------------------------------------------------------

    async def get_amp_info(self) -> dict[str, Any]:
        """Fetch amplifier identification info (best-effort).

        Some firmware revisions do not implement every identity command; if the
        device stops responding mid-fetch the transport will be closed and the
        loop simply stops.  Callers must not rely on this completing.
        """
        results: dict[str, Any] = {}
        for cmd_type in (CMD_GET_AMP_NAME, CMD_GET_FIRMWARE, CMD_GET_MAC, CMD_GET_SERIAL):
            if not self.connected:
                break  # transport died on a previous command — stop trying
            try:
                resp = await self.send_command({"type": cmd_type})
                results[cmd_type] = resp
            except EpisodeAmpError as err:
                _LOGGER.debug("Could not fetch %s: %s", cmd_type, err)
        return results

    async def get_temperature(self) -> float | None:
        """Get the amplifier temperature (best-effort).

        Returns None on any error.  Connection errors are re-raised so the
        coordinator can mark the poll as failed and reconnect on the next cycle.
        """
        try:
            resp = await self.send_command({"type": CMD_GET_TEMPERATURE})
            raw = _extract_scalar(resp, None)
            if raw is None:
                return None
            try:
                return float(raw)
            except (TypeError, ValueError):
                return None
        except (ConnectionFailed, CommandTimeout) as err:
            # Re-raise so the poll fails and the coordinator reconnects.
            raise ConnectionFailed(str(err)) from err
        except EpisodeAmpError:
            return None

    async def set_zone_volume(self, zone: int, volume_db: int) -> dict[str, Any]:
        """Set zone volume in dB (-80..0)."""
        volume_db = max(-80, min(0, volume_db))
        return await self.send_command({
            "type": "set_outputvol",
            "index": zone,
            "value": volume_db,
        })

    async def get_zone_volume(self, zone: int) -> int:
        """Get zone volume in dB."""
        resp = await self.send_command({
            "type": "get_outputvol",
            "index": zone,
        })
        return int(_extract_indexed(resp, zone, -80))

    async def set_zone_mute(self, zone: int, muted: bool) -> dict[str, Any]:
        """Set zone mute state."""
        return await self.send_command({
            "type": "set_muteoutput",
            "index": zone,
            "value": 1 if muted else 0,
        })

    async def get_zone_mute(self, zone: int) -> bool:
        """Get zone mute state."""
        resp = await self.send_command({
            "type": "get_muteoutput",
            "index": zone,
        })
        return bool(_extract_indexed(resp, zone, 0))

    async def set_zone_source(self, zone: int, source: int, *, channel: int = 1) -> dict[str, Any]:
        """Set zone source input (channel 1 or 2)."""
        cmd = f"set_outputsource{channel}"
        return await self.send_command({
            "type": cmd,
            "index": zone,
            "value": source,
        })

    async def get_zone_source(self, zone: int, *, channel: int = 1) -> int:
        """Get zone source input."""
        cmd = f"get_outputsource{channel}"
        resp = await self.send_command({
            "type": cmd,
            "index": zone,
        })
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_enable(self, zone: int, enabled: bool) -> dict[str, Any]:
        """Enable or disable a zone."""
        return await self.send_command({
            "type": "set_outputenable",
            "index": zone,
            "value": 1 if enabled else 0,
        })

    async def get_zone_enable(self, zone: int) -> bool:
        """Get zone enable state."""
        resp = await self.send_command({
            "type": "get_outputenable",
            "index": zone,
        })
        return bool(_extract_indexed(resp, zone, 1))

    async def set_zone_dsp_preset(self, zone: int, preset: int) -> dict[str, Any]:
        """Set zone DSP preset."""
        return await self.send_command({
            "type": "set_dsppreset",
            "index": zone,
            "value": preset,
        })

    async def get_zone_dsp_preset(self, zone: int) -> int:
        """Get zone DSP preset."""
        resp = await self.send_command({
            "type": "get_dsppreset",
            "index": zone,
        })
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_bass(self, zone: int, value: int) -> dict[str, Any]:
        """Set zone bass (-12..12 dB)."""
        return await self.send_command({
            "type": "set_bass",
            "index": zone,
            "value": max(-12, min(12, value)),
        })

    async def get_zone_bass(self, zone: int) -> int:
        """Get zone bass value."""
        resp = await self.send_command({"type": "get_bass", "index": zone})
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_treble(self, zone: int, value: int) -> dict[str, Any]:
        """Set zone treble (-12..12 dB)."""
        return await self.send_command({
            "type": "set_treble",
            "index": zone,
            "value": max(-12, min(12, value)),
        })

    async def get_zone_treble(self, zone: int) -> int:
        """Get zone treble value."""
        resp = await self.send_command({"type": "get_treble", "index": zone})
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_balance(self, zone: int, value: int) -> dict[str, Any]:
        """Set zone balance (-20..20)."""
        return await self.send_command({
            "type": "set_balance",
            "index": zone,
            "value": max(-20, min(20, value)),
        })

    async def get_zone_balance(self, zone: int) -> int:
        """Get zone balance."""
        resp = await self.send_command({"type": "get_balance", "index": zone})
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_loudness(self, zone: int, enabled: bool) -> dict[str, Any]:
        """Set zone loudness compensation."""
        return await self.send_command({
            "type": "set_loudness",
            "index": zone,
            "value": 1 if enabled else 0,
        })

    async def get_zone_loudness(self, zone: int) -> bool:
        """Get zone loudness state."""
        resp = await self.send_command({"type": "get_loudness", "index": zone})
        return bool(_extract_indexed(resp, zone, 0))

    async def set_zone_delay(self, zone: int, value: int) -> dict[str, Any]:
        """Set zone delay (ms)."""
        return await self.send_command({
            "type": "set_delay",
            "index": zone,
            "value": max(0, value),
        })

    async def get_zone_delay(self, zone: int) -> int:
        """Get zone delay (ms)."""
        resp = await self.send_command({"type": "get_delay", "index": zone})
        return int(_extract_indexed(resp, zone, 0))

    async def set_zone_limiter(self, zone: int, enabled: bool) -> dict[str, Any]:
        """Set zone limiter."""
        return await self.send_command({
            "type": "set_limiter",
            "index": zone,
            "value": 1 if enabled else 0,
        })

    async def get_zone_limiter(self, zone: int) -> bool:
        """Get zone limiter state."""
        resp = await self.send_command({"type": "get_limiter", "index": zone})
        return bool(_extract_indexed(resp, zone, 0))

    async def set_zone_bridge(self, zone: int, enabled: bool) -> dict[str, Any]:
        """Set zone bridge mode."""
        return await self.send_command({
            "type": "set_bridge",
            "index": zone,
            "value": 1 if enabled else 0,
        })

    async def get_zone_bridge(self, zone: int) -> bool:
        """Get zone bridge mode."""
        resp = await self.send_command({"type": "get_bridge", "index": zone})
        return bool(_extract_indexed(resp, zone, 0))

    async def set_standby(self, standby: bool) -> dict[str, Any]:
        """Set amplifier standby mode."""
        return await self.send_command({
            "type": "set_standby",
            "value": 1 if standby else 0,
        })

    async def get_standby(self) -> bool:
        """Get amplifier standby state."""
        resp = await self.send_command({"type": "get_standby"})
        return bool(_extract_scalar(resp, 0))

    async def set_mode(self, mode: int) -> dict[str, Any]:
        """Set amplifier operating mode (0=On,1=Standby,2=VTrig,3=Audio)."""
        return await self.send_command({
            "type": "set_mode",
            "value": mode,
        })

    async def get_mode(self) -> int:
        """Get amplifier operating mode."""
        resp = await self.send_command({"type": "get_mode"})
        return int(_extract_scalar(resp, 0))

    async def set_amp_name(self, name: str) -> dict[str, Any]:
        """Set amplifier name."""
        return await self.send_command({
            "type": "set_ampname",
            "value": name,
        })

    async def get_amp_name(self) -> str:
        """Get amplifier name."""
        resp = await self.send_command({"type": "get_ampname"})
        return resp.get("value", "")

    async def set_output_name(self, zone: int, name: str) -> dict[str, Any]:
        """Set zone/output name."""
        return await self.send_command({
            "type": "set_outputname",
            "index": zone,
            "value": name,
        })

    async def get_output_name(self, zone: int) -> str:
        """Get zone/output name."""
        resp = await self.send_command({"type": "get_outputname", "index": zone})
        return str(_extract_indexed(resp, zone, f"Zone {zone + 1}"))

    async def set_input_name(self, index: int, name: str) -> dict[str, Any]:
        """Set input name."""
        return await self.send_command({
            "type": "set_inputname",
            "index": index,
            "value": name,
        })

    async def get_input_name(self, index: int) -> str:
        """Get input name."""
        resp = await self.send_command({"type": "get_inputname", "index": index})
        return str(_extract_indexed(resp, index, f"Input {index + 1}"))

    async def set_input_gain(self, index: int, gain: int) -> dict[str, Any]:
        """Set input gain."""
        return await self.send_command({
            "type": "set_inputgain",
            "index": index,
            "value": gain,
        })

    async def get_input_gain(self, index: int) -> int:
        """Get input gain."""
        resp = await self.send_command({"type": "get_inputgain", "index": index})
        return int(_extract_indexed(resp, index, 0))

    async def reboot(self) -> dict[str, Any]:
        """Reboot the amplifier."""
        return await self.send_command({"type": "reboot"})

    async def factory_reset(self) -> dict[str, Any]:
        """Factory-reset the amplifier."""
        return await self.send_command({"type": "factory_reset"})

    # ------------------------------------------------------------------
    # Full state poll
    # ------------------------------------------------------------------

    async def poll_full_state(self) -> AmplifierState:
        """Poll all zone and amplifier state. Used by the coordinator.

        The Episode firmware returns bulk (all-zone) responses regardless of the
        index in the request, so each property is queried with a single command
        and all 6 zone values are parsed from the one response.  This reduces
        round-trips from ~100 to ~16 per poll cycle.
        """
        if not self.connected:
            raise ConnectionFailed("Not connected to amplifier")

        # Global state — always poll
        try:
            self.state.standby = await self.get_standby()
            self.state.mode = await self.get_mode()
        except (ConnectionFailed, CommandTimeout):
            raise
        except EpisodeAmpError as err:
            _LOGGER.debug("Could not poll standby/mode: %s", err)

        self.state.temperature = await self.get_temperature()

        if self.state.standby:
            _LOGGER.debug("Amplifier in standby — skipping zone poll")
            if self._on_state_update:
                self._on_state_update(self.state)
            return self.state

        # ------------------------------------------------------------------
        # Bulk zone property poll.
        # One request per property → device replies with all 6 zone values.
        # Tuple: (API command, ZoneState attribute, default, type coercion)
        # ------------------------------------------------------------------
        _ZONE_PROPS: list[tuple[str, str, Any, type]] = [
            ("get_outputvol",     "volume_db",  -80,   int),
            ("get_muteoutput",    "muted",      False, bool),
            ("get_outputsource1", "source1",    0,     int),
            ("get_outputsource2", "source2",    0,     int),
            ("get_outputenable",  "enabled",    True,  bool),
            ("get_dsppreset",     "dsp_preset", 0,     int),
            ("get_bass",          "bass",       0,     int),
            ("get_treble",        "treble",     0,     int),
            ("get_balance",       "balance",    0,     int),
            ("get_loudness",      "loudness",   False, bool),
            ("get_delay",         "delay",      0,     int),
            ("get_limiter",       "limiter",    False, bool),
            ("get_bridge",        "bridge",     False, bool),
        ]

        for cmd_type, attr, default, coerce in _ZONE_PROPS:
            try:
                resp = await self.send_command({"type": cmd_type})
                values = _extract_all_indexed(resp)
                for zone_idx in range(6):
                    raw = values.get(zone_idx, default)
                    try:
                        setattr(self.state.zones[zone_idx], attr, coerce(raw))
                    except (TypeError, ValueError):
                        setattr(self.state.zones[zone_idx], attr, default)
            except (ConnectionFailed, CommandTimeout):
                raise
            except EpisodeAmpError as err:
                _LOGGER.debug("Bulk poll %s failed: %s", cmd_type, err)

        # Zone names — one request, all 6 names
        try:
            resp = await self.send_command({"type": "get_outputname"})
            names = _extract_all_indexed(resp)
            for zone_idx in range(6):
                raw = names.get(zone_idx)
                if isinstance(raw, str) and raw:
                    self.state.zones[zone_idx].name = raw
        except (ConnectionFailed, CommandTimeout):
            raise
        except EpisodeAmpError:
            pass

        # Input names — one request, all 6 names
        try:
            resp = await self.send_command({"type": "get_inputname"})
            names = _extract_all_indexed(resp)
            for inp_idx in range(6):
                raw = names.get(inp_idx)
                if isinstance(raw, str) and raw:
                    self.state.inputs[inp_idx].name = raw
        except (ConnectionFailed, CommandTimeout):
            raise
        except EpisodeAmpError:
            pass

        # Input gains — one request, all 6 gains
        try:
            resp = await self.send_command({"type": "get_inputgain"})
            gains = _extract_all_indexed(resp)
            for inp_idx in range(6):
                raw = gains.get(inp_idx, 0)
                try:
                    self.state.inputs[inp_idx].gain = int(raw)
                except (TypeError, ValueError):
                    pass
        except (ConnectionFailed, CommandTimeout):
            raise
        except EpisodeAmpError:
            pass

        if self._on_state_update:
            self._on_state_update(self.state)

        return self.state

    async def _fetch_amp_identity(self) -> None:
        """Fetch static amplifier identity (firmware, MAC, serial, name)."""
        info = await self.get_amp_info()

        if CMD_GET_AMP_NAME in info:
            self.state.name = info[CMD_GET_AMP_NAME].get("value", "")
        if CMD_GET_FIRMWARE in info:
            self.state.firmware = info[CMD_GET_FIRMWARE].get("value", "")
        if CMD_GET_MAC in info:
            self.state.mac_address = info[CMD_GET_MAC].get("value", "")
        if CMD_GET_SERIAL in info:
            self.state.serial_number = info[CMD_GET_SERIAL].get("value", "")

    # ------------------------------------------------------------------
    # Heartbeat / keep-alive
    # ------------------------------------------------------------------

    def _start_heartbeat(self) -> None:
        """No-op: persistent heartbeat is disabled.

        The coordinator reconnects inline before each poll, which makes a
        background keep-alive unnecessary and avoids the exponential-backoff
        death spiral that occurs when the device drops an idle connection.
        """

    def _cancel_heartbeat(self) -> None:
        """Cancel any lingering heartbeat task (kept for backwards compatibility)."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        self._heartbeat_task = None

    async def _heartbeat_loop(self) -> None:
        """No-op: heartbeat disabled — coordinator handles reconnection."""
        return

    # ------------------------------------------------------------------
    # Reconnect logic with exponential backoff
    # ------------------------------------------------------------------

    def _schedule_reconnect(self) -> None:
        """Schedule an automatic reconnect attempt."""
        if self._closing:
            return
        if self._reconnect_task and not self._reconnect_task.done():
            return  # already scheduled
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    def _cancel_reconnect(self) -> None:
        """Cancel any pending reconnect task."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        self._reconnect_task = None

    async def _reconnect_loop(self) -> None:
        """Reconnect with exponential backoff and jitter."""
        self._cancel_heartbeat()
        await self._close_transport()
        self.state.connected = False
        self._connected_since = None
        if self._on_disconnected:
            self._on_disconnected()

        while not self._closing:
            # Add jitter to prevent thundering herd on multi-amp setups
            jitter = random.uniform(-RECONNECT_JITTER, RECONNECT_JITTER)  # noqa: S311
            delay = max(0.5, self._reconnect_delay + jitter)
            _LOGGER.info(
                "Reconnecting to %s:%s in %.1f seconds…",
                self._host,
                self._port,
                delay,
            )
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            self._total_reconnects += 1
            try:
                await self.connect()
                _LOGGER.info(
                    "Reconnected to %s:%s (attempt %d)",
                    self._host,
                    self._port,
                    self._total_reconnects,
                )
                return
            except AuthenticationFailed:
                _LOGGER.error("Authentication failed during reconnect — stopping")
                return
            except (ConnectionFailed, OSError, asyncio.TimeoutError) as err:
                _LOGGER.warning("Reconnect attempt %d failed: %s", self._total_reconnects, err)
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, RECONNECT_MAX_DELAY
                )

    # ------------------------------------------------------------------
    # Test connection (used by config flow)
    # ------------------------------------------------------------------

    @staticmethod
    async def probe_port(host: str, port: int, *, timeout: float = 1.0) -> bool:
        """Return True when a TCP port accepts a connection within timeout."""
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout,
            )
            return True
        except Exception:  # noqa: BLE001
            return False
        finally:
            if writer is not None:
                with suppress(Exception):
                    writer.close()
                    await writer.wait_closed()

    @staticmethod
    async def test_connection(
        host: str,
        port: int,
        username: str,
        password: str,
        *,
        attempts: int = 2,
    ) -> dict[str, Any]:
        """Quick connect → login → get info → disconnect. Returns amp info dict.

        Used by the config flow to validate credentials before saving.
        """
        last_error = "Unknown connection error"
        total_attempts = max(1, attempts)

        for attempt in range(1, total_attempts + 1):
            client = EpisodeResponseClient(host, port, username, password)
            try:
                await client.connect()
                # Stop heartbeat since this is just a short-lived probe.
                client._cancel_heartbeat()  # noqa: SLF001

                # Login success is enough to validate config data.
                # Name read is best-effort and should not fail setup.
                try:
                    name = await client.get_amp_name()
                except EpisodeAmpError:
                    name = ""
                return {"success": True, "name": name}
            except AuthenticationFailed as err:
                # Do not retry bad credentials.
                last_error = str(err)
                break
            except CommandTimeout:
                last_error = (
                    "Timed out reading from amplifier. The port may be busy, mapped to a "
                    "different service, or the amplifier may be saturated with active sessions."
                )
            except EpisodeAmpError as err:
                last_error = str(err).strip() or err.__class__.__name__
            except Exception as err:  # noqa: BLE001
                last_error = str(err).strip() or err.__class__.__name__
            finally:
                with suppress(Exception):
                    await client.disconnect()

            if attempt < total_attempts:
                await asyncio.sleep(min(1.0, 0.25 * attempt))

        return {"success": False, "error": last_error}
