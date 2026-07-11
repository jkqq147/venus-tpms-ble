# venus-tpms-ble

Venus OS / CCGX integration for BLE TPMS sensors.

The project installs a Venus-native Python service and a GX GUI page:

- scans BLE advertisements through BlueZ D-Bus;
- parses TPMS manufacturer data;
- publishes `com.victronenergy.tpms.main`;
- stores wheel bindings in Venus settings;
- shows TPMS readings in the local GX/GGCX UI.

## Install

Copy this repository to the Venus OS device, then run:

```sh
sh scripts/install.sh
```

The installer:

- copies the TPMS service to `/data/venus-tpms-ble/venus-tpms-ble.py`;
- installs `PageTpms.qml`, `PageTpmsWheel.qml`, and `PageTpmsBind.qml`;
- patches `PageMain.qml` to add a `TPMS` menu item;
- backs up the original `PageMain.qml` under `/data/venus-tpms-ble/backups`;
- creates `/service/venus-tpms-ble` for Venus runit supervision;
- restarts the GX GUI.

After install, open the GX/GGCX `TPMS` page. Discovered sensors appear by their
advertised name, for example `TPMS2_225C0A`. Select a discovered sensor and bind
it to a wheel. The main device list shows four separate TPMS value blocks in
wheel order: front left, front right, rear left, rear right.

## Uninstall

```sh
sh scripts/uninstall.sh
```

The uninstaller stops the service, removes the TPMS GUI pages, restores
`PageMain.qml` from the latest backup when available, and restarts the GUI.

## Data Model

The service publishes:

```text
com.victronenergy.tpms.main
```

Discovered sensors:

```text
/Discovered/0/Name
/Discovered/0/SensorId
/Discovered/0/AssignedWheel
/Discovered/0/Pressure
/Discovered/0/PressureDisplay
/Discovered/0/Temperature
/Discovered/0/TemperatureDisplay
/Discovered/0/Battery
/Discovered/0/Rssi
/Discovered/0/RssiDisplay
/Discovered/0/LastSeen
/Discovered/0/ManufacturerData
```

The service keeps up to 10 discovered TPMS sensors visible. The list is sorted
by RSSI so stronger nearby sensors appear first; empty rows are hidden in the
GUI. Discovered rows show pressure, temperature, and RSSI to make binding easier.
Already-bound sensors are kept in the discovered list when possible and are
always available through `/Slots/*`.

Wheel slots:

```text
/Slots/front_left/StateText
/Slots/front_left/SensorId
/Slots/front_left/Pressure
/Slots/front_left/PressureDisplay
/Slots/front_left/Temperature
/Slots/front_left/TemperatureDisplay
/Slots/front_left/Battery
/Slots/front_left/Rssi
/Slots/front_left/Summary
/Slots/front_left/DeviceListValue
```

`/Slots/*` only shows bound sensors. Unbound wheels show `Unassigned`. The main
TPMS page shows each wheel's pressure, temperature, and state in the native
Venus list style; opening a wheel shows the full details.

The device-list TPMS entry uses `/Slots/*/DeviceListValue` for four separate
value blocks, for example:

```text
--  wait  --  --
```

`--` means unassigned, `wait` means bound but not yet seen, and `*` marks a
stale last-known pressure.

Bindings are persisted in Venus settings:

```text
/Settings/Tpms/FrontLeftSensorId
/Settings/Tpms/FrontRightSensorId
/Settings/Tpms/RearLeftSensorId
/Settings/Tpms/RearRightSensorId
```

The last real reading for each bound wheel is also persisted. After a reboot,
if a bound sensor has not advertised yet, the slot shows the last known reading
as `Stale` instead of presenting it as live data. If there is no stored reading
for that binding, the slot shows `Waiting` until the first advertisement is
received.

The GUI writes `/Discovered/<n>/AssignedWheel`; the service enforces one-to-one
binding and updates Venus settings.

## Development

Run the real scanner manually:

```sh
python3 service/venus-tpms-ble.py
```

For GUI development without waiting for BLE advertisements, use the mock helper:

```sh
python3 tools/mock_tpms_dbus.py
```

Protocol parsing should stay aligned with the `tpms-ble-parser` project. The
Venus service owns BlueZ scanning, D-Bus publishing, GUI integration, binding
state, stale handling, and install/uninstall behavior.

The installed service discards stdout/stderr by default to avoid filling limited
storage. For debugging, stop the service and run it manually:

```sh
svc -d /service/venus-tpms-ble
VENUS_TPMS_DEBUG=1 python3 /data/venus-tpms-ble/venus-tpms-ble.py
```
