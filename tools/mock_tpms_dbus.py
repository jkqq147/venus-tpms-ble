#!/usr/bin/env python3
"""Publish mock TPMS readings on Venus OS D-Bus.

This is a development helper. It does not scan Bluetooth and does not install
anything permanently; run it manually on Venus OS while developing UI and D-Bus
integration.
"""

import argparse
import math
import os
import signal
import sys
import time

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

from vedbus import VeDbusService  # noqa: E402
from settingsdevice import SettingsDevice  # noqa: E402


SOFTWARE_VERSION = "0.1.0"
TPMS_SERVICE_NAME = "com.victronenergy.tpms.mock0"
SETTINGS_PREFIX = "/Settings/Tpms"
UNASSIGNED = "unassigned"
WHEELS = (
    ("front_left", "FrontLeft", "Front left"),
    ("front_right", "FrontRight", "Front right"),
    ("rear_left", "RearLeft", "Rear left"),
    ("rear_right", "RearRight", "Rear right"),
)


def debug(message):
    if os.environ.get("VENUS_TPMS_DEBUG"):
        print(message, file=sys.stderr, flush=True)

MOCK_TIRES = (
    {
        "index": 0,
        "position": "front_left",
        "sensor_id": "80EACA125D3B",
        "pressure_bar": 6.05,
        "temperature_c": 31.8,
        "battery_percent": 100,
        "rssi": -78,
    },
    {
        "index": 1,
        "position": "front_right",
        "sensor_id": "81EACA225C0A",
        "pressure_bar": 6.19,
        "temperature_c": 32.6,
        "battery_percent": 100,
        "rssi": -81,
    },
    {
        "index": 2,
        "position": "rear_left",
        "sensor_id": "82EACA325EEB",
        "pressure_bar": 6.13,
        "temperature_c": 32.5,
        "battery_percent": 100,
        "rssi": -84,
    },
    {
        "index": 3,
        "position": "rear_right",
        "sensor_id": "83EACA425D11",
        "pressure_bar": 6.08,
        "temperature_c": 31.9,
        "battery_percent": 100,
        "rssi": -86,
    },
)


