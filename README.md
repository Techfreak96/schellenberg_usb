# Schellenberg USB Home Assistant Integration

> [!CAUTION]
> **⚠️ Under Development** — This integration is currently under active development. Functionality may be unstable or broken. Use with caution and expect breaking changes.

[![GitHub Release](https://img.shields.io/github/release/Techfreak96/schellenberg_usb.svg)](https://github.com/Techfreak96/schellenberg_usb/releases)
[![License](https://img.shields.io/github/license/Techfreak96/schellenberg_usb.svg)](https://github.com/Techfreak96/schellenberg_usb/blob/main/LICENSE)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/Techfreak96/schellenberg_usb/build-test.yaml)](https://github.com/Techfreak96/schellenberg_usb/actions)
[![HA Integration](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-blue)](https://www.home-assistant.io/)

Home Assistant integration for the [Schellenberg USB Funk-Stick (21009)](https://www.schellenberg.de/smart-home-produkte/smart-home-steuerzentralen/funk-stick/21009/) – a drop-in replacement for the discontinued Smart Friends / QIVICON system.

> [!WARNING]
> This integration is **not affiliated with Schellenberg GmbH**. The developers take no responsibility for anything that happens to your devices. Use at your own risk.

> [!IMPORTANT]
> **Schellenberg has discontinued their Smart Friends platform.**

![Schellenberg](https://raw.githubusercontent.com/Techfreak96/schellenberg_usb/main/images/schellenberg-logo.png)

---

## 📋 Table of Contents

- [Features](#features)
- [Supported Devices](#supported-devices)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Device Pairing](#device-pairing)
- [Configuration](#configuration)
- [Services](#services)
- [Safety Lock System](#safety-lock-system)
- [Window Handle Sensor](#window-handle-sensor)
- [Remote Controls](#remote-controls)
- [Group Commands](#group-commands)
- [Technical Details](#technical-details)
- [FAQ / Troubleshooting](#faq--troubleshooting)
- [Credits & Sources](#credits--sources)

---

## ✨ Features

### Core
- ✅ **Blind Control** – Up, Down, Stop with smooth position tracking (0-100%)
- ✅ **Virtual Position Tracking** – Time-based position estimation for unidirectional Gen 1 devices
- ✅ **Calibration** – Auto-measure travel times for accurate position calculation
- ✅ **Belt Drive Support** – Native support for Rollodrive Gurtwickler with configurable travel characteristics

### Smart Home
- ✅ **Safety Lock System** – Lock blinds against closing via binary sensor (window/door contact)
- ✅ **Window Handle Sensor** – Detect Schellenberg window positions (closed/tilted/open) with auto-safety-lock
- ✅ **Remote Learning** – Register physical Schellenberg remotes as HA event entities
- ✅ **Group Commands** – Hardware broadcast (native) + sequential (software queue) group control
- ✅ **Auto-Discovery** – New devices trigger HA notifications with pairing instructions

### Monitoring
- ✅ **RSSI Signal Strength** – Per-blind radio signal quality sensor
- ✅ **Connection Status** – USB stick connectivity monitoring
- ✅ **Firmware Version** – Stick firmware version display
- ✅ **Operating Mode** – Stick mode (bootloader/initial/listening)

### Technical
- ✅ **100% Async** – Non-blocking I/O via `pyserial-asyncio`
- ✅ **Exponential Backoff** – Retry mechanism for `tE` (stick busy) errors: 100ms→200ms→400ms→800ms
- ✅ **ConfigEntryNotReady** – Proper HA retry on connection failure
- ✅ **Auto-Reconnect** – Automatic reconnection on USB disconnect
- ✅ **Multi-Language** – German, English, Spanish, French

---

## 📋 Supported Devices

### Schellenberg USB Stick

| Article | Name | Type |
|---------|------|------|
| 21009 | Funk-Stick (Magenta SmartHome / QIVICON) | USB dongle, 868.4 MHz |

### Blind Motors & Belt Drives

| Product ID | Name | Type | Position Tracking |
|-----------|------|------|-----------------|
| 22567, 22767 | ROLLODRIVE 65 PREMIUM | Electric belt winder (Gurtwickler) | ✅ Virtual (time-based) |
| 22576, 22776 | ROLLODRIVE 75 PREMIUM | Electric belt winder (Gurtwickler) | ✅ Virtual (time-based) |
| 21106, 21110 | Funk-Rollladenmotor PREMIUM | Radio tube motor | ✅ Virtual (time-based) |
| 21210, 21220, 21240 | Funk-Rollladenmotor PREMIUM V2 | Bidirectional radio tube motor | ✅ Virtual + Events |
| 20264 | Funk-Markisenantrieb Premium | Awning motor | ⚠️ Basic (no intermediate positions) |

### Sensors & Remotes

| Product ID | Name | Type |
|-----------|------|------|
| 20016, 20023 | 1-/5-Channel Remote | Wireless remote control |
| Various | Window handle sensor | Tilt sensor (0°/90°/180°) |

> [!NOTE]
> **Gen 1 devices (20xxx)** are **unidirectional** – they only receive commands and send no status feedback. The integration estimates position (0-100%) virtually based on calibrated travel times.

---

## 📦 Installation

### Option A: Via HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Techfreak96&repository=schellenberg_usb&category=integration)

1. Ensure HACS is installed ([guide](https://hacs.xyz/docs/installation/download))
2. Go to **HACS > Integrations > "..." > Custom repositories**
3. Add `https://github.com/Techfreak96/schellenberg_usb` (category: Integration)
4. Click **Install**
5. **Restart Home Assistant**

### Option B: Manual

```bash
# Clone to your custom_components directory
git clone https://github.com/Techfreak96/schellenberg_usb.git
cp -r schellenberg_usb/custom_components/schellenberg_usb /path/to/config/custom_components/

# Restart Home Assistant
```

---

## 🚀 Quick Start

### 1. Add the Integration

```
Settings > Devices & Services > "+" > "Schellenberg USB"
```

- Select your USB stick serial port (e.g., `/dev/ttyACM0`, `COM3`)
- The stick will be verified automatically

### 2. Pair a Blind

```
Integration Page > "+" (Blind) > "Pair"
```

1. Put your blind into pairing mode (see [Device Pairing](#device-pairing))
2. Click **Pair** in the HA dialog
3. Wait for the blind to be detected (up to 120 seconds)
4. Provide a friendly name

### 3. Calibrate

After pairing, the calibration wizard starts automatically:

1. **Close the blind** – press Next
2. **Open the blind** – manually raise it, the timer starts automatically
3. **Close the blind** – manually lower it, the timer starts automatically
4. Times are saved – position tracking is now active

> [!TIP]
> You can recalibrate anytime via **Options > Calibrate** on the blind device page.

---

## 🔗 Device Pairing

New blinds are added via the **"+" (Blind)** button on the integration device page.
When clicked, the pairing wizard guides you through the process:

1. Click **Pair** – the USB stick enters pairing mode
2. Activate pairing mode on your blind motor (see below)
3. Wait for detection (up to 120 seconds)
4. Name the device and run calibration

### ROLLODRIVE 65/75 PREMIUM (Electric Belt Winders)

```
Art. 22567, 22576, 22578, 22726, 22727, 22728, 22767
```

1. Press and hold **Sun (☀)** + **Up (▲)** buttons simultaneously for ~5s
2. LED flashes – device is in pairing mode
3. Click **Pair** in Home Assistant within 2 minutes

### Funk-Rollladenmotoren PREMIUM (Radio Tube Motors)

```
Art. 21106, 21110, 21210, 21220, 21240
```

- Pairing is typically done via the connected Schellenberg remote
- Follow the instructions in your device's manual

### General Tips

- Keep the USB stick within range (~20m indoors, ~100m outdoors)
- Avoid metal obstructions between the stick and the motor
- Use the **RSSI Signal sensor** to find the optimal stick position

---

## ⚙️ Configuration

### Option Flow

```
Integration Page > "Configure" > Menu
```

| Option | Description |
|--------|-------------|
| **USB-Anschluss konfigurieren** | Change the serial port path |
| **Neue Fernbedienung anlernen** | Register a physical remote control |
| **Fernbedienungen verwalten** | View and delete registered remotes |
| **Virtuelle Gruppen verwalten** | Create/remove group channel IDs |
| **Sicherheitssperre konfigurieren** | Assign binary sensors (window/door) to blinds via entity selector |

### Window Sensor Configuration

Window handle sensors are **not** added via a "+" button. Instead:

1. Go to **Configure > Sicherheitssperre konfigurieren**
2. Each paired blind shows an entity selector field
3. Select the `binary_sensor` entity for the corresponding window
4. When the window is open, the blind will be locked against closing

### Per-Blind Options

Each blind can be recalibrated from its device page:

```
Devices > [Blind Name] > Gear Icon > Calibrate
```

---

## 🔌 Services

| Service | Description |
|---------|-------------|
| `send_group_command` | Send a command to multiple blinds sequentially (via software queue) |
| `send_native_group_command` | Send a hardware broadcast command to all devices on a channel |
| `pair_device` | Pair a device directly by its 6-char hex ID |
| `set_blind_lock` | Lock/unlock a blind to prevent DOWN commands |

### send_group_command (Sequential)

```yaml
service: schellenberg_usb.send_group_command
data:
  entity_id:
    - cover.wohnzimmer
    - cover.schlafzimmer
  action: open
```

### send_native_group_command (Hardware Broadcast)

```yaml
service: schellenberg_usb.send_native_group_command
data:
  action: open
  group_id: "05"  # Channel 5 = "All" (default)
```

> [!NOTE]
> **send_native_group_command** sends a single radio broadcast to all devices on the specified channel – they react simultaneously. **send_group_command** sends commands sequentially with anti-collision delays.

### set_blind_lock (Safety Lock)

```yaml
# Lock by entity_id (easiest)
service: schellenberg_usb.set_blind_lock
data:
  entity_id: cover.wohnzimmer_rollo
  locked: true

# Lock by device_id
service: schellenberg_usb.set_blind_lock
data:
  device_id: "A1B2C3"
  locked: false
```

---

## 🔒 Safety Lock System

The safety lock prevents a blind from closing (DOWN command) while always allowing UP and STOP for safety.

### Automatic via Options Flow

1. Go to **Integration > Options > Configure Safety Lock**
2. For each blind, select a `binary_sensor` (window/door contact)
3. When the sensor turns **on** (open), the blind is automatically locked
4. When the sensor turns **off** (closed), the blind is unlocked

### Manual via Service Call

```yaml
service: schellenberg_usb.set_blind_lock
data:
  entity_id: cover.wohnzimmer_rollo
  locked: true
```

### Automation Example

```yaml
- alias: "Lock blinds when window opens"
  trigger:
    - platform: state
      entity_id: binary_sensor.wohnzimmer_fenster
      to: "on"
  action:
    - service: schellenberg_usb.set_blind_lock
      data:
        entity_id: cover.wohnzimmer_rollo
        locked: true
```

### Safety Guarantee

> [!IMPORTANT]
> **CMD_UP (open) and CMD_STOP are NEVER blocked** – the blind can always be opened or stopped. Only CMD_DOWN (close) is blocked when the lock is active. This ensures no one gets trapped.

---

## 🪟 Window Handle Sensor

The USB stick receives signals from Schellenberg **window handle sensors**. Once detected, they appear as HA sensor entities.

### Adding a Window Sensor

1. **Integration > Configure > Sicherheitssperre konfigurieren**
2. **Select which blind** this sensor belongs to via the entity selector
3. Enter the binary sensor entity ID for your window handle sensor
4. The safety lock activates automatically (see [Safety Lock](#sicherheitssperre-konfigurieren))

> [!NOTE]
> Window sensors are added through the **Options Flow** (gear icon), not via a "+" button. This keeps the device card focused on blind management.

### Auto-Safety Lock

When a window sensor is bound to a blind, the safety lock activates **automatically**:

| Sensor State | Action |
|-------------|--------|
| `closed` (0°) | 🔓 Blind unlocked – normal operation |
| `tilted` (90°) | 🔒 Blind locked – DOWN blocked |
| `open` (180°) | 🔒 Blind locked – DOWN blocked |

### Entity States

| HA State | Icon | Description |
|----------|------|-------------|
| `closed` | 🪟 `window-closed-variant` | Handle at 0° (closed) |
| `tilted` | 🪟 `window-open-variant` | Handle at 90° (tilted) |
| `open` | 🪟 `window-open` | Handle at 180° (fully open) |

---

## 📡 Remote Controls

Physical Schellenberg remotes can be learned as **persistent HA event entities**.

### Learning a Remote

```
Integration > Options > "Learn a New Remote"
→ Press any button on the physical remote within 30 seconds
→ Remote is registered as an EventEntity
```

### Automation Trigger

```yaml
trigger:
  - platform: event
    event_type: schellenberg_usb_remote_button_pressed
    event_data:
      remote_id: "A1B2C3"
      button: "up"
```

### Event Data

| Field | Type | Description |
|-------|------|-------------|
| `remote_id` | string | 6-char hex ID (e.g., `A1B2C3`) |
| `channel` | string | Channel number (`1`–`5`) |
| `button` | string | `up`, `down`, or `stop` |
| `command` | string | Raw hex command byte |

---

## 👥 Group Commands

### Hardware Broadcast (Native)

Mimics the behavior of Schellenberg 5-channel remotes – sends a single radio broadcast to all devices on a channel. **All devices react simultaneously.**

```yaml
service: schellenberg_usb.send_native_group_command
data:
  action: open
  group_id: "05"  # Channel 5 = all devices
```

### Software Queue (Sequential)

Sends the same command to multiple blinds one at a time with anti-collision delays (150ms between commands, 200ms between devices). Prevents `tE` (stick busy) errors.

```yaml
service: schellenberg_usb.send_group_command
data:
  entity_id:
    - cover.wohnzimmer
    - cover.schlafzimmer
    - cover.kueche
  action: close
```

---

## 🔧 Technical Details

### Protocol

Based on the reverse-engineered protocol by [Hypfer](https://github.com/Hypfer/schellenberg-qivicon-usb) and [LoPablo](https://github.com/LoPablo/schellenberg-qivicon-usb).

#### Message Format (Sending)

```
ss XX 9 AA 0000\r\n

ss    = Schellenberg transmit prefix (fixed)
XX    = Device enumerator (2 hex chars, 01-FF)
9     = Message count (0-F, typically 9)
AA    = Command byte (00=stop, 01=up, 02=down, 40=pair, 60=change direction)
0000  = Padding (required)
```

#### Message Format (Receiving)

```
ss XX YYYYYY ZZZZ CC PP RR

ss    = Prefix (2 chars)
XX    = Device enumerator (2 hex chars)
YYYYYY = Device ID (6 hex chars)
ZZZZ  = Message counter (4 hex chars, ignored)
CC    = Command (2 hex chars)
PP    = Padding (2 hex chars)
RR    = RSSI signal strength (2 hex chars)
```

#### USB Stick Responses

| Response | Meaning |
|----------|---------|
| `t1` | Transmit ON – command accepted, radio active |
| `t0` | Transmit OFF – command completed |
| `tE` | Transmit Error – stick busy, **retry with backoff** |
| `RFTU_V20...` | Device verification response |

### Virtual Position Tracking

Since **Gen 1 devices are unidirectional** (no status feedback), the integration estimates position using:

```
position = (elapsed_time / travel_time) * 100
```

Where:
- `elapsed_time` = time since movement started (measured in real-time)
- `travel_time` = calibrated full-stroke time (per blind, from calibration)
- `position` = estimated position (0% = fully closed, 100% = fully open)

#### Tracking Loop

```
Movement starts → position task created (200ms interval)
  → Every 200ms: recalculate position from elapsed time
  → Every 1 second: write new state to HA
  → On STOP event OR target reached: finalize position, stop loop
```

#### Calibration

During calibration, the integration measures:
- **Open time**: Time from fully closed to fully open
- **Close time**: Time from fully open to fully closed

These times are stored per-blind and survive HA restarts.

### Retry Mechanism

The integration implements exponential backoff for `tE` (stick busy) errors:

```
tE received → Retry after 100ms
  → tE received → Retry after 200ms
    → tE received → Retry after 400ms
      → tE received → Retry after 800ms
        → Failed after 4 retries → Warning logged
```

### Connection Management

```
async_setup_entry → await api.connect()
  → Success? → Continue setup
  → Failure? → Raise ConfigEntryNotReady → HA retries later

connection_lost (USB unplugged)
  → _is_connected = False
  → Wait 2 seconds
  → await api.connect() (cancelable via _reconnect_task)

disconnect (integration unload)
  → Cancel _retry_task, _reconnect_task, _stop_pairing_task
  → Close transport
```

### Architecture Diagram

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Home Assistant  │     │  schellenberg_usb │     │  USB Stick 21009 │
│  (Entity Layer)  │────▶│  (Integration)    │────▶│  (Serial 112500) │
│                  │     │                   │     │                  │
│  CoverEntity ◀───│────▶│  api.py           │────▶│  ssXX9AA0000\r\n │
│  SensorEntity ◀──│────▶│  protocol →       │◀────│  t1/t0/tE/RSSI   │
│  EventEntity  ◀──│────▶│  _handle_message()│◀────│  ssXX... messages │
│  SwitchEntity    │     │  dispatcher       │     │                  │
└─────────────────┘     └──────────────────┘     └──────────────────┘
```

### Communication Timing

| Operation | Typical Duration |
|-----------|-----------------|
| Single blind UP/DOWN | ~10-20s (depends on travel time) |
| Position update interval | 200ms |
| HA state write interval | 1s (every 5th update) |
| Pairing timeout | 120s |
| Reconnect delay | 2s (initial) |
| Command retry backoff | 100ms → 200ms → 400ms → 800ms |
| Connection verification | 5s timeout |

---

## ❓ FAQ / Troubleshooting

### Blind doesn't move after pairing

- The pairing may have captured the **remote ID** instead of the **motor ID**. The motor's actual device ID is usually in the logs (`enum=09, id=6A7CBF`).
- Try **re-pairing** and ensure no remote button is pressed during the pairing window.
- Check the debug logs for `Received message for device X but no corresponding entity found`.

### Position tracking is inaccurate

- **Recalibrate** the blind via **Options > Calibrate**
- Ensure the blind is fully closed before starting calibration
- Default travel time is 60s – calibration measures the actual time

### USB stick not detected

- Check `dmesg | grep tty` for device enumeration
- Ensure the user has permissions: `sudo usermod -a -G dialout $USER`
- Try a different USB port
- The stick auto-negotiates baudrate – 112500 is the default

### Connection keeps dropping

- Check the USB cable quality
- Use the **RSSI Signal sensor** to verify radio signal strength
- Monitor debug logs for `tE` (busy) patterns

### Error: "400 Bad Request" when clicking "+"

- This was a bug in earlier versions – update to `v1.2.0+`
- If persisting, check the Home Assistant logs for specific error details

### Logging

Enable debug logging in `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.schellenberg_usb: debug
```

---

## 🙏 Credits & Sources

This integration builds on the work of many community members:

| Source | Contribution |
|--------|-------------|
| [GimpArm/schellenberg_usb](https://github.com/GimpArm/schellenberg_usb) | Original Home Assistant integration (base structure) |
| [Hypfer/schellenberg-qivicon-usb](https://github.com/Hypfer/schellenberg-qivicon-usb) | Protocol reverse engineering (message format, commands) |
| [LoPablo/schellenberg-qivicon-usb](https://github.com/LoPablo/schellenberg-qivicon-usb) | Extended packet analysis, device enumerator mapping |
| [moTo31/schellenberg-mqtt](https://github.com/moTo31/schellenberg-mqtt) | MQTT daemon, pairing procedure, command structure |
| [ohlmannmichael-ai](https://github.com/ohlmannmichael-ai) | Bug reports, calibration persistence testing |
| [HA Community Thread](https://community.home-assistant.io/t/integration-schellenberg/102832) | Gurtwickler belt drive information, user feedback |

---

## 📄 License

Apache License 2.0 – See [LICENSE](LICENSE) for details.

---

**Status**: 🟢 Active Development | **Latest**: `v1.2.0` | **Branches**: `main`, `beta`

| Service | Description |
|---------|-------------|
| `pair` | Activate pairing mode on the USB stick |
| `pair_device` | Pair a device directly by 6-char hex ID |
| `send_group_command` | Sequential group command (queue-based) |
| `send_native_group_command` | Hardware broadcast group command |
| `set_blind_lock` | Lock/unlock a blind against DOWN commands |

---

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
