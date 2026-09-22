"""Read-only WirelessAir telemetry. No pressure-control characteristic writes."""
import asyncio
import json
import logging
import struct
import threading
import time
from datetime import datetime, timezone
from uuid import UUID

DEVICE_NAME = 'WirelessAir-095789'
SERVICE_UUID = '0003abcd-0000-1000-8000-00805f9b0131'
PRESSURE_UUID = '00031234-0000-1000-8000-00805f9b0131'
OBSERVED_UUIDS = {PRESSURE_UUID, 'e1fc2ca1-7e10-4f98-a8b3-0764f70ad668',
                  '8070d7a0-8c69-47fc-81e3-3f76dc93bac6'}
STALE_SECONDS = 10.0
RETRY_SECONDS = 15.0
MAX_RETRY_SECONDS = 60.0
IO_TIMEOUT_SECONDS = 10.0
LOG = logging.getLogger('ovrland.airlift')


def decode_pressure_packet(packet):
    if len(packet) != 4:
        raise ValueError('Pressure packet must contain exactly four bytes')
    left, right = struct.unpack('>HH', packet)
    return {'left_psi': left / 10.0, 'right_psi': right / 10.0}


def decode_status(packet):
    if len(packet) != 1:
        raise ValueError('Status packet must contain exactly one byte')
    return {0: 'idle', 1: 'deflating', 2: 'inflating'}.get(packet[0], 'unknown')


def characteristic_info(characteristic):
    # On BlueZ, Bleak 1.1 uses the charXXXX object-path declaration handle.
    # Do not call this an ATT value handle or silently add one to it.
    obj = getattr(characteristic, 'obj', None)
    bluez = (isinstance(obj, tuple) and isinstance(obj[0], str)
             and obj[0].startswith('/org/bluez/'))
    return {'uuid': characteristic.uuid.lower(), 'handle': characteristic.handle,
            'handle_hex': f'0x{characteristic.handle:04x}',
            'handle_kind': 'bluez_declaration' if bluez else 'backend_characteristic',
            'service_uuid': characteristic.service_uuid.lower(),
            'properties': list(characteristic.properties)}


