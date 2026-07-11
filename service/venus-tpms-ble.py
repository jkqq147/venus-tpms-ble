#!/usr/bin/env python3
"""Scan TPMS BLE advertisements through BlueZ and publish them on Venus D-Bus."""

import argparse
import json
import os
import signal
import sys
import time

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


VELIB_PATHS = (
    "/opt/victronenergy/dbus-systemcalc-py/ext/velib_python",
    "/opt/victronenergy/dbus-tempsensor-relay/ext/velib_python",
)

for path in VELIB_PATHS:
    if os.path.exists(os.path.join(path, "vedbus.py")):
        sys.path.insert(1, path)
        break

from settingsdevice import SettingsDevice  # noqa: E402
from vedbus import VeDbusService  # noqa: E402


SOFTWARE_VERSION = "0.1.0"
TPMS_SERVICE_NAME = "com.victronenergy.tpms.main"
SETTINGS_PREFIX = "/Settings/Tpms"
UNASSIGNED = "unassigned"
DISCOVERED_LIMIT = 10
LAST_READING_PERSIST_INTERVAL_SECONDS = 60

WHEELS = (
    ("front_left", "FrontLeft", "Front left"),
    ("front_right", "FrontRight", "Front right"),
    ("rear_left", "RearLeft", "Rear left"),
    ("rear_right", "RearRight", "Rear right"),
)


def debug(message):
    if os.environ.get("VENUS_TPMS_DEBUG"):
        print(message, file=sys.stderr, flush=True)


def bytes_from_dbus_array(value):
    return bytes(int(item) & 0xFF for item in value)


def parse_tpms_manufacturer_data(data):
    if len(data) != 18 or data[0:2] != b"\x00\x01":
        return None

    payload = data[2:]
    pressure_raw = int.from_bytes(payload[6:10], "little")
    temperature_raw = int.from_bytes(payload[10:12], "little")
    return {
        "manufacturer_id": 0x0100,
        "sensor_id": payload[0:6].hex().upper(),
        "pressure_bar": round(pressure_raw * 0.00001, 3),
        "temperature_c": round(temperature_raw / 100.0, 1),
        "battery_percent": int(payload[14]),
        "alarm": int(payload[15]),
        "manufacturer_data_hex": data.hex().upper(),
    }


