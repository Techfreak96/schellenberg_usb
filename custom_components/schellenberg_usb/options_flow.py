"""Options flow for Schellenberg USB hub."""

from __future__ import annotations

import logging
from typing import Any

import serial
import voluptuous as vol

from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BLIND_LOCK_SENSORS,
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

OPTION_MENU = "menu_option"
OPT_CONFIGURE = "configure_port"
OPT_LEARN_REMOTE = "learn_remote"
OPT_MANAGE_REMOTES = "manage_remotes"
OPT_MANAGE_GROUPS = "manage_groups"
OPT_CONFIGURE_SAFETY = "configure_safety"


class SchellenbergOptionsFlowHandler(OptionsFlow):
    """Handle hub options."""

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
        """Show the configuration menu."""
        if user_input is not None:
            choice = user_input.get(OPTION_MENU)
            if choice == OPT_CONFIGURE:
                return await self.async_step_configure_port()
            if choice == OPT_LEARN_REMOTE:
                return await self.async_step_learn_remote()
            if choice == OPT_MANAGE_REMOTES:
                return await self.async_step_manage_remotes()
            if choice == OPT_MANAGE_GROUPS:
                return await self.async_step_manage_groups()
            if choice == OPT_CONFIGURE_SAFETY:
                return await self.async_step_configure_safety()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(OPTION_MENU): vol.In(
                        {
                            OPT_CONFIGURE: "USB-Anschluss konfigurieren",
                            OPT_LEARN_REMOTE: "Neue Fernbedienung anlernen",
                            OPT_MANAGE_REMOTES: "Fernbedienungen verwalten",
                            OPT_MANAGE_GROUPS: "Virtuelle Gruppen verwalten",
                            OPT_CONFIGURE_SAFETY: "Sicherheitssperre konfigurieren",
                        }
                    ),
                }
            ),
            errors=self._errors,
        )

    async def async_step_configure_port(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the USB serial port."""
        self._errors = {}
        current_port = self.config_entry.data.get(CONF_SERIAL_PORT, "/dev/ttyUSB0")

        if user_input is not None:
            new_port = user_input[CONF_SERIAL_PORT]
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
                    updated = {**self.config_entry.data, CONF_SERIAL_PORT: new_port}
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, data=updated
                    )
                    self.hass.config_entries.async_schedule_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data={})
                return self._show_port_form(current_port)
            return self.async_create_entry(title="", data={})

        return self._show_port_form(current_port)

    def _show_port_form(self, current_port: str) -> ConfigFlowResult:
        """Show the port configuration form."""
        return self.async_show_form(
            step_id="configure_port",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT, default=current_port
                    ): selector.TextSelector(),
                }
            ),
            errors=self._errors,
        )

    async def async_step_learn_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Learn a new physical remote by listening for a button press."""
        self._errors = {}
        if user_input is not None:
            api = getattr(self.config_entry, "runtime_data", None)
            if api is None:
                self._errors["base"] = "cannot_connect"
            else:
                remote = await api.learn_remote_and_wait()
                if remote is None:
                    self._errors["base"] = "remote_learning_timeout"
                else:
                    updated_options = dict(self.config_entry.options)
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
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=updated_options
                    )
                    self.hass.config_entries.async_schedule_reload(
                        self.config_entry.entry_id
                    )
                    return self.async_create_entry(title="", data=updated_options)

            if self._errors:
                return self.async_show_form(
                    step_id="learn_remote",
                    data_schema=vol.Schema(
                        {
                            vol.Optional(CONF_REMOTE_NAME): selector.TextSelector(),
                        }
                    ),
                    errors=self._errors,
                )

        return self.async_show_form(
            step_id="learn_remote",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_REMOTE_NAME): selector.TextSelector(),
                }
            ),
            errors=self._errors,
            description_placeholders={
                "instruction": "Press any button on the physical remote within 30 seconds"
            },
        )

    async def async_step_manage_remotes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """List registered remotes and allow deletion."""
        self._errors = {}
        current_options = dict(self.config_entry.options)
        remotes = list(current_options.get(CONF_REMOTE_CONTROLS, []))

        if user_input is not None:
            selected = user_input.get("remove_remote", [])
            if selected:
                updated_options = dict(current_options)
                updated_options[CONF_REMOTE_CONTROLS] = [
                    r for r in remotes if r.get("remote_id") not in selected
                ]
                self.hass.config_entries.async_update_entry(
                    self.config_entry, options=updated_options
                )
                self.hass.config_entries.async_schedule_reload(
                    self.config_entry.entry_id
                )
                return self.async_create_entry(title="", data=updated_options)
            return self.async_create_entry(title="", data=current_options)

        if not remotes:
            return self.async_abort(reason="no_remotes")

        remote_options = {
            r.get("remote_id"): r.get(CONF_REMOTE_NAME)
            or f"Remote {r.get('remote_id')} (ch{r.get('channel')})"
            for r in remotes
        }

        return self.async_show_form(
            step_id="manage_remotes",
            data_schema=vol.Schema(
                {
                    vol.Optional("remove_remote"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=list(remote_options.items()),
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=self._errors,
            description_placeholders={
                "count": str(len(remotes)),
            },
        )

    async def async_step_manage_groups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage virtual group IDs."""
        self._errors = {}
        current_options = dict(self.config_entry.options)

        if user_input is not None:
            updated_options = dict(current_options)
            group_id = user_input.get(CONF_GROUP_ID)
            if group_id:
                normalized_group_id = self._normalize_group_id(group_id)
                if len(normalized_group_id) != 2:
                    self._errors[CONF_GROUP_ID] = "invalid_group_id"
                else:
                    groups = list(updated_options.get(CONF_VIRTUAL_GROUPS, []))
                    groups = [
                        g
                        for g in groups
                        if g.get(CONF_GROUP_ID) != normalized_group_id
                    ]
                    groups.append(
                        {
                            CONF_GROUP_ID: normalized_group_id,
                            CONF_GROUP_NAME: user_input.get(CONF_GROUP_NAME)
                            or f"Group {normalized_group_id}",
                        }
                    )
                    updated_options[CONF_VIRTUAL_GROUPS] = groups
                    self.hass.config_entries.async_update_entry(
                        self.config_entry, options=updated_options
                    )
                    return self.async_create_entry(title="", data=updated_options)

            if self._errors:
                return self._show_group_form()
            return self.async_create_entry(title="", data=current_options)

        return self._show_group_form()

    def _show_group_form(self) -> ConfigFlowResult:
        """Show the group management form."""
        return self.async_show_form(
            step_id="manage_groups",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_GROUP_ID, default=GROUP_CHANNEL_ALL
                    ): selector.TextSelector(),
                    vol.Optional(CONF_GROUP_NAME): selector.TextSelector(),
                }
            ),
            errors=self._errors,
        )

    async def async_step_configure_safety(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure a binary_sensor per blind for auto-safety-lock."""
        self._errors = {}
        current_options = dict(self.config_entry.options)

        # Build a list of all paired blinds from subentries
        blinds: list[tuple[str, str]] = []
        for subentry in self.config_entry.subentries.values():
            device_id = subentry.data.get("device_id", "")
            device_name = subentry.title or f"Blind {device_id}"
            if device_id:
                blinds.append((device_id, device_name))

        if not blinds:
            return self.async_abort(reason="no_blinds")

        if user_input is not None:
            lock_sensors: dict[str, str] = {}
            for device_id, _ in blinds:
                sensor_entity = user_input.get(f"sensor_{device_id}")
                if sensor_entity:
                    lock_sensors[device_id] = sensor_entity

            updated_options = dict(current_options)
            updated_options[CONF_BLIND_LOCK_SENSORS] = lock_sensors
            self.hass.config_entries.async_update_entry(
                self.config_entry, options=updated_options
            )
            return self.async_create_entry(title="", data=updated_options)

        # Build schema with one text field per blind for sensor entity ID
        schema = {}
        for device_id, device_name in blinds:
            schema[vol.Optional(f"sensor_{device_id}")] = selector.TextSelector(
                selector.TextSelectorConfig(type="text"),
            )

        return self.async_show_form(
            step_id="configure_safety",
            data_schema=vol.Schema(schema),
            errors=self._errors,
            description_placeholders={
                "instruction": (
                    "Select a window/door sensor for each blind. "
                    "When the sensor is open, the blind will be locked "
                    "against closing (DOWN blocked)."
                )
            },
        )

    @callback
    def async_get_options_flow(self):
        """Return self (options flow factory compatibility)."""
        return self
