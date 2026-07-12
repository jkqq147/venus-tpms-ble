#!/usr/bin/env python3
"""Scan TPMS BLE advertisements through BlueZ and publish them on Venus D-Bus."""

import argparse
import ctypes
import errno
import fcntl
import json
import os
import queue
import select
import signal
import struct
import sys
import threading
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
BLE_ACTIVITY_WINDOW_SECONDS = 300
HCI_DRAIN_INTERVAL_MS = 100
HCI_EVENTS_PER_DRAIN = 8
HCI_EVENT_QUEUE_SIZE = 128

AF_BLUETOOTH = 31
SOCK_RAW = 3
BTPROTO_HCI = 1
SOL_HCI = 0
HCI_FILTER = 2
HCI_EVENT_PKT = 0x04
EVT_LE_META_EVENT = 0x3E
EVT_LE_ADVERTISING_REPORT = 0x02

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


def parse_advertisement_data(data):
    name = ""
    manufacturer_data = []
    offset = 0
    while offset < len(data):
        length = data[offset]
        offset += 1
        if length == 0:
            break
        end = offset + length
        if end > len(data):
            break
        ad_type = data[offset]
        value = data[offset + 1:end]
        if ad_type in (0x08, 0x09):
            name = value.decode("utf-8", errors="replace")
        elif ad_type == 0xFF:
            manufacturer_data.append(value)
        offset = end
    return name, manufacturer_data


def parse_hci_le_advertising_reports(packet):
    if packet and packet[0] == HCI_EVENT_PKT:
        packet = packet[1:]
    if len(packet) < 4 or packet[0] != EVT_LE_META_EVENT:
        return []

    parameter_length = packet[1]
    parameters = packet[2:2 + parameter_length]
    if len(parameters) < 2 or parameters[0] != EVT_LE_ADVERTISING_REPORT:
        return []

    reports = []
    offset = 2
    for _ in range(parameters[1]):
        if offset + 9 > len(parameters):
            break
        event_type = parameters[offset]
        address_type = parameters[offset + 1]
        address = ":".join(f"{byte:02X}" for byte in reversed(parameters[offset + 2:offset + 8]))
        data_length = parameters[offset + 8]
        data_start = offset + 9
        data_end = data_start + data_length
        if data_end >= len(parameters):
            break
        reports.append({
            "event_type": event_type,
            "address_type": address_type,
            "address": address,
            "data": parameters[data_start:data_end],
            "rssi": int.from_bytes(parameters[data_end:data_end + 1], "little", signed=True),
        })
        offset = data_end + 1
    return reports


class SockaddrHci(ctypes.Structure):
    _fields_ = (
        ("hci_family", ctypes.c_ushort),
        ("hci_dev", ctypes.c_ushort),
        ("hci_channel", ctypes.c_ushort),
    )


