"""Event platform for Schellenberg USB remote controls.

This module implements the Home Assistant event platform for registering and
processing physical Schellenberg remote controls. Each known remote is represented
as an EventEntity that fires HA events on button press.

Remote types (Schema):
    - {remote_id: "A1B2C3", channel: "1"}

Events fired (event_type = schellenberg_usb_remote_button_pressed):
    - remote_id: 6-char hex ID of the remote
    - channel: remote channel (1-5)
    - button: "up", "down", or "stop"
    - command: raw hex command byte
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SchellenbergUsbApi
from .const import (
    DOMAIN,
    SIGNAL_REMOTE_EVENT,
    SUBENTRY_TYPE_BLIND,
    SchellenbergConfigEntry,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SchellenbergConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Schellenberg USB remote event entities.

    Creates one EventEntity per registered remote ID found in the config
    subentries. Each entity listens for dispatcher signals from the API
    when a button on the corresponding physical remote is pressed.
    """
    api: SchellenbergUsbApi = entry.runtime_data
    entities: list[SchellenbergRemoteEvent] = []

    # Create entities from subentries that have remote_id data
    for subentry in entry.subentries.values():
        remote_id = subentry.data.get("remote_id")
        channel = subentry.data.get("channel")
        if remote_id and channel is not None:
            entities.append(
                SchellenbergRemoteEvent(
                    api=api,
                    entry=entry,
                    remote_id=remote_id,
                    channel=channel,
                    subentry_id=subentry.subentry_id,
                )
            )

    if not entities:
        _LOGGER.debug("No registered remote IDs found; no event entities to create")
        return

    _LOGGER.info(
        "Setting up %d Schellenberg remote event entities", len(entities)
    )
    async_add_entities(entities)


class SchellenbergRemoteEvent(EventEntity):
    """Representation of a Schellenberg physical remote control.

    This entity fires HA events when a button on the associated remote is
    pressed. It subscribes to a dispatcher signal that is emitted by the
    API on every received remote button frame.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = "remote"

    # The event types that this entity can fire
    _attr_event_types = [
        "up",
        "down",
        "stop",
    ]

    def __init__(
        self,
        api: SchellenbergUsbApi,
        entry: SchellenbergConfigEntry,
        remote_id: str,
        channel: str,
        subentry_id: str | None = None,
    ) -> None:
        """Initialize the remote event entity.

        Args:
            api: The Schellenberg USB API instance.
            entry: The HA config entry for this integration.
            remote_id: 6-char hex ID of the physical remote.
            channel: Remote channel (e.g. "1" to "5").
            subentry_id: Optional config subentry to group under.

        """
        self.api = api
        self._remote_id = remote_id
        self._channel = channel
        self._subentry_id = subentry_id

        self._attr_unique_id = f"{entry.entry_id}_remote_{remote_id}"
        self._attr_name = f"Remote {remote_id} (ch{channel})"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_remote_{remote_id}")},
            name=f"Schellenberg Remote {remote_id}",
            manufacturer="Schellenberg",
            via_device=(DOMAIN, entry.entry_id),
        )

    async def async_added_to_hass(self) -> None:
        """Register the dispatcher listener on add."""
        await super().async_added_to_hass()

        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_REMOTE_EVENT}_{self._remote_id}",
                self._async_handle_button,
            )
        )
        _LOGGER.debug(
            "Remote event entity %s listening for dispatcher signal %s",
            self.entity_id,
            f"{SIGNAL_REMOTE_EVENT}_{self._remote_id}",
        )

    @callback
    def _async_handle_button(self, button: str, command: str) -> None:
        """Fire an event when a remote button is pressed.

        This callback is triggered by the API's dispatcher signal. The entity
        fires a typed event that can be used in automations via the trigger
        ``event`` platform.

        Args:
            button: "up", "down", or "stop".
            command: Raw hex command byte from the protocol.

        """
        _LOGGER.debug(
            "Remote %s button press: %s (cmd=%s)",
            self._remote_id,
            button,
            command,
        )

        # Fire the typed event for automation triggers
        self._trigger_event(button, {"command": command})
        self.async_write_ha_state()

        # Additionally fire a bus event for broad compatibility
        self.hass.bus.async_fire(
            f"{DOMAIN}_remote_button_pressed",
            {
                "entity_id": self.entity_id,
                "remote_id": self._remote_id,
                "channel": self._channel,
                "button": button,
                "command": command,
            },
        )
