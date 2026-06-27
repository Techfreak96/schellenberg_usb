"""Tests for the Schellenberg USB API module."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.schellenberg_usb.api import SchellenbergUsbApi
from custom_components.schellenberg_usb.const import (
    CMD_DOWN,
    CMD_STOP,
    CMD_TRANSMIT,
    CMD_UP,
    DOMAIN,
    EVENT_REMOTE_BUTTON_PRESSED,
)


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance."""
    hass = MagicMock()
    hass.loop = asyncio.get_event_loop()
    hass.data = {}
    hass.bus = MagicMock()
    hass.config_entries = MagicMock()
    return hass


@pytest.fixture
def api(mock_hass):
    """Create a SchellenbergUsbApi instance with mocked hass."""
    return SchellenbergUsbApi(mock_hass, "/dev/ttyUSB0")


class TestSchellenbergUsbApi:
    """Test suite for the SchellenbergUsbApi class."""

    def test_init(self, api):
        """Test initial state of the API."""
        assert api.port == "/dev/ttyUSB0"
        assert api.is_connected is False
        assert api._registered_devices == {}
        assert api._registered_remotes == {}
        assert api._device_rssi == {}
        assert api._discovered_devices == set()
        assert api.device_version is None
        assert api.device_mode is None

    def test_command_to_button(self):
        """Test mapping of command bytes to button names."""
        assert SchellenbergUsbApi._command_to_button(CMD_UP) == "up"
        assert SchellenbergUsbApi._command_to_button(CMD_DOWN) == "down"
        assert SchellenbergUsbApi._command_to_button(CMD_STOP) == "stop"
        assert SchellenbergUsbApi._command_to_button("99") is None

    def test_normalize_channel(self):
        """Test channel normalization."""
        assert SchellenbergUsbApi._normalize_channel("01") == "1"
        assert SchellenbergUsbApi._normalize_channel("05") == "5"
        assert SchellenbergUsbApi._normalize_channel("10") == "10"
        assert SchellenbergUsbApi._normalize_channel("FF") == "FF"
        assert SchellenbergUsbApi._normalize_channel("XX") == "XX"

    def test_register_remote(self, api):
        """Test remote registration."""
        api.register_remote("A1B2C3", "1")
        assert api.is_remote_known("A1B2C3") is True
        assert api.is_remote_known("UNKNOWN") is False

    def test_register_existing_remotes(self, api):
        """Test bulk remote registration from stored config."""
        remotes = [
            {"remote_id": "A1B2C3", "channel": "1"},
            {"remote_id": "D4E5F6", "channel": "2"},
        ]
        api.register_existing_remotes(remotes)
        assert api.is_remote_known("A1B2C3") is True
        assert api.is_remote_known("D4E5F6") is True
        assert api.is_remote_known("UNKNOWN") is False

    def test_get_device_rssi_default(self, api):
        """Test RSSI returns None when no signal received."""
        assert api.get_device_rssi("A1B2C3") is None

    def test_register_entity(self, api):
        """Test blind entity registration."""
        api.register_entity("A1B2C3", "10")
        assert "A1B2C3" in api._registered_devices
        assert api._registered_devices["A1B2C3"] == "10"

    def test_remove_known_device(self, api):
        """Test blind device removal."""
        api.register_entity("A1B2C3", "10")
        api.remove_known_device("A1B2C3")
        assert "A1B2C3" not in api._registered_devices

    def test_initialize_next_device_enum_first(self, api):
        """Test first device enum starts at 0x10."""
        device_enum = api.initialize_next_device_enum()
        assert device_enum == "10"

    def test_initialize_next_device_enum_increment(self, api):
        """Test next device enum increments correctly."""
        api.register_entity("DEV1", "10")
        api.register_entity("DEV2", "11")
        device_enum = api.initialize_next_device_enum()
        assert device_enum == "12"

    @pytest.mark.asyncio
    async def test_control_blind_valid(self, api):
        """Test blind control builds correct command format."""
        api.send_command = AsyncMock()
        await api.control_blind("10", CMD_UP)
        api.send_command.assert_called_once_with(
            f"{CMD_TRANSMIT}10{CMD_UP}0000"
        )

    @pytest.mark.asyncio
    async def test_control_blind_invalid_action(self, api):
        """Test blind control ignores invalid actions."""
        api.send_command = AsyncMock()
        await api.control_blind("10", "INVALID")
        api.send_command.assert_not_called()

    @pytest.mark.asyncio
    async def test_control_native_group_valid(self, api):
        """Test native group command builds correct format."""
        api.send_command = AsyncMock()
        await api.control_native_group(CMD_UP, "05")
        api.send_command.assert_called_once_with(
            f"{CMD_TRANSMIT}05{CMD_UP}0000"
        )

    @pytest.mark.asyncio
    async def test_handle_remote_message_fires_event(self, api):
        """Test remote message fires bus event."""
        api._handle_remote_message(
            remote_id="A1B2C3",
            channel="1",
            button="up",
            command=CMD_UP,
            raw_message="ss01A1B2C3000001000000",
        )
        api.hass.bus.async_fire.assert_called_once_with(
            EVENT_REMOTE_BUTTON_PRESSED,
            {
                "remote_id": "A1B2C3",
                "channel": "1",
                "button": "up",
                "command": CMD_UP,
                "raw": "ss01A1B2C3000001000000",
            },
        )

    def test_register_existing_devices(self, api):
        """Test bulk blind registration from storage."""
        devices = [
            {"id": "DEV1", "enum": "10"},
            {"id": "DEV2", "enum": "11"},
        ]
        api.register_existing_devices(devices)
        assert "DEV1" in api._registered_devices
        assert "DEV2" in api._registered_devices
        assert api._registered_devices["DEV1"] == "10"
