"""Tests for the Schellenberg USB constants."""

from __future__ import annotations

from custom_components.schellenberg_usb.const import (
    CONF_CLOSE_TIME,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_LEARN_REMOTE,
    CONF_OPEN_TIME,
    CONF_REMOTE_CONTROLS,
    CONF_REMOTE_NAME,
    CONF_SERIAL_PORT,
    CONF_VIRTUAL_GROUPS,
    CMD_ALLOW_PAIRING,
    CMD_DOWN,
    CMD_MANUAL_DOWN,
    CMD_MANUAL_UP,
    CMD_PAIR,
    CMD_SET_LOWER_ENDPOINT,
    CMD_SET_UPPER_ENDPOINT,
    CMD_STOP,
    CMD_UP,
    DOMAIN,
    GROUP_CHANNEL_ALL,
    SERVICE_SEND_NATIVE_GROUP_COMMAND,
    SIGNAL_CALIBRATION_COMPLETED,
    SIGNAL_DEVICE_EVENT,
    SIGNAL_DEVICE_PAIRED,
    SIGNAL_PAIRING_STARTED,
    SIGNAL_PAIRING_TIMEOUT,
    SIGNAL_REMOTE_EVENT,
    SIGNAL_RSSI_UPDATED,
    SIGNAL_STICK_STATUS_UPDATED,
    SUBENTRY_TYPE_BLIND,
    SUBENTRY_TYPE_HUB,
    SUBENTRY_TYPE_LED,
)


class TestConstants:
    """Verify all constants are correctly defined."""

    def test_domain(self):
        """Test domain constant."""
        assert DOMAIN == "schellenberg_usb"

    def test_config_keys(self):
        """Test config key strings."""
        assert CONF_SERIAL_PORT == "serial_port"
        assert CONF_DEVICE_NAME == "device_name"
        assert CONF_VIRTUAL_GROUPS == "virtual_groups"
        assert CONF_REMOTE_CONTROLS == "remote_controls"
        assert CONF_GROUP_ID == "group_id"
        assert CONF_GROUP_NAME == "group_name"
        assert CONF_REMOTE_NAME == "remote_name"
        assert CONF_LEARN_REMOTE == "learn_remote"
        assert CONF_OPEN_TIME == "open_time"
        assert CONF_CLOSE_TIME == "close_time"
        assert CONF_DEVICE_ID == "device_id"

    def test_command_bytes(self):
        """Test command byte values."""
        assert CMD_STOP == "00"
        assert CMD_UP == "01"
        assert CMD_DOWN == "02"
        assert CMD_ALLOW_PAIRING == "40"
        assert CMD_MANUAL_UP == "41"
        assert CMD_MANUAL_DOWN == "42"
        assert CMD_PAIR == "60"
        assert CMD_SET_UPPER_ENDPOINT == "61"
        assert CMD_SET_LOWER_ENDPOINT == "62"

    def test_subentry_types(self):
        """Test subentry type constants."""
        assert SUBENTRY_TYPE_LED == "led"
        assert SUBENTRY_TYPE_HUB == "hub"
        assert SUBENTRY_TYPE_BLIND == "blind"

    def test_signals(self):
        """Test dispatcher signal strings."""
        assert SIGNAL_DEVICE_EVENT == f"{DOMAIN}_device_event"
        assert SIGNAL_DEVICE_PAIRED == f"{DOMAIN}_device_paired"
        assert SIGNAL_PAIRING_STARTED == f"{DOMAIN}_pairing_started"
        assert SIGNAL_PAIRING_TIMEOUT == f"{DOMAIN}_pairing_timeout"
        assert SIGNAL_STICK_STATUS_UPDATED == f"{DOMAIN}_stick_status_updated"
        assert SIGNAL_CALIBRATION_COMPLETED == f"{DOMAIN}_calibration_completed"
        assert SIGNAL_REMOTE_EVENT == f"{DOMAIN}_remote_event"
        assert SIGNAL_RSSI_UPDATED == f"{DOMAIN}_rssi_updated"

    def test_group_channel(self):
        """Test group channel constant."""
        assert GROUP_CHANNEL_ALL == "05"

    def test_service_names(self):
        """Test service name constants."""
        assert SERVICE_SEND_NATIVE_GROUP_COMMAND == "send_native_group_command"
