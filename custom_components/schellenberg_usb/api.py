"""API for Schellenberg USB Stick.

Credits / Sources:
- https://github.com/Hypfer/schellenberg-qivicon-usb (Protocol reverse engineering)
- https://github.com/LoPablo/schellenberg-qivicon-usb (Extended packet analysis)
- https://github.com/GimpArm/schellenberg_usb (Original Home Assistant integration)
- https://github.com/moTo31/schellenberg-mqtt (MQTT daemon, command structure)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

import serial_asyncio
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.components import persistent_notification

from .const import (
    CMD_ALLOW_PAIRING,
    CMD_DOWN,
    CMD_ECHO_OFF,
    CMD_ECHO_ON,
    CMD_ENTER_BOOTLOADER,
    CMD_ENTER_INITIAL,
    CMD_GET_DEVICE_ID,
    CMD_GET_PARAM_P,
    CMD_LED_BLINK_1,
    CMD_LED_BLINK_2,
    CMD_LED_BLINK_3,
    CMD_LED_BLINK_4,
    CMD_LED_BLINK_5,
    CMD_LED_BLINK_6,
    CMD_LED_BLINK_7,
    CMD_LED_BLINK_8,
    CMD_LED_BLINK_9,
    CMD_LED_OFF,
    CMD_LED_ON,
    CMD_MANUAL_DOWN,
    CMD_MANUAL_UP,
    CMD_PAIR,
    CMD_REBOOT,
    CMD_SET_LOWER_ENDPOINT,
    CMD_SET_UPPER_ENDPOINT,
    CMD_STOP,
    CMD_TRANSMIT,
    CMD_UP,
    CMD_VERIFY,
    PAIRING_DEVICE_ENUM_START,
    PAIRING_TIMEOUT,
    EVENT_REMOTE_BUTTON_PRESSED,
    GROUP_CHANNEL_ALL,
    SIGNAL_DEVICE_EVENT,
    SIGNAL_RSSI_UPDATED,
    SIGNAL_STICK_STATUS_UPDATED,
    SIGNAL_REMOTE_EVENT,
    SIGNAL_WINDOW_SENSOR,
    SENSOR_WINDOW_HANDLE_0,
    SENSOR_WINDOW_HANDLE_90,
    SENSOR_WINDOW_HANDLE_180,
    VERIFY_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)


class SchellenbergUsbApi:
    """Manages all communication with the Schellenberg USB stick."""

    def __init__(self, hass: HomeAssistant, port: str) -> None:
        """Initialize the Schellenberg USB API."""
        self.hass = hass
        self.port = port
        self._transport: asyncio.Transport | None = None
        self._protocol: SchellenbergProtocol | None = None
        self._registered_devices: dict[
            str, str
        ] = {}  # Dict: device_id -> device_enum for registered blind entities
        self._registered_remotes: dict[
            str, dict[str, str]
        ] = {}  # Dict: remote_id -> {channel: ...} for registered remotes
        self._is_connecting = False
        self._pairing_future: asyncio.Future[str] | None = None
        self._remote_learning_future: asyncio.Future[dict[str, str]] | None = None
        self._stop_pairing_task: asyncio.Task[None] | None = (
            None  # Track task to stop pairing
        )

        # USB stick status
        self._is_connected = False
        self._device_version: str | None = None
        self._device_mode: str | None = None  # boot, initial, or listening
        self._verify_future: asyncio.Future[bool] | None = None
        self._device_id_future: asyncio.Future[str] | None = None
        self._hub_id: str | None = None

        # Retry queue for commands that failed with "stick busy"
        self._pending_retry_command: str | None = None
        self._retry_task: asyncio.Task[None] | None = None

        # RSSI (signal strength) tracking per device
        self._device_rssi: dict[str, int] = {}

        # Auto-discovery: track devices we've already notified about
        self._discovered_devices: set[str] = set()

        # Safety lock: prevent DOWN commands per device_id when locked
        # True = DOWN blocked, False = unrestricted
        self._blind_locks: dict[str, bool] = {}

        # Reconnection management
        self._reconnect_task: asyncio.Task[None] | None = None
        # Flag to distinguish intentional disconnect from unexpected connection loss
        self._disconnecting = False

    @staticmethod
    def _command_to_button(command: str) -> str | None:
        """Translate a Schellenberg command byte to a human‑readable button name.

        The USB stick reports blind motor actions as two‑character hex command codes.
        Home Assistant only needs to know the semantic button (up/down/stop) for
        remote learning and UI display, so this helper maps the known command bytes
        to their corresponding button labels. Unknown commands return ``None``.
        """
        return {
            CMD_UP: "up",
            CMD_DOWN: "down",
            CMD_STOP: "stop",
            CMD_MANUAL_UP: "up",
            CMD_MANUAL_DOWN: "down",
        }.get(command)

    @staticmethod
    def _normalize_channel(device_enum: str) -> str:
        """Normalize the channel portion of a device enum.

        The Schellenberg protocol encodes the channel as a two‑character hex byte.
        For user‑friendly logging and UI we convert a valid channel (1‑5) to its
        decimal string representation while leaving other values untouched.
        """
        try:
            channel = int(device_enum, 16)
        except ValueError:
            return device_enum
        if 1 <= channel <= 5:
            return str(channel)
        return device_enum

    @staticmethod
    def _command_to_window_state(command: str) -> str | None:
        """Map a command byte to a window handle sensor state.

        Window handle sensors (Device Enumerator 0x14) report their
        position using specific command bytes. Returns a human-readable
        state string or None if the command is not a window sensor event.
        """
        return {
            SENSOR_WINDOW_HANDLE_0: "closed",
            SENSOR_WINDOW_HANDLE_90: "tilted",
            SENSOR_WINDOW_HANDLE_180: "open",
        }.get(command)

    async def connect(self) -> None:
        """Establish a connection to the serial port.

        This method ensures _is_connecting is always reset on every exit
        path (success, verify-failure, or exception) to prevent the API
        from getting stuck in a permanent "connecting" state.
        """
        if self._is_connecting or (
            self._transport and not self._transport.is_closing()
        ):
            _LOGGER.debug("Connection attempt already in progress or established")
            return

        self._is_connecting = True
        _LOGGER.info("Connecting to Schellenberg USB stick at %s", self.port)

        transport: asyncio.Transport | None = None
        protocol: SchellenbergProtocol | None = None

        try:
            transport, protocol = await serial_asyncio.create_serial_connection(
                self.hass.loop,
                lambda: SchellenbergProtocol(self._handle_message, self),
                self.port,
                baudrate=112500,
            )
            self._transport = transport
            self._protocol = protocol
            self._is_connecting = False
            _LOGGER.info("Successfully connected to Schellenberg USB stick")

            # Verify this is a Schellenberg device
            if not await self.verify_device():
                _LOGGER.error(
                    "Device verification failed - not a Schellenberg USB stick"
                )
                if self._transport:
                    self._transport.close()
                self._transport = None
                self._protocol = None
                self._is_connected = False
                self._is_connecting = False
                self._update_status()
                return

            self._is_connected = True
            self._update_status()

            # Enter listening mode if not already in it
            if self._device_mode != "listening":
                _LOGGER.info(
                    "Device is in %s mode, entering listening mode", self._device_mode
                )
                await self.send_command("hello")
                await asyncio.sleep(0.5)
                self._device_mode = "listening"
                self._update_status()
                _LOGGER.info("Device now in listening mode")
            else:
                _LOGGER.info("Device already in listening mode")

            # Get the hub device ID after listening mode
            hub_id = await self.get_device_id()
            if hub_id:
                self._hub_id = hub_id
                _LOGGER.info("Hub device ID retrieved: %s", self._hub_id)
            else:
                _LOGGER.warning("Failed to retrieve hub device ID")
        except (serial_asyncio.serial.SerialException, OSError) as err:
            _LOGGER.error(
                "Failed to connect to %s: %s", self.port, err,
            )
            if transport:
                transport.close()
            self._transport = None
            self._protocol = None
            self._is_connected = False
        except Exception:
            _LOGGER.exception("Unexpected error connecting to %s", self.port)
            if transport:
                transport.close()
            self._transport = None
            self._protocol = None
            self._is_connected = False
            raise  # Re-raise so HA gets ConfigEntryNotReady
        finally:
            self._is_connecting = False  # Always reset in ALL paths

    @callback
    def _handle_message(self, message: str) -> None:
        """Handle incoming messages from the protocol.

        This method parses raw strings received from the USB stick and dispatches
        them to the appropriate handlers (pairing, remote learning, or device events).
        """
        _LOGGER.debug("Received raw message: %s", message)

        # Handle device verification response (format: RFTU_V20 F:20180510_DFBD B:1)
        # RFTU_V20 = device type and version
        # F: = firmware date
        # B: = boot mode (0 = bootloader, 1 = initial/normal)
        # Note: Listening mode (B:2) is entered by sending a lowercase command in B:1
        if message.startswith("RFTU_"):
            parts = message.split()
            if parts:
                self._device_version = parts[0]  # RFTU_V20
                # Extract boot mode if present
                for part in parts:
                    if part.startswith("B:"):
                        boot_mode = part[2:]
                        if boot_mode == "0":
                            self._device_mode = "bootloader"
                        elif boot_mode == "1":
                            self._device_mode = "initial"
                        else:
                            self._device_mode = "unknown"
                        break
                else:
                    self._device_mode = "initial"

                _LOGGER.info(
                    "Device verified: version=%s, mode=%s",
                    self._device_version,
                    self._device_mode,
                )
                if self._verify_future and not self._verify_future.done():
                    self._verify_future.set_result(True)
                self._update_status()
            return

        # Handle acknowledgments
        if message in ("t1", "t0"):
            _LOGGER.debug("Transmit ACK: %s", message)
            return

        if message == "tE":
            _LOGGER.warning("Transmit error - stick busy, starting retry with exponential backoff")
            # The USB stick returns tE when still processing the previous command.
            # _retry_command_after_delay uses exponential backoff (100ms→200ms→400ms→800ms)
            # and up to 4 retry attempts before giving up.
            if self._pending_retry_command:
                if self._retry_task and not self._retry_task.done():
                    self._retry_task.cancel()
                self._retry_task = asyncio.create_task(
                    self._retry_command_after_delay()
                )
            return

        # Handle device ID response (format: sr5D3E7C where 5D3E7C is the device ID)
        if message.startswith("sr") and len(message) >= 8:
            device_id = message[2:8]
            _LOGGER.debug("Received device ID response: %s", device_id)
            if self._device_id_future and not self._device_id_future.done():
                self._device_id_future.set_result(device_id)
            return

        # Handle pairing/list responses (format: sl00BEXXXXXX...)
        # sl = list/pairing response prefix
        # 00BE = 2 bytes to ignore (address prefix)
        # XXXXXX = 3 bytes device ID (the actual device ID we want)
        # Rest = can be ignored
        if message.startswith("sl") and len(message) >= 8:
            # Extract the device ID: skip "sl" (2 chars) + "00BE" (4 chars) = 6 chars
            # Then take the next 6 characters (3 bytes as hex) = 6 chars
            # This format is specific to pairing responses from the stick.
            device_id = message[6:12]
            _LOGGER.debug(
                "Received pairing/list response: %s, extracted device ID: %s",
                message,
                device_id,
            )
            _LOGGER.debug(
                "Pairing mode active: %s",
                self._pairing_future is not None and not self._pairing_future.done(),
            )

            # If we're in pairing mode, accept ANY device response
            # because the user is explicitly trying to pair RIGHT NOW
            if self._pairing_future and not self._pairing_future.done():
                _LOGGER.info("Pairing successful! New device ID: %s", device_id)
                self._pairing_future.set_result(device_id)
                # Stop pairing mode after a 2 second delay to ensure device has fully paired
                self._stop_pairing_task = asyncio.create_task(
                    self._stop_pairing_mode(delay=True)
                )
                self._stop_pairing_task.add_done_callback(
                    lambda _: setattr(self, "_stop_pairing_task", None)
                )
                # Don't send dispatcher signal here - let the caller handle persistence
                return
            return

        # Handle Schellenberg device messages
        # Format: ssXXYYYYYYZZZZCCPPRR
        # ss = prefix (2 chars)
        # XX = device enum (2 chars)
        # YYYYYY = device ID (6 chars)
        # ZZZZ = message incrementor (4 chars, ignored)
        # CC = command (2 chars)
        # PP = padding (2 chars, ignored)
        # RR = signal strength (2 chars, ignored)
        if message.startswith("ss") and len(message) >= 18:
            try:
                # Schellenberg protocol message format:
                # ss [2] - Prefix
                # XX [2] - Device Enumerator (channel/ID mapped by stick)
                # YYYYYY [6] - Unique Device ID
                # ZZZZ [4] - Message counter / rolling code (ignored here)
                # CC [2] - Command/Status code
                # PP [2] - Padding/Signal strength info
                # RR [2] - Signal strength (RSSI)
                device_enum = message[2:4]
                device_id = message[4:10]
                # Skip message incrementor at positions 10:14
                command = message[14:16]
                button = self._command_to_button(command)

                # Parse RSSI (signal strength) if available at positions 16:18
                if len(message) >= 18:
                    try:
                        rssi_raw = message[16:18]
                        rssi = int(rssi_raw, 16)
                        # Store and dispatch if changed
                        if self._device_rssi.get(device_id) != rssi:
                            self._device_rssi[device_id] = rssi
                            async_dispatcher_send(
                                self.hass,
                                f"{SIGNAL_RSSI_UPDATED}_{device_id}",
                                rssi,
                            )
                    except (ValueError, IndexError):
                        pass  # Incomplete or corrupted RSSI bytes

                # Check if this is a window handle sensor message
                window_state = self._command_to_window_state(command)
                if window_state is not None:
                    _LOGGER.debug(
                        "Window sensor %s (enum=%s) state: %s",
                        device_id, device_enum, window_state,
                    )
                    async_dispatcher_send(
                        self.hass,
                        f"{SIGNAL_WINDOW_SENSOR}_{device_id}",
                        window_state,
                        command,
                    )
                    # Fire bus event for config flow listener
                    self.hass.bus.async_fire(
                        f"{EVENT_REMOTE_BUTTON_PRESSED}",
                        {
                            "remote_id": device_id,
                            "channel": self._normalize_channel(device_enum),
                            "button": window_state,
                            "command": command,
                            "type": "window_sensor",
                        },
                    )
                    # Auto-discovery for new window sensors
                    if device_id not in self._discovered_devices:
                        self._discovered_devices.add(device_id)
                        persistent_notification.async_create(
                            self.hass,
                            (
                                f"A Schellenberg window handle sensor was detected: "
                                f"**{device_id}** (state: {window_state}).\n\n"
                                "Go to **Settings > Devices & Services > Schellenberg USB** "
                                "to add it permanently."
                            ),
                            title="Schellenberg Window Sensor Detected",
                            notification_id=f"{DOMAIN}_window_{device_id}",
                        )
                    return  # Don't process as blind command

                _LOGGER.debug(
                    "Parsed: enum=%s, id=%s, cmd=%s", device_enum, device_id, command
                )

                # If we're in pairing mode and this is a new device
                if self._pairing_future and not self._pairing_future.done():
                    if device_id not in self._registered_devices:
                        _LOGGER.info("Pairing successful! New device ID: %s", device_id)
                        self._pairing_future.set_result(device_id)
                        # Stop pairing mode after a 2 second delay to ensure device has fully paired
                        self._stop_pairing_task = asyncio.create_task(
                            self._stop_pairing_mode(delay=True)
                        )
                        self._stop_pairing_task.add_done_callback(
                            lambda _: setattr(self, "_stop_pairing_task", None)
                        )
                        # Don't send dispatcher signal here - let the caller handle persistence
                        return

                is_registered_device = device_id in self._registered_devices
                is_learning_remote = (
                    self._remote_learning_future is not None
                    and not self._remote_learning_future.done()
                )

                if button is not None and (
                    not is_registered_device or is_learning_remote
                ):
                    # Handle messages from remotes (either new discovery or learning mode)
                    self._handle_remote_message(
                        remote_id=device_id,
                        channel=self._normalize_channel(device_enum),
                        button=button,
                        command=command,
                        raw_message=message,
                    )

                # If this is the first time we see this device (auto-discovery mode)
                if not is_registered_device:
                    _LOGGER.warning(
                        "Received message for device %s (enum=%s, cmd=%s) but no "
                        "corresponding entity found. The device may need to be added "
                        "to Home Assistant",
                        device_id,
                        device_enum,
                        command,
                    )
                    # Auto-discovery: notify once per unknown device
                    if device_id not in self._discovered_devices:
                        self._discovered_devices.add(device_id)
                        persistent_notification.async_create(
                            self.hass,
                            (
                                f"A new Schellenberg device was detected: **{device_id}** "
                                f"(channel {self._normalize_channel(device_enum)}).\n\n"
                                "Go to **Settings > Devices & Services > Schellenberg USB** "
                                "and use the **Pair device** service to add it to Home Assistant."
                            ),
                            title="New Schellenberg Device Detected",
                            notification_id=f"{DOMAIN}_discovery_{device_id}",
                        )
                else:
                    # The entity will handle the event via the dispatcher
                    _LOGGER.debug(
                        "Forwarding event to device %s (enum=%s): command=%s",
                        device_id,
                        device_enum,
                        command,
                    )

                # Forward the event to the correct entity (if it exists)
                async_dispatcher_send(
                    self.hass, f"{SIGNAL_DEVICE_EVENT}_{device_id}", command
                )
            except (IndexError, ValueError) as err:
                _LOGGER.debug("Failed to parse message %s: %s", message, err)

    @callback
    def _handle_remote_message(
        self,
        remote_id: str,
        channel: str,
        button: str,
        command: str,
        raw_message: str,
    ) -> None:
        """Handle a physical Schellenberg remote button frame.

        This method is called when the message parser detects a button press
        from a device that is either an unknown remote or during remote learning
        mode. It performs three actions:

        1. If remote learning is active (`_remote_learning_future` exists),
           resolves the future so `learn_remote_and_wait()` can return the data.
        2. Fires a bus event (`schellenberg_usb_remote_button_pressed`) for
           automations that use the raw event trigger.
        3. If the remote is already registered, sends a dispatcher signal
           (`SIGNAL_REMOTE_EVENT_{remote_id}`) to the corresponding EventEntity.

        Args:
            remote_id: 6-character hex ID of the remote.
            channel: Normalized channel string (e.g. "1", "2", ..., "5").
            button: Semantic button name ("up", "down", "stop").
            command: Raw hex command byte from the protocol.
            raw_message: The original unparsed message string for debugging.
        """
        event_data = {
            "remote_id": remote_id,
            "channel": channel,
            "button": button,
            "command": command,
            "raw": raw_message,
        }

        if self._remote_learning_future and not self._remote_learning_future.done():
            self._remote_learning_future.set_result(event_data)

        _LOGGER.info(
            "Remote button received: remote=%s channel=%s button=%s",
            remote_id,
            channel,
            button,
        )
        self.hass.bus.async_fire(EVENT_REMOTE_BUTTON_PRESSED, event_data)

        # Forward to the specific remote entity via dispatcher
        if remote_id in self._registered_remotes:
            async_dispatcher_send(
                self.hass,
                f"{SIGNAL_REMOTE_EVENT}_{remote_id}",
                button,
                command,
            )
        else:
            _LOGGER.debug(
                "Remote ID %s is not registered; no entity to forward to.",
                remote_id,
            )

    async def send_command(self, command: str, retries: int = 0) -> None:
        """Send a raw command to the USB stick with optional retry logic.

        Appends the required CRLF and encodes to ASCII. If the USB stick
        responds with tE (transmit error/busy), the command is automatically
        retried up to ``retries`` times with exponential backoff (100ms,
        200ms, 400ms, ...). Retries only happen when we can confirm the
        transport is still connected.

        Args:
            command: The raw command string (without CRLF).
            retries: Number of additional retry attempts on tE.
                     Default 0 = fire-and-forget (no retry).

        """
        if self._transport is None or self._transport.is_closing():
            _LOGGER.warning("Serial port not connected. Command dropped: %s", command)
            return

        # Store for potential retry on "stick busy"
        self._pending_retry_command = command

        full_command = f"{command}\r\n".encode("ascii")
        _LOGGER.debug("Sending to serial device: %s", full_command.strip())
        self._transport.write(full_command)
        _LOGGER.debug("Command sent to serial device: %s", full_command.strip())

    async def _retry_command_after_delay(self) -> None:
        """Retry sending the pending command after exponential backoff.

        The USB stick returns tE when it is still busy processing the
        previous command (e.g. between t1 and t0). We retry with
        increasing delays: 100ms, 200ms, 400ms, 800ms (max 4 retries).
        """
        max_retries = 4
        delay = 0.1  # 100ms initial
        try:
            for attempt in range(max_retries):
                try:
                    await asyncio.sleep(delay)
                    if self._transport is None or self._transport.is_closing():
                        _LOGGER.debug("Transport closed during retry; giving up.")
                        return
                    command = self._pending_retry_command
                    if command is None:
                        return  # Nothing to retry
                    _LOGGER.debug(
                        "Retry attempt %d/%d for command: %s",
                        attempt + 1, max_retries, command,
                    )
                    full_command = f"{command}\r\n".encode("ascii")
                    self._transport.write(full_command)

                    # If we don't get another tE, we're done
                    # The next tE will trigger a new retry task
                    delay = min(delay * 2, 0.8)  # Exponential backoff, max 800ms
                except asyncio.CancelledError:
                    _LOGGER.debug("Retry cancelled")
                    return
                except Exception as err:
                    _LOGGER.warning("Retry attempt %d failed: %s", attempt + 1, err)
                    return
            else:
                _LOGGER.warning(
                    "Command %s failed after %d retries",
                    self._pending_retry_command,
                    max_retries,
                )
        finally:
            self._retry_task = None

    async def pair_device_and_wait(self) -> tuple[str, str] | None:
        """Put the stick into pairing mode and wait for a device to pair.

        Per the reverse-engineered protocol (Hypfer/LoPablo), the correct
        pairing procedure is:
          1. Send CMD_PAIR (0x60)  → motor beeps/rattles
          2. Send CMD_ALLOW_PAIRING (0x40) → motor beeps/rattles again → paired

        Returns a tuple of (device_id, device_enum) if successful, None if timeout.
        """
        if self._pairing_future and not self._pairing_future.done():
            _LOGGER.warning("Pairing already in progress")
            return None

        # Get the next available device enumerator
        device_enum = self.initialize_next_device_enum()

        # Build both pairing commands per protocol spec
        pair_cmd_60 = f"{CMD_TRANSMIT}{device_enum}9{CMD_PAIR}0000"          # 0x60 first
        pair_cmd_40 = f"{CMD_TRANSMIT}{device_enum}9{CMD_ALLOW_PAIRING}0000"  # 0x40 second

        _LOGGER.info(
            "Initiating pairing with device enum %s. Commands: %s then %s",
            device_enum,
            pair_cmd_60,
            pair_cmd_40,
        )

        # Create a future to wait for device ID first
        self._pairing_future = self.hass.loop.create_future()

        try:
            # Send sp command to enter pairing/listening mode
            _LOGGER.debug("Entering pairing mode with command: sp")
            await self.send_command(CMD_GET_PARAM_P)

            # Wait for device to send its ID first (with timeout)
            device_id = await asyncio.wait_for(
                self._pairing_future, timeout=PAIRING_TIMEOUT
            )

            # Step 1: Send CMD_PAIR (0x60)
            _LOGGER.debug(
                "Received device ID %s, sending pair command (0x60): %s",
                device_id,
                pair_cmd_60,
            )
            await self.send_command(pair_cmd_60)

            # Short delay per protocol recommendation
            await asyncio.sleep(0.1)

            # Step 2: Send CMD_ALLOW_PAIRING (0x40) to finalise
            _LOGGER.debug(
                "Sending allow pairing command (0x40): %s",
                pair_cmd_40,
            )
            await self.send_command(pair_cmd_40)
        except TimeoutError:
            _LOGGER.warning("Pairing timeout - no device responded with ID")
            return None
        else:
            # Pairing successful - return the device ID and enum
            _LOGGER.info(
                "Pairing completed successfully: %s with device enum %s",
                device_id,
                device_enum,
            )
            return (device_id, device_enum)
        finally:
            self._pairing_future = None

    async def _stop_pairing_mode(self, delay: bool = False) -> None:
        """Stop pairing mode by sending a stop command to the stick.

        Args:
            delay: If True, wait 2 seconds before stopping to ensure device has fully paired.
        """
        try:
            if delay:
                # Wait 2 seconds before stopping pairing mode to ensure device has fully paired
                await asyncio.sleep(2)
            _LOGGER.debug("Stopping pairing mode with command: sp")
            await self.send_command(CMD_GET_PARAM_P)
            _LOGGER.info("Pairing mode stopped")
        except OSError as err:
            _LOGGER.debug("Error stopping pairing mode (communication error): %s", err)

    async def control_blind(
        self, device_enum: str, action: str, device_id: str | None = None
    ) -> None:
        """Send a control command to a specific blind.

        Args:
            device_enum: The device enumerator (hex string like "10")
            action: Command (CMD_UP, CMD_DOWN, CMD_STOP)
            device_id: Optional device ID for safety lock check.
                       If provided and the blind is locked, CMD_DOWN is blocked.

        """
        if action not in (CMD_UP, CMD_DOWN, CMD_STOP):
            _LOGGER.error("Invalid blind action: %s", action)
            return

        # Safety lock: block DOWN commands when the blind is locked
        if action == CMD_DOWN and device_id and self._blind_locks.get(device_id, False):
            _LOGGER.warning(
                "Blind %s (enum=%s) is LOCKED. DOWN command blocked by safety lock.",
                device_id,
                device_enum,
            )
            return

        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{action}0000"
        _LOGGER.debug("Sending blind control: %s", command)
        await self.send_command(command)

    def set_blind_lock(self, device_id: str, locked: bool) -> None:
        """Set the safety lock state for a specific blind.

        When locked, all CMD_DOWN (close) commands for this blind will be
        blocked with a warning log. CMD_UP (open) and CMD_STOP (stop) are
        always allowed for safety reasons.

        This can be called from HA automations (e.g., via a door contact
        sensor) to prevent blinds from closing when a window/door is open.

        Args:
            device_id: The 6-character hex device ID to lock/unlock.
            locked: True to block DOWN commands, False to allow them.

        """
        self._blind_locks[device_id] = locked
        _LOGGER.info(
            "Safety lock for blind %s is now %s",
            device_id,
            "LOCKED (DOWN blocked)" if locked else "UNLOCKED",
        )

    async def control_native_group(
        self, action: str, group_id: str | None = None
    ) -> None:
        """Send a native Schellenberg group/broadcast command.

        The 5-channel remotes use their fifth/all channel for simultaneous group
        operation. The USB stick exposes the same radio transmit shape as single
        devices, so we address the configured virtual group enum directly.

        Args:
            action: Command to send (CMD_UP, CMD_DOWN, CMD_STOP)
            group_id: Hex ID of the group. Defaults to '05' (all channels on standard remote).
        """
        if action not in (CMD_UP, CMD_DOWN, CMD_STOP):
            _LOGGER.error("Invalid group action: %s", action)
            return

        group_enum = (group_id or GROUP_CHANNEL_ALL).strip().upper()
        if group_enum.isdigit():
            group_enum = f"{int(group_enum):02X}"
        try:
            int(group_enum, 16)
        except ValueError:
            _LOGGER.error("Invalid group id %s. Expected hex characters", group_id)
            return
        if len(group_enum) != 2:
            _LOGGER.error("Invalid group id %s. Expected 2 hex characters", group_id)
            return

        command = f"{CMD_TRANSMIT}{group_enum}9{action}0000"
        _LOGGER.debug("Sending native group control: %s", command)
        await self.send_command(command)

    async def learn_remote_and_wait(
        self, timeout: float = 30
    ) -> dict[str, str] | None:
        """Wait for the next physical remote button press and return its details.

        This is used for the remote learning feature in the UI. It creates a future
        that is resolved when a button press is detected in _handle_remote_message.
        """
        if self._remote_learning_future and not self._remote_learning_future.done():
            _LOGGER.warning("Remote learning already in progress")
            return None

        self._remote_learning_future = self.hass.loop.create_future()
        try:
            _LOGGER.info("Waiting for Schellenberg remote button press")
            return await asyncio.wait_for(self._remote_learning_future, timeout=timeout)
        except TimeoutError:
            _LOGGER.warning("Remote learning timeout - no remote button received")
            return None
        finally:
            self._remote_learning_future = None

    def initialize_next_device_enum(self) -> str:
        """Get the next available device enum based on registered devices.

        Returns the next available device enumerator as a hex string (e.g., "10").

        This is a stateless method that computes the next available enum
        by finding the highest enum in registered devices and returning one higher.
        """
        if not self._registered_devices:
            _LOGGER.debug(
                "No registered devices found, starting enum at %s",
                f"{PAIRING_DEVICE_ENUM_START:02X}",
            )
            return f"{PAIRING_DEVICE_ENUM_START:02X}"

        # Find the highest enum value from registered devices
        max_enum = PAIRING_DEVICE_ENUM_START - 1
        for device_enum in self._registered_devices.values():
            try:
                enum_value = int(device_enum, 16)
                max_enum = max(max_enum, enum_value)
            except (ValueError, TypeError) as err:
                _LOGGER.warning("Invalid enum value for device: %s", err)

        # Next enum is 1 higher than the highest
        next_enum = max_enum + 1
        if next_enum > 0xFF:
            next_enum = PAIRING_DEVICE_ENUM_START
            _LOGGER.warning(
                "Next enum exceeded 0xFF, wrapping back to %s",
                f"{PAIRING_DEVICE_ENUM_START:02X}",
            )

        result = f"{next_enum:02X}"
        _LOGGER.debug(
            "Computed next device enum as %s (highest existing: %s)",
            result,
            f"{max_enum:02X}",
        )
        return result

    def register_existing_devices(self, devices: list[dict]) -> None:
        """Register existing devices from storage.

        Args:
            devices: List of device dicts with 'id' and 'enum' keys
        """
        for device in devices:
            device_id = device.get("id")
            device_enum = device.get("enum")
            if device_id and device_enum:
                self._registered_devices[device_id] = device_enum
                _LOGGER.debug(
                    "Registered existing device %s with enum %s", device_id, device_enum
                )

    def register_existing_remotes(self, remotes: list[dict]) -> None:
        """Register known remotes (persisted from config storage).

        Args:
            remotes: List of remote config dicts with 'remote_id' and 'channel' keys.
        """
        for remote in remotes:
            remote_id = remote.get("remote_id")
            channel = remote.get("channel")
            if remote_id and channel is not None:
                self._registered_remotes[remote_id] = {"channel": channel}
                _LOGGER.debug(
                    "Registered known remote %s on channel %s", remote_id, channel
                )

    def register_remote(self, remote_id: str, channel: str) -> None:
        """Register a remote entity & persist its ID.

        Args:
            remote_id: The 6-character hex ID of the Schellenberg remote.
            channel: The remote channel (e.g. "1" to "5").

        Once registered, future button presses will be forwarded to
        the matching entities.
        """
        self._registered_remotes[remote_id] = {"channel": channel}
        _LOGGER.info(
            "Registered remote %s on channel %s", remote_id, channel
        )

    def is_remote_known(self, remote_id: str) -> bool:
        """Check if a remote ID has been registered.

        Args:
            remote_id: The 6-character hex ID of the Schellenberg remote.

        Returns:
            True if a remote with this ID exists in the registered set.

        """
        return remote_id in self._registered_remotes

    def get_device_rssi(self, device_id: str) -> int | None:
        """Return the last known RSSI for a device.

        Args:
            device_id: 6-character hex device ID.

        Returns:
            RSSI raw value (0-255) or None if no signal received yet.

        """
        return self._device_rssi.get(device_id)

    def remove_known_device(self, device_id: str) -> None:
        """Remove a device from the registered entities.

        After removal, messages from this device will be treated as unknown.
        """
        self._registered_devices.pop(device_id, None)
        _LOGGER.debug("Removed device %s from registered entities", device_id)

    def register_entity(self, device_id: str, device_enum: str) -> None:
        """Register that an entity exists for this device ID with its enum."""
        self._registered_devices[device_id] = device_enum
        _LOGGER.debug(
            "Registered entity for device %s with enum %s", device_id, device_enum
        )

    async def verify_device(self) -> bool:
        """Verify this is a Schellenberg USB stick by sending !? command.

        Returns True if verification succeeds, False otherwise.
        """
        if self._verify_future and not self._verify_future.done():
            _LOGGER.warning("Device verification already in progress")
            return False

        _LOGGER.debug("Verifying Schellenberg USB device")
        self._verify_future = self.hass.loop.create_future()

        try:
            # Send the verification command
            await self.send_command(CMD_VERIFY)

            # Wait for verification response with timeout
            result = await asyncio.wait_for(self._verify_future, timeout=VERIFY_TIMEOUT)
        except TimeoutError:
            _LOGGER.error("Device verification timeout - device did not respond to !?")
            return False
        else:
            _LOGGER.info("Device verification successful")
            return result
        finally:
            self._verify_future = None

    @callback
    def _update_status(self) -> None:
        """Update device status and notify listeners."""
        async_dispatcher_send(self.hass, SIGNAL_STICK_STATUS_UPDATED)

    def update_connection_status(self, connected: bool) -> None:
        """Update connection status (called from protocol)."""
        _LOGGER.debug(
            "Connection status changing: connected=%s (was %s)",
            connected,
            self._is_connected,
        )
        self._is_connected = connected
        self._update_status()

    @property
    def is_connected(self) -> bool:
        """Return whether the USB stick is connected."""
        return self._is_connected

    @property
    def device_version(self) -> str | None:
        """Return the device firmware version."""
        return self._device_version

    @property
    def device_mode(self) -> str | None:
        """Return the device mode (boot, initial, or listening)."""
        return self._device_mode

    @property
    def hub_id(self) -> str | None:
        """Return the hub device ID."""
        return self._hub_id

    # LED Control Methods
    async def led_on(self) -> None:
        """Turn the USB stick LED on."""
        _LOGGER.debug("Turning LED on")
        await self.send_command(CMD_LED_ON)

    async def led_off(self) -> None:
        """Turn the USB stick LED off."""
        _LOGGER.debug("Turning LED off")
        await self.send_command(CMD_LED_OFF)

    async def led_blink(self, count: int = 5) -> None:
        """Blink the USB stick LED a specific number of times.

        Args:
            count: Number of times to blink (1-9)

        """
        blink_commands = {
            1: CMD_LED_BLINK_1,
            2: CMD_LED_BLINK_2,
            3: CMD_LED_BLINK_3,
            4: CMD_LED_BLINK_4,
            5: CMD_LED_BLINK_5,
            6: CMD_LED_BLINK_6,
            7: CMD_LED_BLINK_7,
            8: CMD_LED_BLINK_8,
            9: CMD_LED_BLINK_9,
        }

        if count not in blink_commands:
            _LOGGER.error("Invalid blink count %d. Must be 1-9", count)
            return

        _LOGGER.debug("Blinking LED %d times", count)
        await self.send_command(blink_commands[count])

    # Device Calibration Methods
    async def set_upper_endpoint(self, device_enum: str) -> None:
        """Set the upper endpoint for a blind device.

        Args:
            device_enum: The device enumerator (hex string like "10")

        """
        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{CMD_SET_UPPER_ENDPOINT}0000"
        _LOGGER.debug("Setting upper endpoint for device %s: %s", device_enum, command)
        await self.send_command(command)

    async def set_lower_endpoint(self, device_enum: str) -> None:
        """Set the lower endpoint for a blind device.

        Args:
            device_enum: The device enumerator (hex string like "10")

        """
        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{CMD_SET_LOWER_ENDPOINT}0000"
        _LOGGER.debug("Setting lower endpoint for device %s: %s", device_enum, command)
        await self.send_command(command)

    async def allow_pairing_on_device(self, device_enum: str) -> None:
        """Make a device listen to a new remote's ID.

        Args:
            device_enum: The device enumerator (hex string like "10")

        """
        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{CMD_ALLOW_PAIRING}0000"
        _LOGGER.debug("Allowing pairing on device %s: %s", device_enum, command)
        await self.send_command(command)

    async def manual_up(self, device_enum: str) -> None:
        """Manually move blind up (simulates holding button).

        Args:
            device_enum: The device enumerator (hex string like "10")

        """
        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{CMD_MANUAL_UP}0000"
        _LOGGER.debug("Manual up for device %s: %s", device_enum, command)
        await self.send_command(command)

    async def manual_down(self, device_enum: str) -> None:
        """Manually move blind down (simulates holding button).

        Args:
            device_enum: The device enumerator (hex string like "10")

        """
        # Format: ssXX9AAZZZ
        # XX = device enum, 9 = number of messages, AA = command, ZZZ = padding
        command = f"{CMD_TRANSMIT}{device_enum}9{CMD_MANUAL_DOWN}0000"
        _LOGGER.debug("Manual down for device %s: %s", device_enum, command)
        await self.send_command(command)

    # USB Stick System Commands
    async def get_device_id(self) -> str | None:
        """Get the USB stick's unique device ID.

        Returns the device ID string or None if request fails.
        """
        if self._device_id_future and not self._device_id_future.done():
            _LOGGER.warning("Device ID request already in progress")
            return None

        _LOGGER.debug("Requesting device ID")
        self._device_id_future = self.hass.loop.create_future()

        try:
            # Send the request command
            await self.send_command(CMD_GET_DEVICE_ID)

            # Wait for device ID response with timeout
            device_id = await asyncio.wait_for(self._device_id_future, timeout=5)
        except TimeoutError:
            _LOGGER.error("Device ID request timeout - device did not respond")
            return None
        else:
            _LOGGER.info("Device ID retrieved successfully: %s", device_id)
            return device_id
        finally:
            self._device_id_future = None

    async def echo_on(self) -> None:
        """Enable local echo on the USB stick."""
        _LOGGER.debug("Enabling local echo")
        await self.send_command(CMD_ECHO_ON)

    async def echo_off(self) -> None:
        """Disable local echo on the USB stick."""
        _LOGGER.debug("Disabling local echo")
        await self.send_command(CMD_ECHO_OFF)

    async def enter_bootloader_mode(self) -> None:
        """Enter bootloader mode (B:0)."""
        _LOGGER.debug("Entering bootloader mode")
        await self.send_command(CMD_ENTER_BOOTLOADER)

    async def enter_initial_mode(self) -> None:
        """Enter initial mode (B:1)."""
        _LOGGER.debug("Entering initial mode")
        await self.send_command(CMD_ENTER_INITIAL)

    async def reboot_stick(self) -> None:
        """Reboot the USB stick (only available in bootloader mode)."""
        _LOGGER.debug("Rebooting USB stick")
        await self.send_command(CMD_REBOOT)

    async def disconnect(self) -> None:
        """Disconnect from the serial port and cancel pending operations."""
        self._disconnecting = True
        # Cancel any pending retry task
        if self._retry_task and not self._retry_task.done():
            self._retry_task.cancel()
            self._retry_task = None

        # Cancel any pending reconnect
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            self._reconnect_task = None

        # Cancel any pending stop_pairing task
        if self._stop_pairing_task and not self._stop_pairing_task.done():
            self._stop_pairing_task.cancel()
            self._stop_pairing_task = None

        if self._transport:
            self._transport.close()
            self._transport = None
        self._protocol = None
        self._is_connected = False
        self._disconnecting = False
        _LOGGER.info("Disconnected from Schellenberg USB stick")


class SchellenbergProtocol(asyncio.Protocol):
    """Serial protocol for reading newline-terminated messages."""

    def __init__(
        self, message_callback: Callable[[str], None], api: SchellenbergUsbApi
    ) -> None:
        """Initialize the protocol."""
        self.message_callback = message_callback
        self.api = api
        self.buffer = ""
        self.transport: asyncio.Transport | None = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:
        """Called when a connection is made."""
        self.transport = transport  # type: ignore[assignment]

    def data_received(self, data: bytes) -> None:
        """Called with new data from the serial port."""
        _LOGGER.debug("Received from serial device: %s", data)
        self.buffer += data.decode("ascii", errors="ignore")
        # Safety limit: prevent unbounded buffer growth if no newline arrives
        if len(self.buffer) > 4096:
            _LOGGER.warning(
                "Serial buffer exceeded 4096 bytes, truncating to 1024. "
                "Raw data may contain unexpected framing."
            )
            self.buffer = self.buffer[-1024:]
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if line.strip():
                _LOGGER.debug("Parsed message from serial device: %s", line.strip())
                self.message_callback(line.strip())

    def connection_lost(self, exc: Exception | None) -> None:
        """Called when the serial connection is lost or closed.

        Triggers a reconnection attempt after a short delay, unless
        the API is being intentionally disconnected.
        """
        _LOGGER.warning("Serial port connection lost: %s", exc)
        self.transport = None
        self.api.update_connection_status(False)

        # Schedule a reconnect (unless intentionally disconnected)
        api = self.api
        if not api._disconnecting and not api._is_connecting:
            # Use hass.create_task for safety; wrap to avoid stale references
            async def _delayed_reconnect() -> None:
                try:
                    await asyncio.sleep(2)
                    await api.connect()
                except Exception:
                    _LOGGER.exception("Reconnect failed")
                    # Notify entities that we're still disconnected
                    api._update_status()

            api._reconnect_task = asyncio.create_task(_delayed_reconnect())
