"""Sensor platform for Schellenberg USB stick status."""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SchellenbergUsbApi
from .const import (
    DOMAIN,
    SIGNAL_RSSI_UPDATED,
    SIGNAL_STICK_STATUS_UPDATED,
    SIGNAL_WINDOW_SENSOR,
    SUBENTRY_TYPE_BLIND,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_WINDOW_SENSOR,
    SchellenbergConfigEntry,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchellenbergConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Schellenberg USB sensor entities."""
    api: SchellenbergUsbApi = entry.runtime_data

    sensors: list[SensorEntity] = [
        SchellenbergConnectionSensor(api, entry),
        SchellenbergVersionSensor(api, entry),
        SchellenbergModeSensor(api, entry),
    ]

    # Hub subentry for hub-level sensors
    hub_subentry_id = next(
        (
            s.subentry_id
            for s in entry.subentries.values()
            if s.subentry_type == SUBENTRY_TYPE_HUB
        ),
        None,
    )

    # Create per-blind RSSI sensors from subentries
    blind_sensors: list[SensorEntity] = []
    window_sensors: list[SensorEntity] = []

    for subentry in entry.subentries.values():
        if subentry.subentry_type == SUBENTRY_TYPE_BLIND:
            device_id = subentry.data.get("device_id")
            device_name = subentry.title or f"Blind {device_id}"
            if device_id:
                blind_sensors.append(
                    SchellenbergRssiSensor(
                        api=api,
                        entry=entry,
                        device_id=device_id,
                        device_name=device_name,
                    )
                )

        # Create window handle sensor entities
        if subentry.subentry_type == SUBENTRY_TYPE_WINDOW_SENSOR:
            device_id = subentry.data.get("device_id")
            device_name = subentry.title or f"Window Sensor {device_id}"
            if device_id:
                window_sensors.append(
                    SchellenbergWindowSensor(
                        api=api,
                        entry=entry,
                        device_id=device_id,
                        device_name=device_name,
                    )
                )

    _LOGGER.debug(
        "Setting up %d hub sensors, %d blind RSSI sensors, "
        "and %d window sensors",
        len(sensors),
        len(blind_sensors),
        len(window_sensors),
    )
    async_add_entities(sensors, config_subentry_id=hub_subentry_id)
    if blind_sensors:
        async_add_entities(blind_sensors)
    if window_sensors:
        async_add_entities(window_sensors)


class SchellenbergBaseSensor(SensorEntity):
    """Base class for Schellenberg USB stick sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, api: SchellenbergUsbApi, entry: SchellenbergConfigEntry) -> None:
        """Initialize the sensor."""
        self.api = api
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Schellenberg USB Stick",
            manufacturer="Schellenberg",
            model="USB Stick",
            sw_version=api.device_version,
        )

    @property
    def available(self) -> bool:
        """Return if entity is available.

        USB stick sensors are available when the stick is connected.
        """
        return self.api.is_connected

    async def async_added_to_hass(self) -> None:
        """Subscribe to status updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_STICK_STATUS_UPDATED, self._handle_status_update
            )
        )

    @callback
    def _handle_status_update(self) -> None:
        """Handle status update from API."""
        self.async_write_ha_state()


class SchellenbergConnectionSensor(SchellenbergBaseSensor):
    """Sensor for USB stick connection status."""

    _attr_translation_key = "connection_status"

    def __init__(self, api: SchellenbergUsbApi, entry: SchellenbergConfigEntry) -> None:
        """Initialize the connection sensor."""
        super().__init__(api, entry)
        self._attr_unique_id = f"{entry.entry_id}_connection"

    @property
    def native_value(self) -> str:
        """Return the connection status."""
        return "Connected" if self.api.is_connected else "Disconnected"

    @property
    def icon(self) -> str:
        """Return the icon based on connection status."""
        return "mdi:usb" if self.api.is_connected else "mdi:usb-off"


class SchellenbergVersionSensor(SchellenbergBaseSensor):
    """Sensor for USB stick firmware version."""

    _attr_translation_key = "firmware_version"

    def __init__(self, api: SchellenbergUsbApi, entry: SchellenbergConfigEntry) -> None:
        """Initialize the version sensor."""
        super().__init__(api, entry)
        self._attr_unique_id = f"{entry.entry_id}_version"

    @property
    def native_value(self) -> str | None:
        """Return the firmware version."""
        return self.api.device_version

    @property
    def icon(self) -> str:
        """Return the icon."""
        return "mdi:chip"


class SchellenbergModeSensor(SchellenbergBaseSensor):
    """Sensor for USB stick operating mode."""

    _attr_translation_key = "operating_mode"

    def __init__(self, api: SchellenbergUsbApi, entry: SchellenbergConfigEntry) -> None:
        """Initialize the mode sensor."""
        super().__init__(api, entry)
        self._attr_unique_id = f"{entry.entry_id}_mode"

    @property
    def native_value(self) -> str | None:
        """Return the operating mode."""
        mode = self.api.device_mode
        if mode:
            return mode.capitalize()
        return None

    @property
    def icon(self) -> str:
        """Return the icon based on mode."""
        mode = self.api.device_mode
        if mode == "listening":
            return "mdi:ear-hearing"
        if mode == "bootloader":
            return "mdi:restart"
        if mode == "initial":
            return "mdi:power"
        return "mdi:help-circle"


class SchellenbergRssiSensor(SensorEntity):
    """Per-blind signal strength (RSSI) sensor.

    Receives signal strength updates from the API via the dispatcher
    whenever a valid message with RSSI bytes is received from the blind.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "signal_strength"
    _attr_native_unit_of_measurement = "dBm"
    _attr_device_class = "signal_strength"
    _attr_suggested_display_precision = 0

    def __init__(
        self,
        api: SchellenbergUsbApi,
        entry: SchellenbergConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the RSSI sensor.

        Args:
            api: The API instance.
            entry: The config entry.
            device_id: 6-char hex ID of the blind.
            device_name: Friendly name for display.

        """
        self.api = api
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_rssi_{device_id}"
        self._attr_name = f"{device_name} Signal"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.api.is_connected

    @property
    def native_value(self) -> int | None:
        """Return the last known RSSI value for this device."""
        return self.api.get_device_rssi(self._device_id)

    @property
    def icon(self) -> str:
        """Return the icon based on signal strength."""
        rssi = self.api.get_device_rssi(self._device_id)
        if rssi is None:
            return "mdi:wifi-off"
        if rssi > 200:
            return "mdi:wifi-strength-4"
        if rssi > 150:
            return "mdi:wifi-strength-3"
        if rssi > 100:
            return "mdi:wifi-strength-2"
        return "mdi:wifi-strength-1"

    async def async_added_to_hass(self) -> None:
        """Subscribe to RSSI updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_RSSI_UPDATED}_{self._device_id}",
                self._handle_rssi_update,
            )
        )

    @callback
    def _handle_rssi_update(self, rssi: int) -> None:
        """Update state when new RSSI data arrives."""
        self.async_write_ha_state()