class MockTpmsService:
    def __init__(self, interval_seconds):
        self.interval_seconds = interval_seconds
        self.started_at = time.time()
        self.settings = None
        self.readings_by_sensor_id = {}
        self.service = VeDbusService(TPMS_SERVICE_NAME, register=False)
        self.service.add_mandatory_paths(
            processname=__file__,
            processversion=SOFTWARE_VERSION,
            connection="mock",
            deviceinstance=0,
            productid=0,
            productname="Mock TPMS",
            firmwareversion=SOFTWARE_VERSION,
            hardwareversion=None,
            connected=1,
        )
        self.service.add_path("/Status", 0)
        self.service.add_path("/StatusText", "mock data")
        self.service.add_path("/TireCount", len(MOCK_TIRES))
        self.service.add_path("/DiscoveredCount", len(MOCK_TIRES))

        self._ensure_settings()

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

        for tire in MOCK_TIRES:
            root = self._tire_root(tire["index"])
            self.service.add_path(f"{root}/Position", tire["position"])
            self.service.add_path(f"{root}/SensorId", tire["sensor_id"])
            self.service.add_path(f"{root}/Pressure", tire["pressure_bar"])
            self.service.add_path(f"{root}/Temperature", tire["temperature_c"])
            self.service.add_path(f"{root}/Battery", tire["battery_percent"])
            self.service.add_path(f"{root}/Rssi", tire["rssi"])
            self.service.add_path(f"{root}/Alarm", 0)
            self.service.add_path(f"{root}/LastSeen", int(time.time()))

            discovered = self._discovered_root(tire["index"])
            self.service.add_path(f"{discovered}/Name", self._sensor_name(tire))
            self.service.add_path(f"{discovered}/SensorId", tire["sensor_id"])
            self.service.add_path(
                f"{discovered}/AssignedWheel",
                self._assigned_wheel_for_sensor(tire["sensor_id"]),
                writeable=True,
                onchangecallback=self._assigned_wheel_changed,
            )
            self.service.add_path(f"{discovered}/Pressure", tire["pressure_bar"])
            self.service.add_path(f"{discovered}/Temperature", tire["temperature_c"])
            self.service.add_path(f"{discovered}/Battery", tire["battery_percent"])
            self.service.add_path(f"{discovered}/Rssi", tire["rssi"])
            self.service.add_path(f"{discovered}/LastSeen", int(time.time()))

        self.service.register()
        self._update_slots()

    @staticmethod
    def _tire_root(index):
        return f"/Tires/{index}"

    @staticmethod
    def _discovered_root(index):
        return f"/Discovered/{index}"

    @staticmethod
    def _slot_root(wheel_key):
        return f"/Slots/{wheel_key}"

    @staticmethod
    def _sensor_name(tire):
        return "TPMS_" + tire["sensor_id"][-6:]

    def _ensure_settings(self):
        import dbus

        bus = dbus.SystemBus()
        settings = {}
        for wheel_key, setting_key, _ in WHEELS:
            settings[wheel_key] = [f"{SETTINGS_PREFIX}/{setting_key}SensorId", "", "", "", True]
        self.settings = SettingsDevice(bus, settings, self._setting_changed, timeout=10)

    def _setting_changed(self, setting, oldvalue, newvalue):
        self._enforce_unique_binding(setting, newvalue)
        self._update_discovered_assignments()
        self._update_slots()

    def _enforce_unique_binding(self, target_wheel, sensor_id):
        if not sensor_id:
            return
        for wheel_key, _, _ in WHEELS:
            if wheel_key != target_wheel and self.settings[wheel_key] == sensor_id:
                self.settings[wheel_key] = ""

    def _assigned_wheel_changed(self, path, newvalue):
        parts = path.split("/")
        if len(parts) < 3:
            return False
        try:
            sensor_index = int(parts[2])
        except ValueError:
            return False
        if sensor_index < 0 or sensor_index >= len(MOCK_TIRES):
            return False

        wheel = str(newvalue)
        if wheel == "":
            wheel = UNASSIGNED
        sensor_id = MOCK_TIRES[sensor_index]["sensor_id"]
        self._clear_sensor_binding(sensor_id)
        if wheel != UNASSIGNED:
            valid_wheels = [wheel_key for wheel_key, _, _ in WHEELS]
            if wheel not in valid_wheels:
                return False
            self.settings[wheel] = sensor_id
        self._update_discovered_assignments()
        self._update_slots()
        return True

    def _clear_sensor_binding(self, sensor_id):
        for wheel_key, _, _ in WHEELS:
            if self.settings[wheel_key] == sensor_id:
                self.settings[wheel_key] = ""

    def _assigned_wheel_for_sensor(self, sensor_id):
        if self.settings is None:
            return UNASSIGNED
        for wheel_key, _, _ in WHEELS:
            if self.settings[wheel_key] == sensor_id:
                return wheel_key
        return UNASSIGNED

    def _update_discovered_assignments(self):
        for tire in MOCK_TIRES:
            path = f"{self._discovered_root(tire['index'])}/AssignedWheel"
            self.service[path] = self._assigned_wheel_for_sensor(tire["sensor_id"])

    def _update_slots(self):
        for wheel_key, _, wheel_label in WHEELS:
            root = self._slot_root(wheel_key)
            sensor_id = self.settings[wheel_key]
            reading = self.readings_by_sensor_id.get(sensor_id)
            if not sensor_id or reading is None:
                self.service[f"{root}/Name"] = wheel_label
                self.service[f"{root}/SensorId"] = ""
                self.service[f"{root}/Pressure"] = None
                self.service[f"{root}/Temperature"] = None
                self.service[f"{root}/Battery"] = None
                self.service[f"{root}/Rssi"] = None
                self.service[f"{root}/LastSeen"] = None
                self.service[f"{root}/State"] = UNASSIGNED
                self.service[f"{root}/StateText"] = "Unassigned"
                continue

            self.service[f"{root}/Name"] = self._sensor_name(reading)
            self.service[f"{root}/SensorId"] = sensor_id
            self.service[f"{root}/Pressure"] = reading["pressure_bar"]
            self.service[f"{root}/Temperature"] = reading["temperature_c"]
            self.service[f"{root}/Battery"] = reading["battery_percent"]
            self.service[f"{root}/Rssi"] = reading["rssi"]
            self.service[f"{root}/LastSeen"] = reading["last_seen"]
            self.service[f"{root}/State"] = "ok"
            self.service[f"{root}/StateText"] = "OK"

    def update(self):
        elapsed = time.time() - self.started_at
        now = int(time.time())
        with self.service as service:
            for tire in MOCK_TIRES:
                root = self._tire_root(tire["index"])
                wave = math.sin((elapsed / 30.0) + tire["index"])
                pressure_bar = round(tire["pressure_bar"] + wave * 0.03, 3)
                temperature_c = round(tire["temperature_c"] + wave * 0.4, 1)
                rssi = int(tire["rssi"] + wave * 3)
                reading = {
                    "sensor_id": tire["sensor_id"],
                    "pressure_bar": pressure_bar,
                    "temperature_c": temperature_c,
                    "battery_percent": tire["battery_percent"],
                    "rssi": rssi,
                    "last_seen": now,
                }
                self.readings_by_sensor_id[tire["sensor_id"]] = reading
                service[f"{root}/Pressure"] = pressure_bar
                service[f"{root}/Temperature"] = temperature_c
                service[f"{root}/Rssi"] = rssi
                service[f"{root}/LastSeen"] = now
                discovered = self._discovered_root(tire["index"])
                service[f"{discovered}/Pressure"] = pressure_bar
                service[f"{discovered}/Temperature"] = temperature_c
                service[f"{discovered}/Rssi"] = rssi
                service[f"{discovered}/LastSeen"] = now
            self._update_slots()
        return True


def parse_args():
    parser = argparse.ArgumentParser(description="Publish mock TPMS values on Venus OS D-Bus")
    parser.add_argument("--interval", type=float, default=2.0, help="update interval in seconds")
    return parser.parse_args()


def main():
    args = parse_args()
    DBusGMainLoop(set_as_default=True)
    loop = GLib.MainLoop()
    service = MockTpmsService(args.interval)
    service.update()

    def stop(*_args):
        service.service["/Connected"] = 0
        loop.quit()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    GLib.timeout_add(int(args.interval * 1000), service.update)
    print(f"publishing {TPMS_SERVICE_NAME}; press Ctrl-C to stop", flush=True)
    loop.run()


if __name__ == "__main__":
    main()
