# schellenberg_usb Home Assistant Component

[![GitHub Release](https://img.shields.io/github/release/GimpArm/schellenberg_usb.svg)](https://github.com/GimpArm/schellenberg_usb/releases)
[![License](https://img.shields.io/github/license/GimpArm/schellenberg_usb.svg)](https://github.com/GimpArm/schellenberg_usb/blob/main/LICENSE)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/GimpArm/schellenberg_usb/build-test.yaml)

Home Assistant component that interfaces with the [Schellenberg Usb Funk-Stick](https://www.schellenberg.de/smart-home-produkte/smart-home-steuerzentralen/funk-stick/21009/).

> [!WARNING] 
> This integration is not affiliated with Schellenberg, the developers take no responsibility for anything that happens to
> your devices because of this library.

![Schellenberg](https://raw.githubusercontent.com/GimpArm/schellenberg_usb/main/images/schellenberg-logo.png)

## Features

* Supports blind movement Up, Down, and Stop
* After calibration, position tracking is possible.
* **Remote Learning Mode**: Register physical Schellenberg remotes as persistent HA event entities for automation triggers.
* **Native Group Control**: Send hardware broadcast commands (like Schellenberg 5-channel remotes) for simultaneous multi-blind operation.

## Installation

### Step 1: Download files

#### Option 1: Via HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=TechFreak96&repository=schellenberg_usb&category=integration)

Make sure you have HACS installed. If you don't, run `wget -O - https://get.hacs.xyz | bash -` in HA.  
Choose Integrations under HACS. Click the '+' button on the bottom of the page, search for "schellenberg usb", choose it, and click install in HACS.

#### Option 2: Manual
Clone this repository or download the source code as a zip file and add/merge the `custom_components/` folder with its contents in your configuration directory.


### Step 2: Restart HA
In order for the newly added integration to be loaded, HA needs to be restarted.

### Step 3: Add integration to HA (<--- this is a step that a lot of people forget)
In HA, go to Configuration > Integrations.
In the bottom right corner, click on the big button with a '+'.

If the component is properly installed, you should be able to find 'Schellenberg USB' in the list. You might need to clear you browser cache for the integration to show up.

Select it, and the schellenberg usb integration is ready for use.

### Step 4: Pair your devices

1. In Home Assistant, go to **Settings > Devices & Services**
2. Find the **Schellenberg USB** integration and click on it
3. Click the **+** button or select **Pair device** from the menu
4. Put your blind motor into pairing mode (see [Device Pairing Instructions](#device-pairing-instructions))
5. Once pairing is successful, provide a friendly name for your blind

### Step 5: Calibrate your blinds

Calibration is essential for accurate position tracking. The integration measures how long it takes your blind to fully open and close, allowing it to calculate the current position during operation.

> [!IMPORTANT]
> This calibration is **not** the same as setting the end positions (fully open/closed limits) on your blind motor. End positions must be configured directly on the device itself using the motor's built-in adjustment features or a Schellenberg remote control before using this integration.

#### Starting Calibration

You can calibrate a blind:
- **During initial pairing**: After naming your device, you'll be prompted to calibrate
- **After pairing from the device page**: Go to the device and click the **Calibrate** gear icon (⚙️) as shown below

![Calibrate button location](images/calibrate-button.png)

*Click the gear icon labeled "Calibrate" in the top right corner of your blind device to start calibration.*

#### Calibration Steps

1. **Step 1 - Close the blind**: Ensure your blind is fully closed (all the way down). Press **Next** when ready.

2. **Step 2 - Measure open time**: 
   - Press **Start** in the dialog
   - Then press the **open button** on your physical remote/control
   - The integration will automatically detect when the blind starts moving and begin timing
   - Wait for the blind to fully open - the timer stops automatically when movement stops

3. **Step 3 - Measure close time**:
   - Press **Start** in the dialog  
   - Then press the **close button** on your physical remote/control
   - The integration will automatically detect when the blind starts moving and begin timing
   - Wait for the blind to fully close - the timer stops automatically when movement stops

4. **Complete**: The integration will display the measured open and close times and save them for position tracking

> [!TIP]
> There's no need to rush when pressing the buttons - the timer doesn't start until the integration receives a "moving" signal from the blind motor.

> [!NOTE]
> If calibration times seem incorrect, you can recalibrate at any time from the device options.

---

## Advanced Features

### Remote Learning Mode

The integration can learn physical Schellenberg remote controls and expose them as **persistent Event Entities** in Home Assistant. Each registered remote fires HA events when a button is pressed, enabling automations without any additional hardware.

**How it works:**
1. Go to **Settings > Devices & Services > Schellenberg USB > Options**
2. Enable **"Learn Remote"** and press a button on your physical Schellenberg remote
3. The remote ID and channel are captured and stored persistently in `entry.options`
4. A new Event Entity appears (e.g. `event.schellenberg_remote_a1b2c3`)
5. Every subsequent button press fires a HA event and updates the entity

**Example Automation Trigger:**
```yaml
trigger:
  - platform: event
    event_type: schellenberg_usb_remote_button_pressed
    event_data:
      remote_id: "A1B2C3"
      button: "up"
```

**Event Data Schema:**
| Field | Type | Description |
|-------|------|-------------|
| `remote_id` | string | 6-char hex ID of the remote (e.g. `5D3E7C`) |
| `channel` | string | Remote channel (e.g. `1`, `2`, ..., `5`) |
| `button` | string | Button pressed: `up`, `down`, or `stop` |
| `command` | string | Raw hex command byte from the protocol |

**Configuration** (via Options Flow):
1. Set **"Learn Remote"** checkbox
2. Press any button on the physical remote within 30 seconds
3. Optionally provide a friendly **"Remote Name"**
4. The remote is now registered and will survive HA restarts

> [!TIP]
> If a remote doesn't appear after learning, ensure you're within range (~20m indoors) and try again. The stick listens for all `ss`-prefixed messages while in listening mode.

### Native Group Command Service

Send hardware-level broadcast commands through the USB stick, mimicking the behavior of Schellenberg 5-channel remotes where all blinds on a channel react **simultaneously** (no sequential delays).

**Service:** `schellenberg_usb.send_native_group_command`

```yaml
# Example: Send "open" to all blinds on channel 5 (the "All" channel)
service: schellenberg_usb.send_native_group_command
data:
  action: open
  group_id: "05"
```

**Parameters:**
| Field | Required | Default | Description |
|-------|----------|---------|-------------|
| `action` | ✅ Yes | — | `up`, `down`, `stop`, `open`, or `close` |
| `group_id` | ❌ No | `05` | 2-char hex group/channel byte (e.g. `01`-`05`) |

**Technical Note:** Unlike the sequence-based group command (`send_group_command`) which queues individual commands to multiple blinds, the native group command sends a single hardware broadcast. All blind motors that are paired to the given channel will react at the exact same time.

### Event Entity Platform

Each registered remote creates an EventEntity that:

- Fires typed events (`up`, `down`, `stop`) via `_trigger_event()` — usable natively in HA automation triggers
- Fires bus events (`schellenberg_usb_remote_button_pressed`) for cross-integration compatibility
- Provides Device Registry entry attached to the USB hub
- Persists across HA restarts via `entry.options` storage

**Entity Attributes:**
| Attribute | Description |
|-----------|-------------|
| `event_types` | Supported event types: `up`, `down`, `stop` |
| `device_info` | Manufacturer: Schellenberg, linked to USB hub |
| `unique_id` | Format: `{entry_id}_remote_{remote_id}` |

---

## Device Pairing Instructions

## Device Pairing Instructions

Each Schellenberg device has a specific button combination to enter pairing mode. You must put your device into pairing mode within 2 minutes of starting the pairing process in Home Assistant.

### ROLLODRIVE 65 PREMIUM / 75 PREMIUM (Electric Belt Winders)
**Art.Nr.: 22567, 22576, 22578, 22726, 22727, 22728, 22767**

To enter pairing mode:
1. Press and hold the **Sun (☀)** button and the **Up (▲)** button simultaneously
2. Hold for **5 seconds** until the LED flashes
3. The device is now in pairing mode

### ROLLOPOWER PLUS / STANDARD (Tube Motors)
**Art.Nr.: 20106, 20110, 20406, 20410, 20610, 20615, 20620, 20640, 20710, 20720, 20740**

These motors are controlled via external switches or remote controls. Pairing is typically done through the connected Schellenberg remote control or timer switch.

### Funk-Rollladenmotoren PREMIUM (Radio Tube Motors)
**Art.Nr.: 21106, 21110, 21210, 21220, 21240**

To enter pairing mode, refer to your specific remote control or timer switch manual. The pairing button combination varies by the control device used.

### Remote Learning

This feature allows you to "listen" for button presses from your physical Schellenberg remote controls, even if they are not directly paired as a device in Home Assistant. This is useful for:
- **Identifying unknown remotes**: Discover the `remote_id`, `channel`, and `button` data of any Schellenberg remote.
- **Triggering automations**: Use remote button presses to trigger Home Assistant automations for any Schellenberg device, regardless of whether it's linked to a blind or not.

#### How to use Remote Learning

1. Go to **Developer Tools > Events** in Home Assistant.
2. In the "Listen to events" box, type `schellenberg_usb_remote_button_pressed` and click **Start Listening**.
3. Press a button on your Schellenberg remote control.
4. You will see an event fired with details like `remote_id`, `channel`, and `button`. You can use this data to create automations.

Example automation snippet (listening for an "up" button press on a specific remote):

```yaml
automation:
  - alias: "Schellenberg Remote Up Button Pressed"
    trigger:
      platform: event
      event_type: schellenberg_usb_remote_button_pressed
      event_data:
        remote_id: "123456" # Replace with your remote's ID
        button: "up"
    action:
      # Your automation actions here
      - service: light.turn_on
        entity_id: light.living_room_lights
```

> [!NOTE]
> The pairing instructions above are based on common Schellenberg products. Your specific device may have different procedures - always refer to the device's original manual if unsure.

### Native Group Control

This integration supports controlling groups of Schellenberg devices, similar to how a 5-channel remote can control individual channels or all channels simultaneously. This is particularly useful for controlling multiple blinds with a single command.

#### How to use Native Group Control

To control a group, you can use the `schellenberg_usb.control_native_group` service in Home Assistant. This service takes two parameters:

- `action`: The desired action (`up`, `down`, `stop`).
- `group_id` (optional): The 2-character hexadecimal group ID. If omitted, the command will be sent to all channels (`FF`). Common group IDs are `01` to `05` for individual channels when controlling a group, or `FF` for all.

Example service calls:

```yaml
# Move all blinds associated with group channel 01 up
- service: schellenberg_usb.control_native_group
  data:
    action: "up"
    group_id: "01"

# Stop all blinds associated with group channel FF (all)
- service: schellenberg_usb.control_native_group
  data:
    action: "stop"
    group_id: "FF"

# Move all blinds up (equivalent to group_id: "FF")
- service: schellenberg_usb.control_native_group
  data:
    action: "up"
```
