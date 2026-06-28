"""Config flow for Schellenberg USB integration.

Credits / Sources:
- https://github.com/GimpArm/schellenberg_usb (Original config_flow by GimpArm)
- https://github.com/Hypfer/schellenberg-qivicon-usb (Protocol: pairing procedure)
"""

import asyncio
import logging
from typing import Any, Awaitable, cast

import serial  # NOTE: blocking open used only to sanity-check connectivity
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import (
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (
    CONF_CLOSE_TIME,
    CONF_OPEN_TIME,
    CONF_REMOTE_CONTROLS,
    CONF_SERIAL_PORT,
    DOMAIN,
    SUBENTRY_TYPE_BELT_DRIVE,
    SUBENTRY_TYPE_BLIND,
    SUBENTRY_TYPE_WINDOW_SENSOR,
)
from .options_flow import SchellenbergOptionsFlowHandler
from .options_flow_calibration import CalibrationFlowHandler

_LOGGER = logging.getLogger(__name__)


class SchellenbergUsbConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Schellenberg USB."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return SchellenbergOptionsFlowHandler()

    @classmethod
    @callback
    def async_get_supported_subentry_types(
        cls, config_entry: config_entries.ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Return subentries supported by this integration."""
        return {
            SUBENTRY_TYPE_BLIND: SchellenbergPairingSubentryFlow,
            SUBENTRY_TYPE_WINDOW_SENSOR: SchellenbergWindowSensorSubentryFlow,
            SUBENTRY_TYPE_BELT_DRIVE: SchellenbergPairingSubentryFlow,
        }

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._discovered_port: str | None = None
        self._discovered_title: str | None = None
        self._discovered_unique: str | None = None

    # -------------------------
    # MENU FLOW (Hub only)
    # -------------------------
    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show menu to set up hub."""
        # For now, only allow setting up the hub through the user flow
        # Device pairing is handled through the subentry flow
        return await self.async_step_user()

    # -------------------------
    # USER-INITIATED FLOW
    # -------------------------
    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Handle the initial step started by the user."""
        errors: dict[str, str] = {}
        if user_input is not None:
            port = user_input[CONF_SERIAL_PORT]
            try:
                # Quick, blocking sanity check that the port is reachable.
                serial_conn = serial.Serial(port)

                serial_conn.close()

                # Use the port path as the unique ID when set up manually.
                await self.async_set_unique_id(port, raise_on_progress=False)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Schellenberg USB ({port})", data=user_input
                )
            except serial.SerialException:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Failed to connect to serial port %s", port)
            except Exception:
                errors["base"] = "unknown"
                _LOGGER.exception("An unexpected error occurred")

        return self._form_schema(errors, default_port="/dev/ttyUSB0")

    # -------------------------
    # USB DISCOVERY FLOW
    # -------------------------
    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle discovery from the USB subsystem."""
        # Try to get the most stable unique identifier we can (serial number if present).
        unique = getattr(discovery_info, "serial_number", None) or (
            f"{getattr(discovery_info, 'vid', 'unknown')}:"
            f"{getattr(discovery_info, 'pid', 'unknown')}:"
            f"{getattr(discovery_info, 'device', 'unknown')}"
        )

        # Prefer the OS device path for the default value in the confirmation form.
        port = getattr(discovery_info, "device", None)
        manufacturer = getattr(discovery_info, "manufacturer", None) or "Schellenberg"
        description = getattr(discovery_info, "description", None) or "USB device"

        # Save for the confirm step
        self._discovered_port = port
        self._discovered_unique = unique
        self._discovered_title = f"{manufacturer} {description}".strip()

        # Deduplicate if already configured; update the stored port if it changed.
        await self.async_set_unique_id(unique, raise_on_progress=False)
        self._abort_if_unique_id_configured(
            updates={CONF_SERIAL_PORT: port} if port else None
        )

        # Ask for confirmation (and allow editing the port if the host maps it differently)
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Confirm USB-discovered device and create the entry."""
        errors: dict[str, str] = {}

        # If we don’t have a port path, let the user supply one.
        default_port = self._discovered_port or "/dev/ttyUSB0"

        if user_input is not None:
            port = user_input[CONF_SERIAL_PORT]
            try:
                serial_conn = serial.Serial(port)
                serial_conn.close()

                # unique_id was already set in async_step_usb(), re-assert and create the entry
                await self.async_set_unique_id(
                    self._discovered_unique, raise_on_progress=False
                )
                self._abort_if_unique_id_configured()

                title = self._discovered_title or f"Schellenberg USB ({port})"
                return self.async_create_entry(
                    title=title, data={CONF_SERIAL_PORT: port}
                )
            except serial.SerialException:
                errors["base"] = "cannot_connect"
                _LOGGER.error("Failed to connect to serial port %s", port)
            except Exception:
                errors["base"] = "unknown"
                _LOGGER.exception("An unexpected error occurred during USB confirm")

        # Mark as confirm-only so the UI shows a simple confirmation experience
        self._set_confirm_only()
        return self._form_schema(
            errors, default_port=default_port, step_id="usb_confirm"
        )

    # -------------------------
    # Helpers
    # -------------------------
    @callback
    def _form_schema(
        self, errors: dict[str, str], default_port: str, step_id: str = "user"
    ) -> ConfigFlowResult:
        """Return a form with a (prefilled) serial port field."""
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SERIAL_PORT, default=default_port
                    ): selector.TextSelector(),
                }
            ),
            errors=errors,
        )


class SchellenbergPairingSubentryFlow(ConfigSubentryFlow):
    """Flow for adding new blind devices as subentries."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the subentry flow."""
        super().__init__()
        self.calibration_handler: CalibrationFlowHandler | None = None
        self._pending_device_id: str | None = None
        self._pending_device_enum: str | None = None
        self._pending_device_name: str | None = None

    def _get_calibration_handler(self) -> CalibrationFlowHandler:
        """Return (and lazily create) the calibration flow handler."""
        if self.calibration_handler is None:
            self.calibration_handler = CalibrationFlowHandler(self)
        return self.calibration_handler

    async def _await_subentry_result(
        self,
        step_coro: Awaitable[ConfigFlowResult | SubentryFlowResult],
    ) -> SubentryFlowResult:
        """Await a calibration step and cast to SubentryFlowResult for mypy."""
        return cast(SubentryFlowResult, await step_coro)

    async def async_step_blind(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Entry point when the user clicks the 'Pair device' button.

        Shows a type selection form: "What do you want to add?"
        - Blind → runs active pairing (send commands, wait for motor)
        - Remote → passive listening (capture remote ID)
        """
        _LOGGER.debug("Subentry blind flow initiated (pairing new device)")

        if user_input is not None:
            device_type = user_input.get("device_type")
            if device_type == "blind":
                return await self.async_step_user()
            if device_type == "remote":
                return await self.async_step_learn_remote()

        return self.async_show_form(
            step_id="blind",
            data_schema=vol.Schema(
                {
                    vol.Required("device_type"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                ("blind", "Blind / Roller Shutter"),
                                ("remote", "Remote Control"),
                            ],
                        )
                    ),
                }
            ),
        )

    async def async_step_learn_remote(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Passively learn a remote by listening for its button press."""
        hub_entry = self._get_entry()
        api = hub_entry.runtime_data

        if user_input is not None:
            remote = await api.learn_remote_and_wait()
            if remote is None:
                return self.async_abort(reason="remote_learning_timeout")

            remote_id = remote["remote_id"]
            channel = remote["channel"]

            # Persist to entry.options
            updated_options = dict(hub_entry.options)
            remotes = list(updated_options.get(CONF_REMOTE_CONTROLS, []))
            # Avoid duplicates
            remotes = [
                r
                for r in remotes
                if not (r.get("remote_id") == remote_id and r.get("channel") == channel)
            ]
            remotes.append(
                {
                    "remote_name": user_input.get("remote_name")
                    or f"Remote {remote_id}",
                    "remote_id": remote_id,
                    "channel": channel,
                    "last_button": remote["button"],
                }
            )
            updated_options[CONF_REMOTE_CONTROLS] = remotes
            self.hass.config_entries.async_update_entry(
                hub_entry, options=updated_options
            )
            # Reload to create the event entity
            await self.hass.config_entries.async_reload(hub_entry.entry_id)
            return self.async_create_entry(
                title=f"Remote {remote_id}",
                data={},
            )

        return self.async_show_form(
            step_id="learn_remote",
            data_schema=vol.Schema(
                {
                    vol.Optional("remote_name"): selector.TextSelector(),
                }
            ),
            description_placeholders={
                "instruction": "Press any button on the physical remote within 30 seconds"
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Handle pairing initialization."""
        _LOGGER.debug("Pairing step user input: %s", user_input)
        if user_input is None:
            _LOGGER.info("Showing pairing form")
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

        # Get the hub entry (parent config entry)
        hub_entry = self._get_entry()
        api = hub_entry.runtime_data

        # Initiate pairing and wait for response (up to 10 seconds)
        pairing_result = await api.pair_device_and_wait()

        if pairing_result is None:
            # Pairing timeout
            return self.async_abort(reason="pairing_timeout")

        # Pairing successful! Store device_id and device_enum in context
        device_id, device_enum = pairing_result
        self._pending_device_id = device_id
        self._pending_device_enum = device_enum
        self._pending_device_name = None
        return await self.async_step_name_device()

    async def async_step_name_device(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Ask user to provide a friendly name for the paired device."""
        device_id = self._pending_device_id
        device_enum = self._pending_device_enum

        if user_input is None:
            # Initial call - show form
            if not device_id:
                return self.async_abort(reason="pairing_failed")

            return self.async_show_form(
                step_id="name_device",
                data_schema=vol.Schema(
                    {
                        vol.Optional("device_name"): selector.TextSelector(),
                    }
                ),
                description_placeholders={
                    "device_id": device_id,
                },
            )

        # User provided a name – begin calibration prior to creating subentry
        if not device_id or not device_enum:
            return self.async_abort(reason="pairing_failed")

        device_name = user_input.get("device_name") or f"Blind {device_id}"
        self._pending_device_name = device_name

        handler = self._get_calibration_handler()

        # Provide minimal device to handler
        handler.set_selected_device(
            {
                "id": device_id,
                "name": device_name,
                "enum": device_enum,
            }
        )
        handler.enable_subentry_creation(
            device_id=device_id,
            device_enum=device_enum,
            device_name=device_name,
        )
        _LOGGER.debug(
            "Starting calibration for paired device %s (%s) before creating subentry",
            device_id,
            device_name,
        )
        return await self._await_subentry_result(
            handler.async_step_calibration_close(None)
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Configure a blind: run calibration for the single device under this subentry.

        We bypass storage lookup and set the calibration handler's selected device
        directly from the subentry data to avoid device_not_found errors before
        calibration has ever run.
        """
        handler = self._get_calibration_handler()
        handler.disable_subentry_creation()

        subentry = self._get_reconfigure_subentry()
        device_id = subentry.data.get("device_id")
        device_enum = subentry.data.get("device_enum")
        if not device_id:
            return self.async_abort(reason="device_not_found")

        # Build a minimal device record; calibration handler will enrich after timing
        device_name = subentry.title or f"Blind {device_id}"
        handler.set_selected_device(
            {
                "id": device_id,
                "name": device_name,
                CONF_OPEN_TIME: subentry.data.get(CONF_OPEN_TIME),
                CONF_CLOSE_TIME: subentry.data.get(CONF_CLOSE_TIME),
                "enum": device_enum,
            }
        )

        return await self._await_subentry_result(
            handler.async_step_calibration_close(user_input)
        )

    # Delegate all calibration steps to the handler
    async def async_step_calibration_close(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Delegate to calibration handler."""
        handler = self._get_calibration_handler()
        return await self._await_subentry_result(
            handler.async_step_calibration_close(user_input)
        )

    async def async_step_calibration_open_instruction(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Delegate to calibration handler."""
        handler = self._get_calibration_handler()
        return await self._await_subentry_result(
            handler.async_step_calibration_open_instruction(user_input)
        )

    async def async_step_calibration_close_instruction(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Delegate to calibration handler."""
        handler = self._get_calibration_handler()
        return await self._await_subentry_result(
            handler.async_step_calibration_close_instruction(user_input)
        )

    async def async_step_calibration_complete(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Delegate to calibration handler (handler now creates entry)."""
        handler = self._get_calibration_handler()
        return await self._await_subentry_result(
            handler.async_step_calibration_complete(user_input)
        )


class SchellenbergWindowSensorSubentryFlow(ConfigSubentryFlow):
    """Flow for adding a window handle sensor and binding it to a blind."""

    VERSION = 1
    _bind_blind_id: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 1: Show form to select which blind this sensor belongs to."""
        hub_entry = self._get_entry()

        # Build a list of existing blinds
        blind_options: list[tuple[str, str]] = []
        for subentry in hub_entry.subentries.values():
            device_id = subentry.data.get("device_id", "")
            device_name = subentry.title or f"Blind {device_id}"
            if device_id and subentry.subentry_type == SUBENTRY_TYPE_BLIND:
                blind_options.append((device_id, device_name))

        if not blind_options:
            return self.async_abort(reason="no_blinds")

        if user_input is not None:
            self._bind_blind_id = user_input["blind_device_id"]
            return await self.async_step_listen()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("blind_device_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=blind_options,
                        ),
                    ),
                }
            ),
        )

    async def async_step_listen(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Step 2: Listen for a window sensor signal."""
        hub_entry = self._get_entry()
        api: SchellenbergUsbApi = hub_entry.runtime_data
        sensor_device_id: str | None = None

        if user_input is not None:
            future: asyncio.Future[dict[str, str]] = (
                hub_entry.runtime_data.hass.loop.create_future()
            )

            # Listen on the bus event that api.py fires for window sensors.
            # Filter by type="window_sensor" to avoid capturing remote button presses.
            bus_unsub = api.hass.bus.async_listen(
                f"{DOMAIN}_remote_button_pressed",
                lambda event: (
                    future.set_result(
                        {
                            "device_id": event.data.get("remote_id", ""),
                            "state": event.data.get("button", ""),
                        }
                    )
                    if not future.done()
                    and event.data.get("type") == "window_sensor"
                    else None
                ),
            )

            try:
                result = await asyncio.wait_for(future, timeout=60)
                sensor_device_id = result.get("device_id", "")
                if not sensor_device_id:
                    return self.async_abort(reason="window_sensor_timeout")
            except TimeoutError:
                return self.async_abort(reason="window_sensor_timeout")
            finally:
                if bus_unsub:
                    bus_unsub()

            return await self.async_step_confirm(sensor_device_id)

        return self.async_show_form(
            step_id="listen",
            data_schema=vol.Schema({}),
            description_placeholders={
                "instruction": "Press any button on the window handle so the stick can detect it. You have 60 seconds."
            },
        )

    async def async_step_confirm(
        self, sensor_device_id: str | None = None,
        user_input: dict[str, Any] | None = None,
    ) -> SubentryFlowResult:
        """Step 3: Confirm and create the subentry."""
        if sensor_device_id is None:
            return self.async_abort(reason="window_sensor_timeout")

        if user_input is not None:
            device_name = user_input.get("name") or f"Window Sensor {sensor_device_id}"
            return self.async_create_entry(
                title=device_name,
                data={
                    "device_id": sensor_device_id,
                    "bound_blind_id": self._bind_blind_id,
                    "type": "window_sensor",
                },
            )

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema(
                {
                    vol.Optional("name"): selector.TextSelector(),
                }
            ),
            description_placeholders={
                "device_id": sensor_device_id,
                "blind_id": self._bind_blind_id or "unknown",
            },
        )
