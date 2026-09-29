"""BLE transport for the OVRLand Nano telemetry GATT service."""
import asyncio
import json
import threading
import time

from adapters.nano import Nano

SERVICE_UUID = '0f0c48e7-9d3f-4c79-90d6-1e664d2cba00'
TELEMETRY_UUID = '0f0c48e7-9d3f-4c79-90d6-1e664d2cba01'
START = 0x01
END = 0x02
HEADER_BYTES = 4
CONNECT_TIMEOUT_SECONDS = 25
MAX_FRAME_BYTES = 1024
MAX_FRAME_PACKETS = 64
FRAME_TIMEOUT_SECONDS = 2


class PacketDecoder:
    """Reassemble the 20-byte notification packets emitted by the Nano."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.frame = None
        self.expected_packet = 0
        self.payload = bytearray()
        self.started_at = None
        self.packet_count = 0

    def feed(self, packet, now=None):
        now = time.monotonic() if now is None else now
        if self.frame is not None and now - self.started_at > FRAME_TIMEOUT_SECONDS:
            self.reset()
        packet = bytes(packet)
        if len(packet) < HEADER_BYTES:
            self.reset()
            return None
        flags, frame, sequence, length = packet[:HEADER_BYTES]
        if flags & ~(START | END) or length != len(packet) - HEADER_BYTES:
            self.reset()
            return None
        if flags & START:
            if sequence != 0 or flags & END:
                self.reset()
                return None
            self.frame = frame
            self.expected_packet = 0
            self.payload = bytearray()
            self.started_at = now
            self.packet_count = 0
        if self.frame is None or frame != self.frame or sequence != self.expected_packet:
            self.reset()
            return None
        if flags & END:
            if length:
                self.reset()
                return None
            result = bytes(self.payload)
            self.reset()
            return result
        if not length:
            self.reset()
            return None
        if self.packet_count >= MAX_FRAME_PACKETS or len(self.payload) + length > MAX_FRAME_BYTES:
            self.reset()
            return None
        self.payload.extend(packet[HEADER_BYTES:])
        self.expected_packet = (self.expected_packet + 1) & 0xff
        self.packet_count += 1
        return None


def expand_record(record):
    """Expand the compact, integer BLE record into the USB JSON contract."""
    if not isinstance(record, dict):
        raise ValueError('Invalid BLE record')
    if record.get('type') == 'joystick':
        return record
    required = ('m', 'x', 'y', 'b', 'f', 'a', 'e', 'l')
    if not isinstance(record, dict) or any(key not in record for key in required):
        raise ValueError('Invalid compact BLE record')
    if not (isinstance(record['a'], list) and len(record['a']) == 3 and
            isinstance(record['e'], list) and len(record['e']) == 4 and
            isinstance(record['l'], list) and len(record['l']) == 4):
        raise ValueError('Invalid compact BLE arrays')
    numeric = (record['m'], record['x'], record['y'], record['b'], record['f'],
               *record['a'], *record['e'], *record['l'])
    if any(not isinstance(value, (int, float)) or isinstance(value, bool) for value in numeric):
        raise ValueError('Invalid compact BLE values')
    flags = int(record['f'])
    return {
        'type': 'joystick', 'ms': record['m'], 'x': record['x'] / 100,
        'y': record['y'] / 100, 'pressed': bool(record['b']),
        'imu_ok': bool(flags & 1), 'ax': record['a'][0] / 1000,
        'ay': record['a'][1] / 1000, 'az': record['a'][2] / 1000,
        'env_ok': bool(flags & 2), 'temp_c': record['e'][0] / 100,
        'humidity_pct': record['e'][1], 'baro_ok': bool(flags & 4),
        'pressure_kpa': record['e'][2] / 10, 'altitude_m': record['e'][3] / 10,
        'apds_ok': bool(flags & 8), 'color_r': record['l'][0],
        'color_g': record['l'][1], 'color_b': record['l'][2],
        'proximity': record['l'][3],
    }


class NanoBLE(Nano):
    """Nano state machine fed by BLE notifications rather than a serial port."""
    def __init__(self, address=None):
        super().__init__(address or 'OVRLand Nano (BLE)')
        self.address = address
        self.decoder = PacketDecoder()

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='nano-ble-reader')
        self.thread.start()

    def _disconnected(self):
        with self.lock:
            self.state = 'disconnected'

    def _notification(self, _sender, packet):
        record = self.decoder.feed(packet)
        if record is None:
            return
        try:
            self._accept(expand_record(json.loads(record)))
        except (ValueError, TypeError, OverflowError, UnicodeDecodeError):
            with self.lock:
                self.invalid += 1

    async def _find(self, scanner_type):
        found = asyncio.get_running_loop().create_future()

        def seen(device, advertisement):
            if SERVICE_UUID in (advertisement.service_uuids or []) and not found.done():
                found.set_result(device)

        scanner = scanner_type(detection_callback=seen)
        await scanner.start()
        try:
            return await asyncio.wait_for(found, timeout=10)
        except asyncio.TimeoutError:
            return None
        finally:
            await scanner.stop()

    async def _session(self, client_type, scanner_type):
        device = self.address or await self._find(scanner_type)
        if not device or self.stop_event.is_set():
            return
        try:
            async with client_type(device, timeout=CONNECT_TIMEOUT_SECONDS) as client:
                await client.start_notify(TELEMETRY_UUID, self._notification)
                while client.is_connected and not self.stop_event.is_set():
                    await asyncio.sleep(.2)
        finally:
            self.decoder.reset()

    def _run(self):
        try:
            from bleak import BleakClient, BleakScanner
        except ImportError:
            self._disconnected()
            return
        while not self.stop_event.is_set():
            try:
                asyncio.run(self._session(BleakClient, BleakScanner))
            except Exception:
                # BLE hardware, range, and peer power may all change in use.
                self._disconnected()
            self.stop_event.wait(1)
