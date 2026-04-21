"""Constants for the Episode Response DSP Amplifier integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

# Integration identifiers
DOMAIN: Final = "episode_response_amp"
MANUFACTURER: Final = "Episode (SnapAV)"
DEFAULT_MODEL: Final = "EA-RSP-12D-100"
INTEGRATION_TITLE: Final = "Episode Response DSP Amplifier"
INTEGRATION_VERSION: Final = "1.0.0"

# Connection defaults
DEFAULT_PORT: Final = 8080
DEFAULT_POLL_INTERVAL: Final = 5  # seconds
MIN_POLL_INTERVAL: Final = 2
MAX_POLL_INTERVAL: Final = 60
RECONNECT_BASE_DELAY: Final = 2  # seconds
RECONNECT_MAX_DELAY: Final = 300  # 5 minutes
RECONNECT_JITTER: Final = 1.0  # ±1 second randomization to prevent thundering herd
HEARTBEAT_INTERVAL: Final = 30  # seconds
CONNECTION_TIMEOUT: Final = 15  # seconds
COMMAND_TIMEOUT: Final = 20  # seconds — device can take up to ~10 s per response
MAX_RECONNECT_ATTEMPTS: Final = 0  # 0 = unlimited
NULL_TERMINATOR: Final = b"\x00"

# Configuration keys
CONF_HOST: Final = "host"
CONF_PORT: Final = "port"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_POLL_INTERVAL: Final = "poll_interval"

# Zone / channel constants
NUM_ZONES: Final = 6
NUM_CHANNELS: Final = 12
NUM_SOURCES: Final = 6
ZONE_INDICES: Final = list(range(NUM_ZONES))  # 0-5

# Volume range (dB)
VOLUME_MIN_DB: Final = -80
VOLUME_MAX_DB: Final = 0
VOLUME_STEP_DB: Final = 1

# DSP ranges
BASS_MIN: Final = -12
BASS_MAX: Final = 12
TREBLE_MIN: Final = -12
TREBLE_MAX: Final = 12
BALANCE_MIN: Final = -20
BALANCE_MAX: Final = 20
DELAY_MIN: Final = 0
DELAY_MAX: Final = 1000
GAIN_MIN: Final = -12
GAIN_MAX: Final = 12

# API command types — Authentication
CMD_LOGIN: Final = "login"
CMD_LOGOUT: Final = "logout"
CMD_SET_PASSWORD: Final = "set_password"

# API command types — Amplifier control
CMD_GET_AMP_NAME: Final = "get_ampname"
CMD_SET_AMP_NAME: Final = "set_ampname"
CMD_GET_MODE: Final = "get_mode"
CMD_SET_MODE: Final = "set_mode"
CMD_GET_STANDBY: Final = "get_standby"
CMD_SET_STANDBY: Final = "set_standby"
CMD_GET_FIRMWARE: Final = "get_firmware"
CMD_GET_MAC: Final = "get_mac"
CMD_GET_SERIAL: Final = "get_serial"
CMD_GET_TEMPERATURE: Final = "get_temperature"
CMD_GET_NETWORK: Final = "get_network"
CMD_SET_NETWORK: Final = "set_network"
CMD_IMPORT_CONFIG: Final = "import_config"
CMD_EXPORT_CONFIG: Final = "export_config"
CMD_FACTORY_RESET: Final = "factory_reset"
CMD_REBOOT: Final = "reboot"

# API command types — Output / Zone control
CMD_GET_OUTPUT_VOL: Final = "get_outputvol"
CMD_SET_OUTPUT_VOL: Final = "set_outputvol"
CMD_GET_MUTE_OUTPUT: Final = "get_muteoutput"
CMD_SET_MUTE_OUTPUT: Final = "set_muteoutput"
CMD_GET_OUTPUT_SOURCE1: Final = "get_outputsource1"
CMD_SET_OUTPUT_SOURCE1: Final = "set_outputsource1"
CMD_GET_OUTPUT_SOURCE2: Final = "get_outputsource2"
CMD_SET_OUTPUT_SOURCE2: Final = "set_outputsource2"
CMD_GET_OUTPUT_NAME: Final = "get_outputname"
CMD_SET_OUTPUT_NAME: Final = "set_outputname"
CMD_GET_OUTPUT_ENABLE: Final = "get_outputenable"
CMD_SET_OUTPUT_ENABLE: Final = "set_outputenable"

# API command types — Input control
CMD_GET_INPUT_NAME: Final = "get_inputname"
CMD_SET_INPUT_NAME: Final = "set_inputname"
CMD_GET_INPUT_GAIN: Final = "get_inputgain"
CMD_SET_INPUT_GAIN: Final = "set_inputgain"

# API command types — DSP control
CMD_GET_DSP_PRESET: Final = "get_dsppreset"
CMD_SET_DSP_PRESET: Final = "set_dsppreset"
CMD_GET_BASS: Final = "get_bass"
CMD_SET_BASS: Final = "set_bass"
CMD_GET_TREBLE: Final = "get_treble"
CMD_SET_TREBLE: Final = "set_treble"
CMD_GET_BALANCE: Final = "get_balance"
CMD_SET_BALANCE: Final = "set_balance"
CMD_GET_LOUDNESS: Final = "get_loudness"
CMD_SET_LOUDNESS: Final = "set_loudness"
CMD_GET_DELAY: Final = "get_delay"
CMD_SET_DELAY: Final = "set_delay"
CMD_GET_LIMITER: Final = "get_limiter"
CMD_SET_LIMITER: Final = "set_limiter"

# API command types — Bridge / Mono
CMD_GET_BRIDGE: Final = "get_bridge"
CMD_SET_BRIDGE: Final = "set_bridge"

# API status codes
STATUS_SUCCESS: Final = 200
STATUS_REPEAT: Final = 300
STATUS_AUTH_ERROR: Final = 400
STATUS_ILLEGAL_REQUEST: Final = 401
STATUS_NOT_LOGGED_IN: Final = 402
STATUS_DEFAULT_PASSWORD: Final = 403
STATUS_SIGNED_OUT: Final = 405
STATUS_LOCKED_OUT: Final = 406
STATUS_REENTER_PASSWORD: Final = 407
STATUS_PASSWORD_SET: Final = 408
STATUS_SERVER_ERROR: Final = 500
STATUS_IMPORT_MISSING: Final = 600
STATUS_MD5_MISMATCH: Final = 601
STATUS_FILE_TYPE_MISMATCH: Final = 602
STATUS_STANDBY: Final = 700
STATUS_VOLTAGE_TRIGGER: Final = 701
STATUS_AUDIO_MODE: Final = 702
STATUS_UPDATE_SUCCESS: Final = 800
STATUS_UPDATE_FAILED: Final = 801

STATUS_CODE_MAP: Final = {
    200: "Success",
    300: "Repeat operation",
    400: "User or password error",
    401: "Illegal request",
    402: "Please log in first",
    403: "Default password needs to be updated",
    405: "User is signed out",
    406: "Too many incorrect attempts — locked out",
    407: "Re-enter the password",
    408: "Password has been set successfully",
    500: "Unknown server error",
    600: "Import file does not exist",
    601: "MD5 values do not match",
    602: "File type mismatch",
    700: "Amplifier is in standby mode",
    701: "Amplifier is in voltage trigger mode",
    702: "Amplifier is in audio mode",
    800: "Successful update",
    801: "Failed update",
}

# DSP presets
DSP_PRESETS: Final = {
    0: "Flat",
    1: "Voice",
    2: "Music",
    3: "Movie",
    4: "Loudness",
    5: "Custom 1",
    6: "Custom 2",
    7: "Custom 3",
}

DSP_PRESET_NAMES: Final = list(DSP_PRESETS.values())
NUM_DSP_PRESETS: Final = len(DSP_PRESETS)

# Source mapping
SOURCE_MAP: Final = {
    0: "Analog 1",
    1: "Analog 2",
    2: "Analog 3",
    3: "Analog 4",
    4: "Analog 5",
    5: "Analog 6",
}

# Amplifier operating modes
AMP_MODE_ON: Final = 0
AMP_MODE_STANDBY: Final = 1
AMP_MODE_VOLTAGE_TRIGGER: Final = 2
AMP_MODE_AUDIO_SENSE: Final = 3

AMP_MODES: Final = {
    0: "On",
    1: "Standby",
    2: "Voltage Trigger",
    3: "Audio Sense",
}

AMP_MODE_NAMES: Final = list(AMP_MODES.values())

# Events
EVENT_AMP_CONNECTED: Final = f"{DOMAIN}_connected"
EVENT_AMP_DISCONNECTED: Final = f"{DOMAIN}_disconnected"
EVENT_AMP_STATE_CHANGED: Final = f"{DOMAIN}_state_changed"

# Services
SERVICE_SET_DSP_PRESET: Final = "set_dsp_preset"
SERVICE_SET_BASS: Final = "set_bass"
SERVICE_SET_TREBLE: Final = "set_treble"
SERVICE_SET_BALANCE: Final = "set_balance"
SERVICE_SET_INPUT_GAIN: Final = "set_input_gain"
SERVICE_SET_LOUDNESS: Final = "set_loudness"
SERVICE_SET_DELAY: Final = "set_delay"
SERVICE_SET_BRIDGE: Final = "set_bridge"
SERVICE_SET_LIMITER: Final = "set_limiter"
SERVICE_REBOOT: Final = "reboot"
SERVICE_FACTORY_RESET: Final = "factory_reset"
SERVICE_SET_AMP_NAME: Final = "set_amp_name"
SERVICE_SET_OUTPUT_NAME: Final = "set_output_name"
SERVICE_SET_INPUT_NAME: Final = "set_input_name"

ALL_SERVICES: Final = [
    SERVICE_SET_DSP_PRESET,
    SERVICE_SET_BASS,
    SERVICE_SET_TREBLE,
    SERVICE_SET_BALANCE,
    SERVICE_SET_INPUT_GAIN,
    SERVICE_SET_LOUDNESS,
    SERVICE_SET_DELAY,
    SERVICE_SET_BRIDGE,
    SERVICE_SET_LIMITER,
    SERVICE_REBOOT,
    SERVICE_FACTORY_RESET,
    SERVICE_SET_AMP_NAME,
    SERVICE_SET_OUTPUT_NAME,
    SERVICE_SET_INPUT_NAME,
]

# Attributes for services
ATTR_ZONE: Final = "zone"
ATTR_PRESET: Final = "preset"
ATTR_VALUE: Final = "value"
ATTR_INPUT: Final = "input"
ATTR_NAME: Final = "name"
ATTR_ENABLED: Final = "enabled"
ATTR_ENTRY_ID: Final = "entry_id"

# Platforms
PLATFORMS: Final = [
    Platform.MEDIA_PLAYER,
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SWITCH,
    Platform.SELECT,
]
