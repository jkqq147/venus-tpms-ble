# venus-tpms-ble

BLE TPMS integration for Victron Venus OS / GX devices.

It adds a `TPMS` page to the local GX UI, scans BLE tire-pressure sensor
advertisements through BlueZ, and lets you bind discovered sensors to four
wheel positions.

[中文说明](README.zh-CN.md)


## What You Get

- A `TPMS` entry in the GX device list.
- Four wheel positions: front left, front right, rear left, rear right.
- Discovered TPMS sensors with pressure, temperature, and RSSI for easier
  identification.
- Persistent wheel bindings.
- Last-known readings after reboot, shown as `Stale` until fresh data arrives.

## Requirements

- Venus OS / GX device with SSH access.
- A USB Bluetooth adapter supported by BlueZ.
- BLE TPMS sensors that advertise compatible manufacturer data.

Before installing, make sure Bluetooth is enabled in the GX settings if your
device exposes that option.

## Quick Install

[Enable SSH / root access on the GX device](https://www.victronenergy.com/live/ccgx:root_access),
SSH into it, then run:

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/install.sh | sh
```

The installer starts the background scanner, adds the `TPMS` page to the GX UI,
and restarts the GX UI so the new menu is loaded. It does not reboot the whole
GX device. Runtime files are copied to `/data/venus-tpms-ble`; temporary
download files are cleaned automatically.

Venus OS updates are supported. Because the GX UI files can be replaced by an
OS update, run the same install command once after an update to restore the
`TPMS` menu and its UI integration.

The service does not bind to a specific adapter model or `hci` number. It uses
the lowest-numbered BlueZ adapter that can scan BLE. You can insert or remove a
USB adapter while it is running: scanning pauses while no adapter is present and
automatically resumes when an adapter reappears. Bound wheels retain their last
known readings during that interruption.

## First Setup

1. Open the local GX screen.
2. Go to the device list and open `TPMS`.
3. Wait for discovered sensors to appear.
4. Open a discovered sensor.
5. Set `Wheel` to one of:
   - `Front left`
   - `Front right`
   - `Rear left`
   - `Rear right`
6. Repeat until all sensors are bound.

The discovered list shows pressure, temperature, and RSSI, which helps identify
which sensor is closest or currently active.

Unbound sensors are temporary: they disappear from the discovered list after
five minutes without a new advertisement. Bound wheels retain their last-known
reading and are shown as `Stale` when the sensor stops advertising.

## Display

The device list shows four compact TPMS values, ordered as:

```text
front left / front right / rear left / rear right
```

Values mean:

- `--`: no sensor assigned
- `wait`: sensor assigned, but no reading received since service start
- `6.17`: current pressure in bar
- `6.17*`: stale last-known pressure

Inside the `TPMS` page, each wheel shows pressure, temperature, and state. Open a
wheel to see details such as sensor ID, battery, RSSI, and last seen time.

The same page also shows Bluetooth status and recent BLE activity. `BLE activity
(5 min)` is the number of different BLE devices that advertised during the last
five minutes. `Manufacturer data (5 min)` is the subset that included a
manufacturer-data field. Both values are diagnostic indicators only. If
`Bluetooth` is not `Scanning`, the adapter or BlueZ discovery needs attention.
`BLE receiver` should be `Receiving` while raw advertisements are arriving; the
service automatically recreates that receiver if it closes.

## Check Status

To check whether the service is running:

```sh
ps w | grep venus-tpms-ble.py | grep -v grep
```

To check the D-Bus status:

```sh
dbus-send --system --print-reply \
  --dest=com.victronenergy.tpms.main \
  /StatusText \
  com.victronenergy.BusItem.GetValue
```

Expected value while scanning:

```text
Scanning
```

## Troubleshooting

If no sensors appear:

1. Confirm the USB Bluetooth adapter is detected.
2. Confirm the service status is `Scanning`.
3. Move the TPMS sensors closer to the GX device.
4. Wait a few minutes; some TPMS sensors advertise infrequently.
5. Wake the sensors by moving the vehicle or changing tire pressure slightly.

The service automatically restarts BlueZ discovery if scanning is stopped by
another process.

If the `TPMS` menu does not appear immediately after install, restart the GX UI
or reboot the GX device.

For debug output:

```sh
svc -d /service/venus-tpms-ble
VENUS_TPMS_DEBUG=1 python3 /data/venus-tpms-ble/venus-tpms-ble.py
```

Stop debug mode with `Ctrl-C`, then restart the service:

```sh
svc -u /service/venus-tpms-ble
```

## Update

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/install.sh | sh
```

## Uninstall

```sh
wget -O - https://raw.githubusercontent.com/jkqq147/venus-tpms-ble/master/uninstall.sh | sh
```

The uninstaller stops the service, removes the TPMS UI pages, restores
`PageMain.qml` from backup when available, and restarts the GX UI.

## Notes

- Wheel bindings are stored in Venus settings.
- Only bound wheels persist last-known readings.
- Unbound discovered sensors are not persisted across reboot.
- Logs are disabled by default to avoid filling limited device storage.

## Development

The installed service publishes:

```text
com.victronenergy.tpms.main
```

Run the scanner manually during development:

```sh
python3 service/venus-tpms-ble.py
```

Run mock data for UI development:

```sh
python3 tools/mock_tpms_dbus.py
```

Protocol parsing should stay aligned with the `tpms-ble-parser` project. The
Venus service owns BlueZ scanning, D-Bus publishing, GUI integration, binding
state, stale handling, and install/uninstall behavior.
