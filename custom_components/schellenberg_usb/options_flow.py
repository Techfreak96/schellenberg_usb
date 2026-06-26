"""Options flow for Schellenberg USB hub.

Hub options allow changing the USB serial port path. Calibration is handled
exclusively during blind subentry pairing and not exposed here.
"""

from __future__ import annotations

import logging
from typing import Any

import serial
import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_GROUP_ID,
    CONF_GROUP_NAME,
    CONF_LEARN_REMOTE,
    CONF_REMOTE_CONTROLS,
    CONF_REMOTE_NAME,
    CONF_SERIAL_PORT,
    CONF_VIRTUAL_GROUPS,
    GROUP_CHANNEL_ALL,
)

_LOGGER = logging.getLogger(__name__)


class SchellenbergOptionsFlowHandler(OptionsFlow):
    """Handle hub options (edit serial port)."""

    def __init__(self) -> None:
        """Initialize hub options flow state."""
        self._errors: dict[str, str] = {}

    @staticmethod
    def _normalize_group_id(group_id: str) -> str:
        """Normalize decimal or hex group ids to the two-character protocol byte."""
        value = group_id.strip().upper()
        if value.isdigit():
            return f"{int(value):02X}"
        try:
            int(value, 16)
        except ValueError:
            return ""
        return value

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the USB serial port."""
        self._errors = {}
        current_port = self.config_entry.data.get(CONF_SERIAL_PORT, "/dev/ttyUSB0")
        current_options = dict(self.config_entry.options)
        if user_input is not None:
            new_port = user_input[CONF_SERIAL_PORT]
            updated_options = dict(current_options)

            group_id = user_input.get(CONF_GROUP_ID)
            if group_id:
                normalized_group_id = self._normalize_group_id(group_id)
                if len(normalized_group_id) != 2:
                    self._errors[CONF_GROUP_ID] = "invalid_group_id"
                else:
                    groups = list(updated_options.get(CONF_VIRTUAL_GROUPS, []))
                    groups = [
                        group
                        for group in groups
                        if group.get(CONF_GROUP_ID) != normalized_group_id
                    ]
                    groups.append(
                        {
                            CONF_GROUP_ID: normalized_group_id,
                            CONF_GROUP_NAME: user_input.get(CONF_GROUP_NAME)
                            or f"Group {normalized_group_id}",
                        }
                    )
                    updated_options[CONF_VIRTUAL_GROUPS] = groups

            if user_input.get(CONF_LEARN_REMOTE):
                api = getattr(self.config_entry, "runtime_data", None)
                if api is None:
                    self._errors["base"] = "cannot_connect"
                else:
                    remote = await api.learn_remote_and_wait()
                    if remote is None:
                        self._errors["base"] = "remote_learning_timeout"
                    else:
                        remotes = list(updated_options.get(CONF_REMOTE_CONTROLS, []))
                        remotes = [
                            item
                            for item in remotes
                            if not (
                                item.get("remote_id") == remote["remote_id"]
                                and item.get("channel") == remote["channel"]
                            )
                        ]
                        remotes.append(
                            {
                                CONF_REMOTE_NAME: user_input.get(CONF_REMOTE_NAME)
                                or f"Remote {remote['remote_id']} channel {remote['channel']}",
                                "remote_id": remote["remote_id"],
                                "channel": remote["channel"],
                                "last_button": remote["button"],
                            }
                        )
                        updated_options[CONF_REMOTE_CONTROLS] = remotes

            if self._errors:
                return self._show_form(current_port)

            if new_port != current_port:
                try:
                    serial_conn = serial.Serial(new_port)
                    serial_conn.close()
                except serial.SerialException:
                    _LOGGER.error(
                        "Failed to open serial port %s during options save", new_port
                    )
                    self._errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("Unexpected error validating port %s", new_port)
                    self._errors["base"] = "unknown"
                else:
                    # Update entry data and reload if changed
                    updated = {**self.config_entry.data, CONF_SERIAL_PORT: new_port}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=updated, options=updated_options
                    )
                    # Schedule reload for new port usage
                    self.hass.config_entries.async_schedule_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data=updated_options)
                return self._show_form(current_port)
            return self.async_create_entry(title="", data=updated_options)

        return self._show_form(current_port)

    def _show_form(self, current_port: str) -> ConfigFlowResult:
        """Show hub options form."""
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT, default=current_port
                    ): selector.TextSelector(),
                    vol.Optional(
                        CONF_GROUP_ID, default=GROUP_CHANNEL_ALL
                    ): selector.TextSelector(),
                    vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                    vol.Optional(CONF_LEARN_REMOTE, default=False): bool,
                    vol.Optional(CONF_REMOTE_NAME): selector.TextSelector(),
                }
            ),
            errors=self._errors,
        )

    @callback
    def async_get_options_flow(self):
        """Return self (options flow factory compatibility)."""
        return self