class SchellenbergWindowSensor(SensorEntity):
    """Represents a Schellenberg window handle sensor.

    These unidirectional sensors report their handle position (closed,
    tilted, open) via radio signals received by the USB stick. The
    state updates in real-time whenever the handle is moved.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "window_handle"
    _attr_device_class = "window"

    def __init__(
        self,
        api: SchellenbergUsbApi,
        entry: SchellenbergConfigEntry,
        device_id: str,
        device_name: str,
    ) -> None:
        """Initialize the window sensor.

        Args:
            api: The API instance.
            entry: The config entry.
            device_id: 6-char hex ID of the sensor.
            device_name: Friendly name for display.

        """
        self.api = api
        self._device_id = device_id
        self._attr_unique_id = f"{entry.entry_id}_window_{device_id}"
        self._attr_name = device_name
        self._attr_native_value = "unknown"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.api.is_connected

    @property
    def icon(self) -> str:
        """Return the icon based on window state."""
        state_map = {
            "closed": "mdi:window-closed-variant",
            "tilted": "mdi:window-open-variant",
            "open": "mdi:window-open",
        }
        return state_map.get(str(self._attr_native_value), "mdi:window-closed")

    async def async_added_to_hass(self) -> None:
        """Subscribe to window sensor state updates."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_WINDOW_SENSOR}_{self._device_id}",
                self._handle_window_event,
            )
        )

    @callback
    def _handle_window_event(self, state: str, command: str) -> None:
        """Update state on window handle event."""
        _LOGGER.debug(
            "Window sensor %s state changed: %s (cmd=%s)",
            self._device_id,
            state,
            command,
        )
        self._attr_native_value = state
        self.async_write_ha_state()
