"""The Schellenberg USB Stick integration."""

from __future__ import annotations

import logging
from types import MappingProxyType

import voluptuous as vol
from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import SchellenbergUsbApi
from .const import (
    CMD_DOWN,
    CMD_STOP,
    CMD_UP,
    CONF_GROUP_ID,
    CONF_SERIAL_PORT,
    DOMAIN,
    SERVICE_SEND_NATIVE_GROUP_COMMAND,
    PLATFORMS,
    SUBENTRY_TYPE_HUB,
    SchellenbergConfigEntry,
)

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: cv.config_entry_only_config_schema(DOMAIN)},
    extra=vol.ALLOW_EXTRA,
)

# Store setup callbacks for each entry so we can track subentries
_SETUP_CALLBACKS: dict[str, dict] = {}
_SERVICES_REGISTERED = False


def _action_to_command(action: str) -> str:
    """Map service action names to Schellenberg command bytes."""
    return {
        "up": CMD_UP,
        "open": CMD_UP,
        "down": CMD_DOWN,
        "close": CMD_DOWN,
        "stop": CMD_STOP,
    }[action]


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register integration services once."""
    global _SERVICES_REGISTERED  # noqa: PLW0603

    if _SERVICES_REGISTERED:
        return

    async def _async_send_native_group_command(call) -> None:
        """Send a native group command through the first configured USB stick."""
        entries = hass.config_entries.async_entries(DOMAIN)
        entry = next(
            (
                item
                for item in entries
                if CONF_SERIAL_PORT in item.data and getattr(item, "runtime_data", None)
            ),
            None,
        )
        if entry is None:
            _LOGGER.error("No active Schellenberg USB hub found for group command")
            return

        api: SchellenbergUsbApi = entry.runtime_data
        await api.control_native_group(
            _action_to_command(call.data["action"]),
            call.data.get(CONF_GROUP_ID),
        )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_NATIVE_GROUP_COMMAND,
        _async_send_native_group_command,
        schema=vol.Schema(
            {
                vol.Required("action"): vol.In(
                    ["up", "down", "stop", "open", "close"]
                ),
                vol.Optional(CONF_GROUP_ID): cv.string,
            }
        ),
    )
    _SERVICES_REGISTERED = True


async def async_setup_entry(
    hass: HomeAssistant, entry: SchellenbergConfigEntry
) -> bool:
    """Set up Schellenberg USB from a config entry."""
    _LOGGER.debug("Setup entry called for entry: %s", entry.entry_id)
    _LOGGER.debug("Entry data keys: %s", list(entry.data.keys()))

    # This is a hub entry - it has CONF_SERIAL_PORT
    if CONF_SERIAL_PORT not in entry.data:
        _LOGGER.warning(
            "Received async_setup_entry for non-hub entry %s, ignoring", entry.entry_id
        )
        return False

    _LOGGER.info("Setting up hub entry: %s", entry.title)
    hass.data.setdefault(DOMAIN, {})

    port = entry.data[CONF_SERIAL_PORT]
    api = SchellenbergUsbApi(hass, port)

    # Store API in runtime_data for platforms and services access
    entry.runtime_data = api

    await _async_register_services(hass)

    # Start the connection
    hass.async_create_task(api.connect())

    # Ensure we have a dedicated hub subentry so hub-level devices/entities
    # (like the LED) do not appear under "Devices that don't belong to a sub-entry".
    hub_subentry = next(
        (s for s in entry.subentries.values() if s.subentry_type == SUBENTRY_TYPE_HUB),
        None,
    )
    if hub_subentry is None:
        _LOGGER.debug("Creating hub subentry for entry %s", entry.entry_id)
        hub_subentry = ConfigSubentry(
            data=MappingProxyType({}),
            subentry_type=SUBENTRY_TYPE_HUB,
            title="Hub",
            unique_id=None,
        )
        hass.config_entries.async_add_subentry(entry, hub_subentry)

    # Attach or create hub device under hub subentry to avoid ungrouped duplication
    device_registry = dr.async_get(hass)
    hub_device = device_registry.async_get_device(
        identifiers={(DOMAIN, entry.entry_id)}
    )
    if hub_device is None:
        _LOGGER.debug(
            "Creating hub device and attaching to hub subentry %s",
            hub_subentry.subentry_id,
        )
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            config_subentry_id=hub_subentry.subentry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name="Schellenberg USB Stick",
            manufacturer="Schellenberg",
            model="USB Stick",
        )
    else:
        _LOGGER.debug(
            "Ensuring existing hub device %s is associated with entry %s and subentry %s",
            hub_device.id,
            entry.entry_id,
            hub_subentry.subentry_id,
        )
        device_registry.async_update_device(
            hub_device.id,
            add_config_entry_id=entry.entry_id,
            add_config_subentry_id=hub_subentry.subentry_id,
        )

    # Forward setup to the hub's platforms (cover, sensor, switch)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Add listener to reload entry when subentries are added
    async def _on_entry_updated(
        hass_instance: HomeAssistant, updated_entry: SchellenbergConfigEntry
    ) -> None:
        """Handle updates to the hub entry (including subentry additions)."""
        current_subentries = set(updated_entry.subentries.keys())
        known_subentries = _SETUP_CALLBACKS.get(entry.entry_id, {}).get(
            "subentry_ids", set()
        )

        _LOGGER.debug(
            "Entry update detected. Current subentries: %s, Known subentries: %s",
            current_subentries,
            known_subentries,
        )

        if current_subentries != known_subentries:
            _LOGGER.info(
                "Subentries changed, reloading entry. Old: %s, New: %s",
                known_subentries,
                current_subentries,
            )
            # Update tracked subentries before reloading
            _SETUP_CALLBACKS[entry.entry_id]["subentry_ids"] = current_subentries
            # Reload the entire entry to re-setup all platforms with new subentries
            await hass_instance.config_entries.async_reload(entry.entry_id)

    entry.add_update_listener(_on_entry_updated)

    # Track known subentries
    if entry.entry_id not in _SETUP_CALLBACKS:
        _SETUP_CALLBACKS[entry.entry_id] = {}
    _SETUP_CALLBACKS[entry.entry_id]["subentry_ids"] = set(entry.subentries.keys())

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: SchellenbergConfigEntry
) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        api: SchellenbergUsbApi = entry.runtime_data
        await api.disconnect()

    return unload_ok
