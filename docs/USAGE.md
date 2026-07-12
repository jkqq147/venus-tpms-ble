# TPMS Detailed Guide

[中文说明](USAGE.zh-CN.md)

## Requirements

- A Venus OS / GX device with SSH root access.
- A USB Bluetooth adapter supported by BlueZ.
- TPMS sensors that advertise compatible BLE manufacturer data.

Enable Bluetooth in GX settings when the device exposes that option.

## Installer Behavior

The installer reports the Venus OS version and UI profile before changing
anything. Enter `n` at the first prompt to exit without changes.

Entering `y` starts a protected 10-minute trial. It temporarily adds the UI and
scanner, then reloads the GX UI. Enter `CONFIRM` in the SSH terminal to make it
permanent. Any other input, a GUI crash loop, timeout, or reboot restores the
previous UI.

The permanent runtime is stored in `/data/venus-tpms-ble`. Normal reboots start
it automatically. A Venus OS update replaces GX UI files under `/opt`; rerun the
install command after every update to restore the TPMS menu.

## Binding and Readings

`Discovered` shows recently received, unbound TPMS sensors. Open a sensor and
choose one of `Front left`, `Front right`, `Rear left`, or `Rear right`.

The device list shows wheels in this order:

```text
front left / front right / rear left / rear right
```

- `--`: no sensor is assigned.
- `wait`: a sensor is assigned but no reading has arrived since service start.
- `6.17`: current pressure in bar.
- `6.17*`: last-known pressure; the reading is stale.

Unbound discoveries expire after five minutes without another advertisement.
Bound wheels keep their last reading across restarts and become `Stale` when a
fresh advertisement is overdue.

## Bluetooth Status

The TPMS page reports `Bluetooth`, `BLE receiver`, `BLE activity (5 min)`, and
`Manufacturer data (5 min)`.

- `Bluetooth` should be `Scanning`.
- `BLE receiver` should be `Receiving` while raw advertisements arrive.
- The two activity counts are recent distinct BLE devices and the subset with
  manufacturer data. They are diagnostics, not the number of configured tires.

The service uses the lowest-numbered usable BlueZ adapter. It does not bind to a
specific USB model or `hci` number. Removing an adapter pauses scanning; adding
one back resumes it automatically. Some TPMS sensors advertise infrequently, so
allow a few minutes and move the sensor closer before concluding that it is not
being received.

## Check and Debug

Service status:

```sh
dbus-send --system --print-reply \
  --dest=com.victronenergy.tpms.main \
  /StatusText \
  com.victronenergy.BusItem.GetValue
```

Expected output during normal scanning:

```text
Scanning
```

For foreground debug output:

```sh
svc -d /service/venus-tpms-ble
VENUS_TPMS_DEBUG=1 python3 /data/venus-tpms-ble/venus-tpms-ble.py
```

Stop it with `Ctrl-C`, then restart the managed service:

```sh
svc -u /service/venus-tpms-ble
```

Logs are disabled by default to avoid filling limited GX storage.

## Uninstall

The uninstall command stops TPMS, removes only its marked startup entry, restores
`PageMain.qml` from backup when available, removes the TPMS QML pages, and reloads
the GX UI. It does not alter unrelated startup commands.

## Development

The service publishes `com.victronenergy.tpms.main` on D-Bus. Run it locally for
development with:

```sh
python3 service/venus-tpms-ble.py
```

For mock UI data:

```sh
python3 tools/mock_tpms_dbus.py
```

Protocol parsing belongs in `tpms-ble-parser`; this repository owns Venus BLE
scanning, D-Bus publishing, UI integration, bindings, stale handling, and
installation.
