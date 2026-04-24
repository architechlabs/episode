"""The Episode Response DSP Amplifier integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.storage import Store

from .client import EpisodeResponseClient
from .const import (
    ALL_SERVICES,
    ATTR_ENABLED,
    ATTR_ENTRY_ID,
    ATTR_INPUT,
    ATTR_NAME,
    ATTR_PRESET,
    ATTR_VALUE,
    ATTR_ZONE,
    CONF_POLL_INTERVAL,
    DEFAULT_MODEL,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    PLATFORMS,
    SERVICE_FACTORY_RESET,
    SERVICE_LINK_ZONE_PLAYER,
    SERVICE_REBOOT,
    SERVICE_SET_AMP_NAME,
    SERVICE_SET_BALANCE,
    SERVICE_SET_BASS,
    SERVICE_SET_BRIDGE,
    SERVICE_SET_DELAY,
    SERVICE_SET_DSP_PRESET,
    SERVICE_SET_INPUT_GAIN,
    SERVICE_SET_INPUT_NAME,
    SERVICE_SET_LIMITER,
    SERVICE_SET_LOUDNESS,
    SERVICE_SET_OUTPUT_NAME,
    SERVICE_SET_TREBLE,
)
from .coordinator import EpisodeResponseCoordinator, EpisodeResponseData
from .errors import AuthenticationFailed, ConnectionFailed

_LOGGER = logging.getLogger(__name__)

type EpisodeConfigEntry = ConfigEntry[EpisodeResponseData]

_STORAGE_VERSION = 1
_LINKS_STORAGE_KEY = f"{DOMAIN}_zone_links"


async def _async_load_zone_links(hass: HomeAssistant, entry_id: str) -> dict[int, str]:
    store = Store[dict[str, Any]](
        hass, _STORAGE_VERSION, f"{_LINKS_STORAGE_KEY}_{entry_id}"
    )
    data = await store.async_load() or {}
    links: dict[int, str] = {}
    raw = data.get("links", {})
    if isinstance(raw, dict):
        for k, v in raw.items():
            try:
                zone = int(k)
            except (TypeError, ValueError):
                continue
            if isinstance(v, str) and v:
                links[zone] = v
    return links


async def _async_save_zone_links(
    hass: HomeAssistant, entry_id: str, links: dict[int, str]
) -> None:
    store = Store[dict[str, Any]](
        hass, _STORAGE_VERSION, f"{_LINKS_STORAGE_KEY}_{entry_id}"
    )
    await store.async_save({"links": {str(k): v for k, v in links.items()}})


async def async_setup_entry(hass: HomeAssistant, entry: EpisodeConfigEntry) -> bool:
    """Set up Episode Response DSP Amplifier from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]
    username = entry.data[CONF_USERNAME]
    password = entry.data[CONF_PASSWORD]
    poll_interval = entry.options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    client = EpisodeResponseClient(host, port, username, password)

    try:
        await client.connect()
    except AuthenticationFailed as err:
        raise ConfigEntryAuthFailed(
            "Invalid credentials for Episode Response amplifier"
        ) from err
    except ConnectionFailed as err:
        raise ConfigEntryNotReady(
            f"Cannot connect to Episode Response amplifier at {host}:{port}"
        ) from err

    coordinator = EpisodeResponseCoordinator(
        hass, client, entry, poll_interval=poll_interval
    )

    # Do an initial full poll
    await coordinator.async_config_entry_first_refresh()

    # Store runtime data
    entry.runtime_data = EpisodeResponseData(client, coordinator)

    # Load per-zone linked player mapping (used for Music Assistant passthrough).
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})
    hass.data[DOMAIN][entry.entry_id]["zone_links"] = await _async_load_zone_links(
        hass, entry.entry_id
    )

    # Register the amplifier device
    _register_device(hass, entry, client)

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    _register_services(hass)

    # Listen for options updates
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    _LOGGER.info(
        "Episode Response DSP Amplifier '%s' set up successfully (%s:%s)",
        client.state.name or "Unnamed",
        host,
        port,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EpisodeConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        data: EpisodeResponseData = entry.runtime_data
        await data.client.disconnect()
        _LOGGER.info("Episode Response DSP Amplifier unloaded")

    # Keep stored links; just clean runtime memory.
    if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    # Unregister services if this was the last entry
    remaining = hass.config_entries.async_entries(DOMAIN)
    if len(remaining) <= 1:  # The entry being unloaded is still in the list
        _unregister_services(hass)

    return unload_ok


async def _async_options_updated(
    hass: HomeAssistant, entry: EpisodeConfigEntry
) -> None:
    """Handle options update — reload the entry."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_device(
    hass: HomeAssistant,
    entry: ConfigEntry,
    client: EpisodeResponseClient,
) -> None:
    """Register the amplifier in the device registry."""
    device_reg = dr.async_get(hass)
    device_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, client.state.mac_address or f"{client.host}:{client.port}")},
        manufacturer=MANUFACTURER,
        model=DEFAULT_MODEL,
        name=client.state.name or f"Episode Response Amp ({client.host})",
        sw_version=client.state.firmware or None,
        configuration_url=f"http://{client.host}",
    )


def _get_entry_data(hass: HomeAssistant, call: ServiceCall) -> EpisodeResponseData:
    """Resolve the config entry data from a service call."""
    entry_id = call.data.get(ATTR_ENTRY_ID)
    if entry_id:
        entry = hass.config_entries.async_get_entry(entry_id)
        if entry and hasattr(entry, "runtime_data"):
            return entry.runtime_data

    # Fall back to the first (or only) entry
    entries = hass.config_entries.async_entries(DOMAIN)
    if not entries:
        raise ValueError("No Episode Response amplifier configured")
    entry = entries[0]
    return entry.runtime_data


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-level services."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_DSP_PRESET):
        return  # Already registered

    import voluptuous as vol  # noqa: PLC0415
    from homeassistant.helpers import config_validation as cv  # noqa: PLC0415

    # ---- link_zone_player ----
    async def handle_link_zone_player(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        entry_id = data.coordinator.config_entry.entry_id
        zone = int(call.data[ATTR_ZONE])
        target = str(call.data.get("entity_id") or "").strip()

        links: dict[int, str] = hass.data.setdefault(DOMAIN, {}).setdefault(
            entry_id, {}
        ).setdefault("zone_links", {})

        if not target or target.lower() in {"none", "null", "unset"}:
            links.pop(zone, None)
        else:
            links[zone] = target

        await _async_save_zone_links(hass, entry_id, links)
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_LINK_ZONE_PLAYER,
        handle_link_zone_player,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTRY_ID): cv.string,
                vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
                # Entity id of an existing HA media_player to proxy, or "none" to clear.
                vol.Required("entity_id"): cv.string,
            }
        ),
    )

    # ---- set_dsp_preset ----
    async def handle_set_dsp_preset(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        zone = call.data[ATTR_ZONE]
        preset = call.data[ATTR_PRESET]
        await data.client.set_zone_dsp_preset(zone, preset)
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DSP_PRESET,
        handle_set_dsp_preset,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
        }),
    )

    # ---- set_bass ----
    async def handle_set_bass(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_bass(call.data[ATTR_ZONE], call.data[ATTR_VALUE])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BASS,
        handle_set_bass,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=-12, max=12)),
        }),
    )

    # ---- set_treble ----
    async def handle_set_treble(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_treble(call.data[ATTR_ZONE], call.data[ATTR_VALUE])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TREBLE,
        handle_set_treble,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=-12, max=12)),
        }),
    )

    # ---- set_balance ----
    async def handle_set_balance(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_balance(call.data[ATTR_ZONE], call.data[ATTR_VALUE])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BALANCE,
        handle_set_balance,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=-20, max=20)),
        }),
    )

    # ---- set_input_gain ----
    async def handle_set_input_gain(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_input_gain(call.data[ATTR_INPUT], call.data[ATTR_VALUE])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INPUT_GAIN,
        handle_set_input_gain,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_INPUT): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=-12, max=12)),
        }),
    )

    # ---- set_loudness ----
    async def handle_set_loudness(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_loudness(call.data[ATTR_ZONE], call.data[ATTR_ENABLED])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LOUDNESS,
        handle_set_loudness,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_ENABLED): cv.boolean,
        }),
    )

    # ---- set_delay ----
    async def handle_set_delay(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_delay(call.data[ATTR_ZONE], call.data[ATTR_VALUE])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DELAY,
        handle_set_delay,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(min=0, max=1000)),
        }),
    )

    # ---- set_bridge ----
    async def handle_set_bridge(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_bridge(call.data[ATTR_ZONE], call.data[ATTR_ENABLED])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BRIDGE,
        handle_set_bridge,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_ENABLED): cv.boolean,
        }),
    )

    # ---- set_limiter ----
    async def handle_set_limiter(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_zone_limiter(call.data[ATTR_ZONE], call.data[ATTR_ENABLED])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_LIMITER,
        handle_set_limiter,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_ENABLED): cv.boolean,
        }),
    )

    # ---- reboot ----
    async def handle_reboot(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.reboot()

    hass.services.async_register(
        DOMAIN,
        SERVICE_REBOOT,
        handle_reboot,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
        }),
    )

    # ---- factory_reset ----
    async def handle_factory_reset(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.factory_reset()

    hass.services.async_register(
        DOMAIN,
        SERVICE_FACTORY_RESET,
        handle_factory_reset,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
        }),
    )

    # ---- set_amp_name ----
    async def handle_set_amp_name(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_amp_name(call.data[ATTR_NAME])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_AMP_NAME,
        handle_set_amp_name,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_NAME): cv.string,
        }),
    )

    # ---- set_output_name ----
    async def handle_set_output_name(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_output_name(call.data[ATTR_ZONE], call.data[ATTR_NAME])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_OUTPUT_NAME,
        handle_set_output_name,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_ZONE): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_NAME): cv.string,
        }),
    )

    # ---- set_input_name ----
    async def handle_set_input_name(call: ServiceCall) -> None:
        data = _get_entry_data(hass, call)
        await data.client.set_input_name(call.data[ATTR_INPUT], call.data[ATTR_NAME])
        await data.coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_INPUT_NAME,
        handle_set_input_name,
        schema=vol.Schema({
            vol.Optional(ATTR_ENTRY_ID): cv.string,
            vol.Required(ATTR_INPUT): vol.All(vol.Coerce(int), vol.Range(min=0, max=5)),
            vol.Required(ATTR_NAME): cv.string,
        }),
    )

    _LOGGER.debug("Episode Response services registered")


def _unregister_services(hass: HomeAssistant) -> None:
    """Remove all integration services when the last entry is unloaded."""
    for service_name in ALL_SERVICES:
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)
    _LOGGER.debug("Episode Response services unregistered")