class TpmsBluezService:
    def __init__(self, stale_seconds):
        self.stale_seconds = stale_seconds
        self.bus = dbus.SystemBus()
        self.settings = None
        self.adapter_path = None
        self.adapter = None
        self.adapter_properties = None
        self.discovery_started = False
        self.discovery_owned = False
        self.hci_fd = None
        self.hci_watch = None
        self.hci_thread = None
        self.hci_stop = threading.Event()
        self.hci_events = queue.Queue(maxsize=HCI_EVENT_QUEUE_SIZE)
        self.hci_activity = {}
        self.hci_activity_lock = threading.Lock()
        self.ble_devices_by_address = {}
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
        self.service.add_path("/Bluetooth/ReceiverStatus", "Starting")
        self.service.add_path("/Bluetooth/DeviceCount", 0)
        self.service.add_path("/Bluetooth/ManufacturerDataCount", 0)

        self._ensure_settings()
        self._add_slot_paths()
        self._add_discovered_paths()
        self.service.register()
        self._update_slots()

        self._connect_bluez()

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
        self.bus.add_signal_receiver(
            self._interfaces_added,
            dbus_interface="org.freedesktop.DBus.ObjectManager",
            signal_name="InterfacesAdded",
        )
        self.bus.add_signal_receiver(
            self._interfaces_removed,
            dbus_interface="org.freedesktop.DBus.ObjectManager",
            signal_name="InterfacesRemoved",
        )
        self.bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path_keyword="path",
        )
        try:
            objects = self._get_bluez_objects()
        except Exception as exc:
            self._set_bluez_unavailable(exc)
            return
        self._sync_adapter(objects)
        for path, ifaces in objects.items():
            props = ifaces.get("org.bluez.Device1")
            if props:
                self._handle_device(path, props)

    def _get_bluez_objects(self):
        manager = dbus.Interface(self.bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        return manager.GetManagedObjects()

    @staticmethod
    def _adapter_sort_key(path):
        name = str(path).rsplit("/", 1)[-1]
        suffix = name[3:] if name.startswith("hci") else ""
        return (int(suffix) if suffix.isdigit() else sys.maxsize, name)

    def _sync_adapter(self, objects):
        adapter_paths = sorted(
            (str(path) for path, ifaces in objects.items() if "org.bluez.Adapter1" in ifaces),
            key=self._adapter_sort_key,
        )
        selected_path = adapter_paths[0] if adapter_paths else None
        if selected_path == self.adapter_path and self.adapter is not None:
            return True

        if self.adapter is not None:
            self._detach_adapter()
        if selected_path is None:
            self._set_no_adapter()
            return False

        try:
            self.adapter_path = selected_path
            self.adapter = dbus.Interface(
                self.bus.get_object("org.bluez", selected_path),
                "org.bluez.Adapter1",
            )
            self.adapter_properties = dbus.Interface(
                self.bus.get_object("org.bluez", selected_path),
                "org.freedesktop.DBus.Properties",
            )
            self.service["/Bluetooth/Adapter"] = selected_path
            self._start_hci_listener()
            self._start_discovery()
            debug(f"Using Bluetooth adapter {selected_path}")
            return True
        except Exception as exc:
            self._detach_adapter()
            self.service["/Status"] = 2
            self.service["/StatusText"] = "Adapter unavailable"
            self.service["/Bluetooth/StatusText"] = "Adapter unavailable"
            self.service["/Bluetooth/Discovering"] = 0
            debug(f"Adapter setup failed: {exc}")
            return False

    def _detach_adapter(self):
        if self.discovery_owned and self.adapter is not None:
            try:
                self.adapter.StopDiscovery()
            except Exception:
                pass
        self.discovery_started = False
        self.discovery_owned = False
        self._close_hci_listener()
        self.adapter_path = None
        self.adapter = None
        self.adapter_properties = None
        self.service["/Bluetooth/Adapter"] = ""
        self.service["/Bluetooth/Discovering"] = 0
        self.ble_devices_by_address.clear()
        self._remove_unbound_readings()

    def _set_no_adapter(self):
        self.service["/Status"] = 2
        self.service["/StatusText"] = "No adapter"
        self.service["/Bluetooth/StatusText"] = "No adapter"
        self.service["/Bluetooth/Discovering"] = 0
        self.service["/Bluetooth/Adapter"] = ""
        self._set_receiver_status("Unavailable")
        self._update_bluetooth_counts({})

    def _set_bluez_unavailable(self, exc):
        self._detach_adapter()
        self.service["/Status"] = 2
        self.service["/StatusText"] = "BlueZ unavailable"
        self.service["/Bluetooth/StatusText"] = "Unavailable"
        self.service["/Bluetooth/Discovering"] = 0
        debug(f"BlueZ unavailable: {exc}")

    def _start_hci_listener(self):
        fd = None
        try:
            adapter_name = self.adapter_path.rsplit("/", 1)[-1]
            if not adapter_name.startswith("hci"):
                raise ValueError(f"Unsupported adapter path: {self.adapter_path}")
            adapter_index = int(adapter_name[3:])

            libc = ctypes.CDLL(None, use_errno=True)
            fd = libc.socket(AF_BLUETOOTH, SOCK_RAW, BTPROTO_HCI)
            if fd < 0:
                raise OSError(ctypes.get_errno(), "HCI socket failed")

            address = SockaddrHci(AF_BLUETOOTH, adapter_index, 0)
            if libc.bind(fd, ctypes.byref(address), ctypes.sizeof(address)) != 0:
                error = ctypes.get_errno()
                os.close(fd)
                raise OSError(error, "HCI socket bind failed")

            filter_data = struct.pack(
                "=IIIH",
                1 << HCI_EVENT_PKT,
                0,
                1 << (EVT_LE_META_EVENT - 32),
                0,
            )
            filter_buffer = ctypes.create_string_buffer(filter_data)
            if libc.setsockopt(fd, SOL_HCI, HCI_FILTER, filter_buffer, len(filter_data)) != 0:
                error = ctypes.get_errno()
                os.close(fd)
                raise OSError(error, "HCI event filter failed")

            flags = fcntl.fcntl(fd, fcntl.F_GETFL)
            fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
            self.hci_fd = fd
            self.hci_stop.clear()
            self.hci_thread = threading.Thread(target=self._read_hci, args=(fd,), daemon=True)
            self.hci_thread.start()
            self.hci_watch = GLib.timeout_add(HCI_DRAIN_INTERVAL_MS, self._drain_hci_events)
            self._set_receiver_status("Listening")
            debug(f"Listening for raw HCI advertisements on {adapter_name}")
        except Exception as exc:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
            self.hci_fd = None
            self.hci_watch = None
            self._set_receiver_status("Unavailable")
            debug(f"Raw HCI listener unavailable, using BlueZ Device1 data: {exc}")

    def _read_hci(self, fd):
        while not self.hci_stop.is_set():
            if self.hci_fd != fd:
                return
            try:
                readable, _, _ = select.select([fd], [], [], 1)
            except (OSError, ValueError):
                return
            if not readable:
                continue
            try:
                packet = os.read(fd, 2048)
            except OSError as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    continue
                debug(f"Raw HCI read failed: {exc}")
                return
            if not packet:
                return
            self._queue_hci_reports(packet)

    def _queue_hci_reports(self, packet):
        now = int(time.time())
        for report in parse_hci_le_advertising_reports(packet):
            name, manufacturer_data = parse_advertisement_data(report["data"])
            with self.hci_activity_lock:
                existing = self.hci_activity.get(report["address"], {})
                self.hci_activity[report["address"]] = {
                    "last_seen": now,
                    "name": name or existing.get("name", ""),
                    "rssi": report["rssi"] if report["rssi"] is not None else existing.get("rssi"),
                    "has_manufacturer_data": bool(manufacturer_data or existing.get("has_manufacturer_data")),
                }
            for data in manufacturer_data:
                if parse_tpms_manufacturer_data(data) is None:
                    continue
                try:
                    self.hci_events.put_nowait((report["address"], name, report["rssi"], data))
                except queue.Full:
                    pass

    def _drain_hci_events(self):
        if self.hci_fd is None:
            return False
        now = int(time.time())
        cutoff = now - BLE_ACTIVITY_WINDOW_SECONDS
        with self.hci_activity_lock:
            self.ble_devices_by_address = {
                address: activity
                for address, activity in self.hci_activity.items()
                if activity["last_seen"] >= cutoff
            }
            self.hci_activity = dict(self.ble_devices_by_address)
        self._update_bluetooth_counts({})
        for _ in range(HCI_EVENTS_PER_DRAIN):
            try:
                address, name, rssi, data = self.hci_events.get_nowait()
            except queue.Empty:
                break
            self._set_receiver_status("Receiving")
            self._handle_manufacturer_data(address, name, rssi, data)
        return self.hci_fd is not None

    def _ensure_hci_listener(self):
        if self.adapter is None or self.hci_fd is not None:
            return
        self._set_receiver_status("Restarting")
        self._start_hci_listener()

    def _set_receiver_status(self, value):
        if self.service["/Bluetooth/ReceiverStatus"] != value:
            self.service["/Bluetooth/ReceiverStatus"] = value

    def _close_hci_listener(self, remove_watch=True):
        if self.hci_watch is not None and remove_watch:
            GLib.source_remove(self.hci_watch)
        self.hci_watch = None
        self.hci_stop.set()
        if self.hci_fd is not None:
            try:
                os.close(self.hci_fd)
            except OSError:
                pass
            self.hci_fd = None
        if self.hci_thread is not None and self.hci_thread is not threading.current_thread():
            self.hci_thread.join(timeout=1)
        self.hci_thread = None
        self.hci_events = queue.Queue(maxsize=HCI_EVENT_QUEUE_SIZE)
        with self.hci_activity_lock:
            self.hci_activity = {}
        self._set_receiver_status("Unavailable")

    def _handle_hci_packet(self, packet):
        for report in parse_hci_le_advertising_reports(packet):
            name, manufacturer_data = parse_advertisement_data(report["data"])
            self._record_ble_activity(
                report["address"],
                name,
                report["rssi"],
                bool(manufacturer_data),
            )
            for data in manufacturer_data:
                self._handle_manufacturer_data(report["address"], name, report["rssi"], data)

    def _start_discovery(self):
        discovering = bool(self.adapter_properties.Get("org.bluez.Adapter1", "Discovering"))
        if discovering:
            self.discovery_owned = False
        else:
            self.adapter.SetDiscoveryFilter({"Transport": dbus.String("le"), "DuplicateData": dbus.Boolean(True)})
            self.adapter.StartDiscovery()
            self.discovery_owned = True
        self.discovery_started = True
        self.service["/Status"] = 0
        self.service["/StatusText"] = "Scanning"
        self.service["/Bluetooth/StatusText"] = "Scanning"
        self.service["/Bluetooth/Discovering"] = 1

    def _ensure_discovery(self):
        try:
            objects = self._get_bluez_objects()
        except Exception as exc:
            self._set_bluez_unavailable(exc)
            return
        if not self._sync_adapter(objects):
            return
        try:
            discovering = bool(self.adapter_properties.Get("org.bluez.Adapter1", "Discovering"))
        except Exception as exc:
            self._detach_adapter()
            self.service["/Status"] = 2
            self.service["/StatusText"] = "Adapter unavailable"
            self.service["/Bluetooth/StatusText"] = "Adapter unavailable"
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
        if self.hci_fd is not None:
            now = int(time.time())
            cutoff = now - BLE_ACTIVITY_WINDOW_SECONDS
            self.ble_devices_by_address = {
                address: device
                for address, device in self.ble_devices_by_address.items()
                if device["last_seen"] >= cutoff
            }
            self.service["/Bluetooth/DeviceCount"] = len(self.ble_devices_by_address)
            self.service["/Bluetooth/ManufacturerDataCount"] = sum(
                1 for device in self.ble_devices_by_address.values() if device["has_manufacturer_data"]
            )
            return

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
        if "org.bluez.Adapter1" in ifaces:
            try:
                self._sync_adapter(self._get_bluez_objects())
            except Exception as exc:
                self._set_bluez_unavailable(exc)
            return
        props = ifaces.get("org.bluez.Device1")
        if props:
            self._handle_device(path, props)

    def _interfaces_removed(self, _path, interfaces):
        if "org.bluez.Adapter1" not in interfaces:
            return
        try:
            self._sync_adapter(self._get_bluez_objects())
        except Exception as exc:
            self._set_bluez_unavailable(exc)

    def _properties_changed(self, interface, changed, _invalidated, path=None):
        if interface == "org.bluez.Device1":
            self._handle_device(path, changed)

    def _handle_device(self, path, props):
        address = str(props.get("Address", path.rsplit("/", 1)[-1]))
        name = str(props.get("Name") or props.get("Alias") or "")
        rssi = props.get("RSSI")
        mfg = props.get("ManufacturerData")
        self._record_ble_activity(address, name, rssi, bool(mfg))
        if not mfg:
            return

        for company, payload in mfg.items():
            manufacturer_data = int(company).to_bytes(2, "little") + bytes_from_dbus_array(payload)
            self._handle_manufacturer_data(address, name, rssi, manufacturer_data)

    def _record_ble_activity(self, address, name, rssi, has_manufacturer_data):
        now = int(time.time())
        existing = self.ble_devices_by_address.get(address, {})
        self.ble_devices_by_address[address] = {
            "last_seen": now,
            "name": name or existing.get("name", ""),
            "rssi": int(rssi) if rssi is not None else existing.get("rssi"),
            "has_manufacturer_data": bool(has_manufacturer_data or existing.get("has_manufacturer_data")),
        }

    def _handle_manufacturer_data(self, address, name, rssi, manufacturer_data):
        parsed = parse_tpms_manufacturer_data(manufacturer_data)
        if parsed is None:
            return
        parsed.update({
            "address": address,
            "name": name or self.ble_devices_by_address.get(address, {}).get("name", ""),
            "rssi": int(rssi) if rssi is not None else None,
            "last_seen": int(time.time()),
        })
        self._update_reading(parsed)

    def _update_reading(self, reading):
        sensor_id = reading["sensor_id"]
        self.readings_by_sensor_id[sensor_id] = reading
        self._persist_bound_reading(reading)
        self._refresh_discovered_order()
        self._update_discovered_paths()
        self._update_slots()

    def _prune_expired_readings(self):
        cutoff = int(time.time()) - BLE_ACTIVITY_WINDOW_SECONDS
        self._remove_unbound_readings(lambda reading: reading["last_seen"] < cutoff)

    def _remove_unbound_readings(self, should_remove=lambda _reading: True):
        bound_sensor_ids = {
            self.settings[wheel_key]
            for wheel_key, _, _ in WHEELS
            if self.settings[wheel_key]
        }
        expired = [
            sensor_id
            for sensor_id, reading in self.readings_by_sensor_id.items()
            if sensor_id not in bound_sensor_ids and should_remove(reading)
        ]
        if not expired:
            return
        for sensor_id in expired:
            del self.readings_by_sensor_id[sensor_id]
        self._refresh_discovered_order()
        self._update_discovered_paths()

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
        suffix = "*" if state == "stale" else ""
        self.service[f"{root}/PressureDisplay"] = f"{reading['pressure_bar']:.2f}{suffix}"
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
        self.service[f"{root}/PressureDisplay"] = "wait" if state == "waiting" else "--"
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
        if self.adapter is None or not self.discovery_started:
            self._ensure_discovery()
        elif self.hci_fd is not None:
            self._update_bluetooth_counts({})
        self._ensure_hci_listener()
        self._prune_expired_readings()
        self._update_slots()
        return True

    def stop(self):
        self.service["/Connected"] = 0
        self._close_hci_listener()
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