class TpmsBluezService:
    def __init__(self, stale_seconds):
        self.stale_seconds = stale_seconds
        self.bus = dbus.SystemBus()
        self.settings = None
        self.adapter_path = None
        self.adapter = None
        self.adapter_properties = None
        self.discovery_started = False
        self.readings_by_sensor_id = {}
        self.discovered_order = []
        self.last_persisted_by_wheel = {}
        self.last_persisted_signature_by_wheel = {}

        self.service = VeDbusService(TPMS_SERVICE_NAME, register=False)
        self.service.add_mandatory_paths(
            processname=__file__,
            processversion=SOFTWARE_VERSION,
            connection="bluez",
            deviceinstance=0,
            productid=0,
            productname="TPMS BLE",
            firmwareversion=SOFTWARE_VERSION,
            hardwareversion=None,
            connected=1,
        )
        self.service.add_path("/Status", 0)
        self.service.add_path("/StatusText", "Starting")
        self.service.add_path("/DiscoveredCount", 0)
        self.service.add_path("/Overview", "FL --  FR -- / RL --  RR --")
        self.service.add_path("/Bluetooth/StatusText", "Starting")
        self.service.add_path("/Bluetooth/Adapter", "")
        self.service.add_path("/Bluetooth/Discovering", 0)
        self.service.add_path("/Bluetooth/DeviceCount", 0)
        self.service.add_path("/Bluetooth/ManufacturerDataCount", 0)

        self._ensure_settings()
        self._add_slot_paths()
        self._add_discovered_paths()
        self.service.register()
        self._update_slots()

        self._connect_bluez()
        self._start_discovery()

    def _ensure_settings(self):
        settings = {}
        for wheel_key, setting_key, _ in WHEELS:
            settings[wheel_key] = [f"{SETTINGS_PREFIX}/{setting_key}SensorId", "", "", "", True]
            settings[self._last_reading_key(wheel_key)] = [
                f"{SETTINGS_PREFIX}/{setting_key}LastReading",
                "",
                "",
                "",
                True,
            ]
        self.settings = SettingsDevice(self.bus, settings, self._setting_changed, timeout=10)

    def _add_slot_paths(self):
        for wheel_key, _, wheel_label in WHEELS:
            root = self._slot_root(wheel_key)
            self.service.add_path(f"{root}/Wheel", wheel_key)
            self.service.add_path(f"{root}/Name", wheel_label)
            self.service.add_path(f"{root}/SensorId", "")
            self.service.add_path(f"{root}/Pressure", None)
            self.service.add_path(f"{root}/Temperature", None)
            self.service.add_path(f"{root}/Battery", None)
            self.service.add_path(f"{root}/Rssi", None)
            self.service.add_path(f"{root}/LastSeen", None)
            self.service.add_path(f"{root}/State", UNASSIGNED)
            self.service.add_path(f"{root}/StateText", "Unassigned")
            self.service.add_path(f"{root}/Summary", "Unassigned")
            self.service.add_path(f"{root}/DeviceListValue", "--")
            self.service.add_path(f"{root}/PressureDisplay", "--")
            self.service.add_path(f"{root}/TemperatureDisplay", "--")

    def _add_discovered_paths(self):
        for index in range(DISCOVERED_LIMIT):
            root = self._discovered_root(index)
            self.service.add_path(f"{root}/Name", "")
            self.service.add_path(f"{root}/SensorId", "")
            self.service.add_path(
                f"{root}/AssignedWheel",
                UNASSIGNED,
                writeable=True,
                onchangecallback=self._assigned_wheel_changed,
            )
            self.service.add_path(f"{root}/Pressure", None)
            self.service.add_path(f"{root}/PressureDisplay", "--")
            self.service.add_path(f"{root}/Temperature", None)
            self.service.add_path(f"{root}/TemperatureDisplay", "--")
            self.service.add_path(f"{root}/Battery", None)
            self.service.add_path(f"{root}/Rssi", None)
            self.service.add_path(f"{root}/RssiDisplay", "--")
            self.service.add_path(f"{root}/LastSeen", None)
            self.service.add_path(f"{root}/ManufacturerData", "")

    @staticmethod
    def _slot_root(wheel_key):
        return f"/Slots/{wheel_key}"

    @staticmethod
    def _discovered_root(index):
        return f"/Discovered/{index}"

    @staticmethod
    def _sensor_name(reading):
        name = reading.get("name") or ""
        if name.startswith("TPMS"):
            return name
        return "TPMS_" + reading["sensor_id"][-6:]

    @staticmethod
    def _last_reading_key(wheel_key):
        return f"{wheel_key}_last_reading"

    def _connect_bluez(self):
        manager = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objects = manager.GetManagedObjects()
        for path, ifaces in objects.items():
            if "org.bluez.Adapter1" in ifaces:
                self.adapter_path = path
                break
        if self.adapter_path is None:
            self.service["/Bluetooth/StatusText"] = "No adapter"
            raise RuntimeError("No BlueZ adapter found")

        self.adapter = dbus.Interface(self.bus.get_object("org.bluez", self.adapter_path), "org.bluez.Adapter1")
        self.adapter_properties = dbus.Interface(
            self.bus.get_object("org.bluez", self.adapter_path),
            "org.freedesktop.DBus.Properties",
        )
        self.service["/Bluetooth/Adapter"] = self.adapter_path
        self._update_bluetooth_counts(objects)
        self.bus.add_signal_receiver(
            self._interfaces_added,
            dbus_interface="org.freedesktop.DBus.ObjectManager",
            signal_name="InterfacesAdded",
        )
        self.bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path_keyword="path",
        )
        for path, ifaces in objects.items():
            props = ifaces.get("org.bluez.Device1")
            if props:
                self._handle_device(path, props)

    def _start_discovery(self):
        self.adapter.SetDiscoveryFilter({"Transport": dbus.String("le"), "DuplicateData": dbus.Boolean(True)})
        self.adapter.StartDiscovery()
        self.discovery_started = True
        self.service["/Status"] = 0
        self.service["/StatusText"] = "Scanning"
        self.service["/Bluetooth/StatusText"] = "Scanning"
        self.service["/Bluetooth/Discovering"] = 1

    def _ensure_discovery(self):
        if self.adapter is None:
            return
        try:
            discovering = bool(self.adapter_properties.Get("org.bluez.Adapter1", "Discovering"))
            objects = dbus.Interface(
                self.bus.get_object("org.bluez", "/"),
                "org.freedesktop.DBus.ObjectManager",
            ).GetManagedObjects()
        except Exception as exc:
            self.service["/Status"] = 2
            self.service["/StatusText"] = "BlueZ unavailable"
            self.service["/Bluetooth/StatusText"] = "Unavailable"
            self.service["/Bluetooth/Discovering"] = 0
            debug(f"Discovering check failed: {exc}")
            return
        self._update_bluetooth_counts(objects)
        if discovering:
            self.service["/Status"] = 0
            self.service["/StatusText"] = "Scanning"
            self.service["/Bluetooth/StatusText"] = "Scanning"
            self.service["/Bluetooth/Discovering"] = 1
            return
        try:
            self._start_discovery()
            debug("Restarted BlueZ discovery")
        except Exception as exc:
            self.service["/Status"] = 2
            self.service["/StatusText"] = "Scan stopped"
            self.service["/Bluetooth/StatusText"] = "Scan stopped"
            self.service["/Bluetooth/Discovering"] = 0
            debug(f"StartDiscovery failed: {exc}")

    def _update_bluetooth_counts(self, objects):
        device_count = 0
        manufacturer_data_count = 0
        for _path, ifaces in objects.items():
            props = ifaces.get("org.bluez.Device1")
            if props is None:
                continue
            device_count += 1
            if props.get("ManufacturerData"):
                manufacturer_data_count += 1
        self.service["/Bluetooth/DeviceCount"] = device_count
        self.service["/Bluetooth/ManufacturerDataCount"] = manufacturer_data_count

    def _interfaces_added(self, path, ifaces):
        props = ifaces.get("org.bluez.Device1")
        if props:
            self._handle_device(path, props)

    def _properties_changed(self, interface, changed, _invalidated, path=None):
        if interface == "org.bluez.Device1":
            self._handle_device(path, changed)

    def _handle_device(self, path, props):
        mfg = props.get("ManufacturerData")
        if not mfg:
            return

        address = str(props.get("Address", path.rsplit("/", 1)[-1]))
        name = str(props.get("Name") or props.get("Alias") or "")
        rssi = props.get("RSSI")
        now = int(time.time())

        for company, payload in mfg.items():
            manufacturer_data = int(company).to_bytes(2, "little") + bytes_from_dbus_array(payload)
            parsed = parse_tpms_manufacturer_data(manufacturer_data)
            if parsed is None:
                continue
            parsed.update({
                "address": address,
                "name": name,
                "rssi": int(rssi) if rssi is not None else None,
                "last_seen": now,
            })
            self._update_reading(parsed)

    def _update_reading(self, reading):
        sensor_id = reading["sensor_id"]
        self.readings_by_sensor_id[sensor_id] = reading
        self._persist_bound_reading(reading)
        self._refresh_discovered_order()
        self._update_discovered_paths()
        self._update_slots()

    def _persist_bound_reading(self, reading):
        now = int(time.time())
        signature = (
            reading["sensor_id"],
            reading["pressure_bar"],
            reading["temperature_c"],
            reading["battery_percent"],
            reading["alarm"],
            reading["manufacturer_data_hex"],
        )
        payload = {
            "sensor_id": reading["sensor_id"],
            "name": self._sensor_name(reading),
            "pressure_bar": reading["pressure_bar"],
            "temperature_c": reading["temperature_c"],
            "battery_percent": reading["battery_percent"],
            "alarm": reading["alarm"],
            "rssi": reading["rssi"],
            "last_seen": reading["last_seen"],
            "manufacturer_data_hex": reading["manufacturer_data_hex"],
        }
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        for wheel_key, _, _ in WHEELS:
            if self.settings[wheel_key] != reading["sensor_id"]:
                continue
            last_persisted = self.last_persisted_by_wheel.get(wheel_key, 0)
            last_signature = self.last_persisted_signature_by_wheel.get(wheel_key)
            if (
                last_signature == signature
                and now - last_persisted < LAST_READING_PERSIST_INTERVAL_SECONDS
            ):
                continue
            self.settings[self._last_reading_key(wheel_key)] = encoded
            self.last_persisted_by_wheel[wheel_key] = now
            self.last_persisted_signature_by_wheel[wheel_key] = signature

    def _refresh_discovered_order(self):
        bound_sensor_ids = {
            self.settings[wheel_key]
            for wheel_key, _, _ in WHEELS
            if self.settings[wheel_key]
        }

        def sort_key(sensor_id):
            reading = self.readings_by_sensor_id[sensor_id]
            rssi = reading["rssi"] if reading["rssi"] is not None else -999
            return (rssi, reading["last_seen"])

        sorted_sensor_ids = sorted(
            self.readings_by_sensor_id.keys(),
            key=sort_key,
            reverse=True,
        )
        selected = sorted_sensor_ids[:DISCOVERED_LIMIT]
        for sensor_id in bound_sensor_ids:
            if sensor_id not in self.readings_by_sensor_id or sensor_id in selected:
                continue
            if len(selected) < DISCOVERED_LIMIT:
                selected.append(sensor_id)
                continue
            for replace_index in range(len(selected) - 1, -1, -1):
                if selected[replace_index] not in bound_sensor_ids:
                    selected[replace_index] = sensor_id
                    break

        self.discovered_order = sorted(selected, key=sort_key, reverse=True)
        self.service["/DiscoveredCount"] = len(self.discovered_order)

    def _update_discovered_paths(self):
        for index in range(DISCOVERED_LIMIT):
            root = self._discovered_root(index)
            if index >= len(self.discovered_order):
                self.service[f"{root}/Name"] = ""
                self.service[f"{root}/SensorId"] = ""
                self.service[f"{root}/AssignedWheel"] = UNASSIGNED
                self.service[f"{root}/Pressure"] = None
                self.service[f"{root}/PressureDisplay"] = "--"
                self.service[f"{root}/Temperature"] = None
                self.service[f"{root}/TemperatureDisplay"] = "--"
                self.service[f"{root}/Battery"] = None
                self.service[f"{root}/Rssi"] = None
                self.service[f"{root}/RssiDisplay"] = "--"
                self.service[f"{root}/LastSeen"] = None
                self.service[f"{root}/ManufacturerData"] = ""
                continue

            sensor_id = self.discovered_order[index]
            reading = self.readings_by_sensor_id[sensor_id]
            self._update_discovered_path(root, sensor_id, reading)

    def _update_discovered_path(self, root, sensor_id, reading):
        self.service[f"{root}/Name"] = self._sensor_name(reading)
        self.service[f"{root}/SensorId"] = sensor_id
        self.service[f"{root}/AssignedWheel"] = self._assigned_wheel_for_sensor(sensor_id)
        self.service[f"{root}/Pressure"] = reading["pressure_bar"]
        self.service[f"{root}/PressureDisplay"] = f"{reading['pressure_bar']:.2f}"
        self.service[f"{root}/Temperature"] = reading["temperature_c"]
        self.service[f"{root}/TemperatureDisplay"] = f"{reading['temperature_c']:.1f}C"
        self.service[f"{root}/Battery"] = reading["battery_percent"]
        self.service[f"{root}/Rssi"] = reading["rssi"]
        self.service[f"{root}/RssiDisplay"] = f"{reading['rssi']}dB" if reading["rssi"] is not None else "--"
        self.service[f"{root}/LastSeen"] = reading["last_seen"]
        self.service[f"{root}/ManufacturerData"] = reading["manufacturer_data_hex"]

    def _update_slots(self):
        now = int(time.time())
        for wheel_key, _, wheel_label in WHEELS:
            root = self._slot_root(wheel_key)
            sensor_id = self.settings[wheel_key]
            reading = self.readings_by_sensor_id.get(sensor_id)
            if not sensor_id:
                self._clear_slot(root, wheel_label, "Unassigned", UNASSIGNED)
                continue
            if reading is None:
                last_reading = self._load_last_reading(wheel_key, sensor_id)
                if last_reading is None:
                    self._clear_slot(root, wheel_label, "Waiting", "waiting")
                    self.service[f"{root}/SensorId"] = sensor_id
                    continue
                self._update_slot(root, sensor_id, last_reading, "stale", "Stale")
                continue
            if now - reading["last_seen"] > self.stale_seconds:
                state = "stale"
                state_text = "Stale"
            else:
                state = "ok"
                state_text = "OK"
            self._update_slot(root, sensor_id, reading, state, state_text)
        self._update_overview()

    def _load_last_reading(self, wheel_key, sensor_id):
        raw = self.settings[self._last_reading_key(wheel_key)]
        if not raw:
            return None
        try:
            reading = json.loads(str(raw))
        except (TypeError, ValueError):
            return None
        if reading.get("sensor_id") != sensor_id:
            return None

        required = ("pressure_bar", "temperature_c", "battery_percent", "last_seen")
        if any(reading.get(key) is None for key in required):
            return None
        return {
            "sensor_id": sensor_id,
            "name": str(reading.get("name") or ""),
            "pressure_bar": float(reading["pressure_bar"]),
            "temperature_c": float(reading["temperature_c"]),
            "battery_percent": int(reading["battery_percent"]),
            "alarm": int(reading.get("alarm", 0)),
            "rssi": int(reading["rssi"]) if reading.get("rssi") is not None else None,
            "last_seen": int(reading["last_seen"]),
            "manufacturer_data_hex": str(reading.get("manufacturer_data_hex") or ""),
        }

    def _update_slot(self, root, sensor_id, reading, state, state_text):
        self.service[f"{root}/Name"] = self._sensor_name(reading)
        self.service[f"{root}/SensorId"] = sensor_id
        self.service[f"{root}/Pressure"] = reading["pressure_bar"]
        self.service[f"{root}/Temperature"] = reading["temperature_c"]
        self.service[f"{root}/Battery"] = reading["battery_percent"]
        self.service[f"{root}/Rssi"] = reading["rssi"]
        self.service[f"{root}/LastSeen"] = reading["last_seen"]
        self.service[f"{root}/State"] = state
        self.service[f"{root}/StateText"] = state_text
        self.service[f"{root}/Summary"] = self._slot_summary(reading, state_text)
        self.service[f"{root}/DeviceListValue"] = self._device_list_value(reading, state)
        self.service[f"{root}/PressureDisplay"] = f"{reading['pressure_bar']:.2f}"
        self.service[f"{root}/TemperatureDisplay"] = f"{reading['temperature_c']:.1f}C"

    def _clear_slot(self, root, wheel_label, state_text, state):
        self.service[f"{root}/Name"] = wheel_label
        self.service[f"{root}/SensorId"] = ""
        self.service[f"{root}/Pressure"] = None
        self.service[f"{root}/Temperature"] = None
        self.service[f"{root}/Battery"] = None
        self.service[f"{root}/Rssi"] = None
        self.service[f"{root}/LastSeen"] = None
        self.service[f"{root}/State"] = state
        self.service[f"{root}/StateText"] = state_text
        self.service[f"{root}/Summary"] = state_text
        self.service[f"{root}/DeviceListValue"] = "wait" if state == "waiting" else "--"
        self.service[f"{root}/PressureDisplay"] = "--"
        self.service[f"{root}/TemperatureDisplay"] = "--"

    @staticmethod
    def _slot_summary(reading, state_text):
        pressure = f"{reading['pressure_bar']:.2f} bar"
        temperature = f"{reading['temperature_c']:.1f} C"
        battery = f"{reading['battery_percent']}%"
        if state_text == "OK":
            return f"{pressure}, {temperature}, {battery}"
        return f"{state_text}: {pressure}, {temperature}, {battery}"

    def _update_overview(self):
        self.service["/Overview"] = (
            f"FL {self._overview_value('front_left')}  "
            f"FR {self._overview_value('front_right')} / "
            f"RL {self._overview_value('rear_left')}  "
            f"RR {self._overview_value('rear_right')}"
        )

    def _overview_value(self, wheel_key):
        root = self._slot_root(wheel_key)
        return self.service[f"{root}/DeviceListValue"]

    @staticmethod
    def _device_list_value(reading, state):
        pressure = f"{reading['pressure_bar']:.2f}"
        if state == "stale":
            return pressure + "*"
        return pressure

    def _setting_changed(self, setting, _oldvalue, newvalue):
        wheel_keys = [wheel_key for wheel_key, _, _ in WHEELS]
        if setting not in wheel_keys:
            self._update_slots()
            return
        self._enforce_unique_binding(setting, newvalue)
        if not newvalue:
            self.settings[self._last_reading_key(setting)] = ""
        self._refresh_discovered_order()
        self._update_discovered_assignments()
        self._update_slots()

    def _enforce_unique_binding(self, target_wheel, sensor_id):
        if not sensor_id:
            return
        for wheel_key, _, _ in WHEELS:
            if wheel_key != target_wheel and self.settings[wheel_key] == sensor_id:
                self.settings[wheel_key] = ""

    def _assigned_wheel_changed(self, path, newvalue):
        try:
            index = int(path.split("/")[2])
        except (IndexError, ValueError):
            return False
        if index < 0 or index >= len(self.discovered_order):
            return False
        wheel = str(newvalue) or UNASSIGNED
        sensor_id = self.discovered_order[index]
        self._clear_sensor_binding(sensor_id)
        if wheel != UNASSIGNED:
            valid_wheels = [wheel_key for wheel_key, _, _ in WHEELS]
            if wheel not in valid_wheels:
                return False
            self.settings[wheel] = sensor_id
        self._refresh_discovered_order()
        self._update_discovered_assignments()
        self._update_slots()
        return True

    def _clear_sensor_binding(self, sensor_id):
        for wheel_key, _, _ in WHEELS:
            if self.settings[wheel_key] == sensor_id:
                self.settings[wheel_key] = ""

    def _assigned_wheel_for_sensor(self, sensor_id):
        for wheel_key, _, _ in WHEELS:
            if self.settings[wheel_key] == sensor_id:
                return wheel_key
        return UNASSIGNED

    def _update_discovered_assignments(self):
        self._refresh_discovered_order()
        for index, sensor_id in enumerate(self.discovered_order):
            self.service[f"{self._discovered_root(index)}/AssignedWheel"] = self._assigned_wheel_for_sensor(sensor_id)

    def tick(self):
        self._ensure_discovery()
        self._update_slots()
        return True

    def stop(self):
        self.service["/Connected"] = 0
        if self.discovery_started:
            try:
                self.adapter.StopDiscovery()
            except Exception as exc:
                debug(f"StopDiscovery failed: {exc}")


def parse_args():
    parser = argparse.ArgumentParser(description="Publish real TPMS values from BlueZ BLE discovery")
    parser.add_argument("--stale-seconds", type=int, default=300)
    return parser.parse_args()


def main():
    args = parse_args()
    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    service = TpmsBluezService(args.stale_seconds)

    def stop(*_args):
        service.stop()
        loop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    GLib.timeout_add_seconds(30, service.tick)
    print(f"publishing {TPMS_SERVICE_NAME}; press Ctrl-C to stop", flush=True)
    loop.run()


if __name__ == "__main__":
    main()
