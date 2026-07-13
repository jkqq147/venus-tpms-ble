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

The TPMS home page is deliberately limited to four wheel rows, `Discover
sensors`, and `Diagnostics`. The home page shows pressure and temperature only;
sensor metadata and BLE scanner diagnostics are available in their respective
subpages.

The device list shows wheels in this order:

```text
front left / front right / rear left / rear right
```

- `--`: no sensor is assigned.
- `wait`: a sensor is assigned but no reading has arrived since service start.
- `6.17`: current pressure in bar.
- `6.17*`: last-known pressure; the reading is stale.

Unbound discoveries expire after five minutes without another advertisement.
Only wheel-to-sensor bindings are stored. Live pressure, temperature, signal,
and last-seen values remain in memory and are never written to flash. After a
restart, a bound wheel shows `wait` until its next advertisement arrives. A
reading becomes `Stale` when a fresh advertisement is overdue during the same
service session.

## Bluetooth Status

The TPMS page reports `Bluetooth`, `BLE receiver`, `BLE activity (60 sec)`, and
`Manufacturer data (60 sec)`.

- `Bluetooth` should be `Scanning`.
- Without an adapter it remains available and reports `No Bluetooth adapter`.
- `BLE receiver` should be `Receiving` while raw advertisements arrive.
- The two activity counts are recent distinct BLE devices and the subset with
  manufacturer data. They are diagnostics, not the number of configured tires.

The service uses the lowest-numbered usable BlueZ adapter. It does not bind to a
specific USB model or `hci` number. Removing an adapter pauses scanning; adding
one back resumes it in the same service process. Some TPMS sensors advertise infrequently, so
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
/data/venus-tpms-ble/venus-tpms-ble
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

The native Rust service publishes `com.victronenergy.tpms.main` on D-Bus. Build
the static ARMv7 binary with:

```sh
rustup target add armv7-unknown-linux-musleabihf
sh scripts/build-armv7.sh
```

Protocol parsing belongs in `tpms-ble-parser`; this repository owns Venus BLE
scanning, D-Bus publishing, UI integration, bindings, stale handling, and
installation.
