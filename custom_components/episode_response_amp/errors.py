"""Exceptions for the Episode Response DSP Amplifier integration."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError


class EpisodeAmpError(HomeAssistantError):
    """Base exception for Episode Response Amp."""


class ConnectionFailed(EpisodeAmpError):
    """Raised when unable to connect to the amplifier."""


class AuthenticationFailed(EpisodeAmpError):
    """Raised on invalid credentials (status 400)."""


class NotLoggedIn(EpisodeAmpError):
    """Raised when the amplifier requires login first (status 402)."""


class DefaultPasswordError(EpisodeAmpError):
    """Raised when the default password needs to be changed (status 403)."""


class AccountLockedOut(EpisodeAmpError):
    """Raised when too many bad attempts lock the account (status 406)."""


class AmplifierInStandby(EpisodeAmpError):
    """Raised when the amplifier is in standby mode (status 700)."""


class IllegalRequest(EpisodeAmpError):
    """Raised for illegal/unsupported requests (status 401)."""


class CommandTimeout(EpisodeAmpError):
    """Raised when a command times out waiting for response."""


class ServerError(EpisodeAmpError):
    """Raised for unknown server errors (status 500)."""


class FirmwareUpdateFailed(EpisodeAmpError):
    """Raised when a firmware update fails (status 801)."""


STATUS_EXCEPTION_MAP: dict[int, type[EpisodeAmpError]] = {
    400: AuthenticationFailed,
    401: IllegalRequest,
    402: NotLoggedIn,
    403: DefaultPasswordError,
    406: AccountLockedOut,
    500: ServerError,
    700: AmplifierInStandby,
    801: FirmwareUpdateFailed,
}


def exception_for_status(status_code: int, message: str = "") -> EpisodeAmpError | None:
    """Return the appropriate exception for a status code, or None if success."""
    exc_class = STATUS_EXCEPTION_MAP.get(status_code)
    if exc_class is not None:
        return exc_class(message or f"Amplifier returned status {status_code}")
    return None