class AirLiftClient:
    def __init__(self, name=DEVICE_NAME, address=None, status_uuid=None,
                 enabled=True, discovery=False):
        self.name = name
        self.address = address
        self.status_uuid = str(UUID(status_uuid)) if status_uuid else None
        if self.status_uuid == PRESSURE_UUID:
            raise ValueError('Status UUID cannot be the measured-pressure UUID')
        self.enabled = enabled
        self.discovery = discovery
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.loop = None
        self.task = None
        self.client = None
        self.connection = 'disconnected' if enabled else 'disabled'
        self.connected = False
        self.pressure = None
        self.pressure_received = None
        self.received_at = None
        self.state = 'unknown'
        self.state_received = None
        self.error = None
        self.characteristics = []
        self.invalid_packets = 0
        self.pressure_packets = 0
        self._generation = 0

    def _log(self, event, level=logging.DEBUG, **fields):
        LOG.log(level, '%s', json.dumps({
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'event': event, 'device': self.name, **fields,
        }))

    def _clear(self, connection='disconnected', error=None):
        with self.lock:
            self._generation += 1
            self.connected = False
            self.connection = connection
            self.pressure = None
            self.pressure_received = self.received_at = None
            self.state, self.state_received = 'unknown', None
            self.error = error

    def snapshot(self):
        with self.lock:
            now = time.monotonic()
            age = now - self.pressure_received if self.pressure_received is not None else None
            fresh = self.connected and age is not None and age <= STALE_SECONDS
            status = ('live' if fresh else 'stale' if age is not None else self.connection)
            state = 'disconnected' if not self.connected else 'unknown'
            if (self.connected and self.state_received is not None
                    and now - self.state_received <= STALE_SECONDS):
                state = self.state
            return {
                'status': status, 'device_name': self.name,
                'age_ms': round(age * 1000) if age is not None else None,
                'received_at': self.received_at, 'status_uuid': self.status_uuid,
                'discovery': self.discovery, 'error': self.error,
                'invalid_packets': self.invalid_packets,
                'pressure_packets': self.pressure_packets,
                'characteristics': [dict(item, properties=list(item['properties']))
                                    for item in self.characteristics],
                'data': {**(self.pressure if fresh else {'left_psi': None, 'right_psi': None}),
                         'state': state},
            }

    def _accept(self, characteristic, packet, source, generation):
        info = characteristic_info(characteristic)
        raw = bytes(packet)
        decoded = None
        kind = None
        try:
            if info['uuid'] == PRESSURE_UUID and info['service_uuid'] == SERVICE_UUID:
                decoded, kind = decode_pressure_packet(raw), 'pressure'
            elif self.status_uuid and info['uuid'] == self.status_uuid:
                decoded, kind = {'state': decode_status(raw)}, 'status'
        except ValueError as error:
            with self.lock:
                if generation == self._generation and self.connected:
                    self.invalid_packets += 1
            self._log('invalid_payload', **info, source=source, raw_payload=raw.hex(' '), error=str(error))
            return
        self._log('payload', **info, source=source, raw_payload=raw.hex(' '), decoded=decoded)
        with self.lock:
            if generation != self._generation or not self.connected or self.stop_event.is_set():
                return
            if kind == 'pressure':
                self.pressure_packets += 1
                self.pressure = decoded
                self.pressure_received = time.monotonic()
                self.received_at = datetime.now(timezone.utc).isoformat()
            elif kind == 'status':
                self.state = decoded['state']
                self.state_received = time.monotonic()

    async def scan(self, scanner_type):
        with self.lock:
            self.connection = 'scanning'

        def matches(device, advertisement):
            if self.address:
                return device.address.lower() == self.address.lower()
            return (advertisement.local_name or device.name) == self.name

        return await scanner_type.find_device_by_filter(matches, timeout=8)

    async def connect(self, device, client_type):
        self._clear('connecting')
        self.client = client_type(device, disconnected_callback=lambda peer:
                                  self._clear() if self.client is peer else None, timeout=20)
        await asyncio.wait_for(self.client.connect(), timeout=25)
        with self.lock:
            self.connected = True
            self.connection = 'connected'
        self._log('connected', logging.INFO, address=device.address)

    async def subscribe(self):
        manifest, selected = [], []
        for service in self.client.services:
            for characteristic in service.characteristics:
                info = characteristic_info(characteristic)
                manifest.append(info)
                if self.discovery:
                    self._log('characteristic', logging.INFO, **info)
                if ((info['service_uuid'] == SERVICE_UUID and
                     (info['uuid'] == PRESSURE_UUID or self.discovery))
                        or info['uuid'] == self.status_uuid
                        or (self.discovery and info['handle'] in (0x0030, 0x0031))):
                    selected.append(characteristic)
        with self.lock:
            self.characteristics = manifest
            generation = self._generation
        pressure = [item for item in selected if item.uuid.lower() == PRESSURE_UUID
                    and item.service_uuid.lower() == SERVICE_UUID]
        if len(pressure) != 1:
            raise ValueError('Expected one measured-pressure characteristic in the Air Lift service')
        if self.status_uuid and sum(item.uuid.lower() == self.status_uuid for item in selected) != 1:
            raise ValueError('Configured status UUID is missing or ambiguous')
        # A matching numeric backend handle alone never establishes the status UUID.
        if self.discovery:
            for info in manifest:
                if info['handle'] in (0x0030, 0x0031):
                    self._log('status_handle_candidate', logging.INFO, **info,
                              captured_att_value_handle='0x0031',
                              verified=False, next_step='Use check_airlift.py --att-map')
        readable = []
        for characteristic in selected:
            props = characteristic.properties
            if 'notify' in props or 'indicate' in props:
                try:
                    await asyncio.wait_for(self.client.start_notify(
                        characteristic, lambda sender, data: self._accept(
                            sender, data, 'notification', generation)), IO_TIMEOUT_SECONDS)
                except Exception as error:
                    if characteristic is pressure[0] and 'read' not in props:
                        raise
                    self._log('subscribe_failed', logging.WARNING,
                              **characteristic_info(characteristic), error=str(error))
            elif characteristic is pressure[0] and 'read' not in props:
                raise ValueError('Measured-pressure characteristic cannot be read or subscribed')
            if 'read' in props:
                readable.append(characteristic)
        return readable, generation

    async def disconnect(self):
        self._clear()
        client, self.client = self.client, None
        if client:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=5)
            except Exception as error:
                self._log('disconnect_failed', logging.WARNING, error=str(error))

    async def _session(self, client_type, scanner_type):
        device = await self.scan(scanner_type)
        if device is None:
            self._clear(error='Device not advertising; remote/app may own the connection')
            return
        try:
            await self.connect(device, client_type)
            readable, generation = await self.subscribe()
            while self.client.is_connected and not self.stop_event.is_set():
                for characteristic in readable:
                    try:
                        raw = await asyncio.wait_for(self.client.read_gatt_char(characteristic), IO_TIMEOUT_SECONDS)
                        self._accept(characteristic, raw, 'read', generation)
                    except Exception as error:
                        self._log('read_failed', uuid=characteristic.uuid, error=str(error))
                await asyncio.sleep(2)
        finally:
            await self.disconnect()

    async def _run(self, client_type, scanner_type):
        delay = RETRY_SECONDS
        while not self.stop_event.is_set():
            started = time.monotonic()
            try:
                await self._session(client_type, scanner_type)
            except Exception as error:
                self._clear(error=str(error))
                self._log('connection_failed', logging.WARNING, error=str(error),
                          hint='Remote or official app may already own the BLE connection')
            if time.monotonic() - started >= MAX_RETRY_SECONDS:
                delay = RETRY_SECONDS
            self._log('retry', logging.INFO, after_seconds=delay)
            await asyncio.sleep(delay)
            delay = min(delay * 2, MAX_RETRY_SECONDS)

    def start(self):
        if not self.enabled or (self.thread and self.thread.is_alive()):
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._thread_main, name='airlift-ble-reader', daemon=True)
        self.thread.start()

    def _thread_main(self):
        async def main():
            from bleak import BleakClient, BleakScanner
            with self.lock:
                self.loop = asyncio.get_running_loop()
                self.task = asyncio.current_task()
            if self.stop_event.is_set():
                return
            try:
                await self._run(BleakClient, BleakScanner)
            except asyncio.CancelledError:
                pass
            finally:
                self._clear()
                with self.lock:
                    self.loop = self.task = None
        try:
            asyncio.run(main())
        except Exception as error:
            self._clear('unavailable', str(error))
            self._log('unavailable', logging.WARNING, error=str(error))

    def stop(self):
        self.stop_event.set()
        with self.lock:
            loop, task = self.loop, self.task
        if loop and task:
            try:
                loop.call_soon_threadsafe(task.cancel)
            except RuntimeError:
                pass
        if self.thread:
            self.thread.join(timeout=6)
        self._clear('disconnected' if self.enabled else 'disabled')
