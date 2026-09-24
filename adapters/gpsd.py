"""Resilient, read-only client for a system-owned gpsd JSON socket."""
import json
import math
import socket
import threading
import time
from datetime import datetime, timezone

WATCH = b'?WATCH={"enable":true,"json":true};\n'
STALE_SECONDS = 10.0


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_tpv(report):
    """Return a usable location from a TPV report, or None without a 2D fix."""
    if not isinstance(report, dict) or report.get('class') != 'TPV':
        return None
    if not _number(report.get('mode')) or report['mode'] < 2:
        return None
    lat, lon = report.get('lat'), report.get('lon')
    if not (_number(lat) and _number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    altitude = next((report[key] for key in ('altMSL', 'altHAE', 'alt')
                     if _number(report.get(key))), None)
    accuracy = next((report[key] for key in ('epx', 'epy', 'eph')
                     if _number(report.get(key))), None)
    track = report.get('track')
    return {
        'latitude': lat,
        'longitude': lon,
        'altitude_m': altitude,
        'heading_deg': track % 360 if _number(track) else None,
        'accuracy_m': accuracy,
        'horizontal_accuracy_m': report.get('eph') if _number(report.get('eph')) else None,
        'longitude_error_m': report.get('epx') if _number(report.get('epx')) else None,
        'latitude_error_m': report.get('epy') if _number(report.get('epy')) else None,
        'vertical_accuracy_m': report.get('epv') if _number(report.get('epv')) else None,
        'speed_mps': report.get('speed') if _number(report.get('speed')) else None,
        'speed_accuracy_mps': report.get('eps') if _number(report.get('eps')) else None,
        'climb_mps': report.get('climb') if _number(report.get('climb')) else None,
        'mode': int(report['mode']),
        'gps_time': report.get('time') if isinstance(report.get('time'), str) else None,
    }


class GPSD:
    def __init__(self, host='127.0.0.1', port=2947, reconnect_seconds=3.0):
        self.host = host
        self.port = port
        self.reconnect_seconds = reconnect_seconds
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.state = 'disconnected'
        self.latest = None
        self.received = 0.0
        self.satellites_seen = None
        self.satellites_used = None
        self.dop = {}

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='gpsd-reader')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def snapshot(self):
        with self.lock:
            age = time.monotonic() - self.received if self.received else None
            state = self.state
            data = dict(self.latest) if self.latest else None
            if data and age is not None and age > STALE_SECONDS:
                state, data = 'stale', None
            return {
                'status': state,
                'age_ms': round(age * 1000) if age is not None else None,
                'satellites_seen': self.satellites_seen,
                'satellites_used': self.satellites_used,
                'dop': dict(self.dop),
                'data': data,
            }

    def _accept(self, report):
        if report.get('class') == 'SKY':
            satellites = report.get('satellites')
            with self.lock:
                if isinstance(satellites, list):
                    self.satellites_seen = len(satellites)
                    self.satellites_used = sum(item.get('used') is True for item in satellites
                                               if isinstance(item, dict))
                self.dop = {key: report[key] for key in ('hdop', 'vdop', 'pdop', 'gdop')
                            if _number(report.get(key))}
            return
        if report.get('class') != 'TPV':
            return
        location = normalize_tpv(report)
        with self.lock:
            if location:
                location['received_at'] = datetime.now(timezone.utc).isoformat()
                self.latest = location
                self.received = time.monotonic()
                self.state = 'live'
            else:
                self.latest = None
                self.received = 0.0
                self.state = 'no_fix'

    def _run(self):
        while not self.stop_event.is_set():
            try:
                with socket.create_connection((self.host, self.port), timeout=2) as connection:
                    connection.settimeout(1)
                    connection.sendall(WATCH)
                    with self.lock:
                        self.state = 'connected'
                    buffer = b''
                    while not self.stop_event.is_set():
                        try:
                            chunk = connection.recv(16384)
                        except socket.timeout:
                            continue
                        if not chunk:
                            raise OSError('gpsd disconnected')
                        buffer += chunk
                        while b'\n' in buffer:
                            line, buffer = buffer.split(b'\n', 1)
                            try:
                                report = json.loads(line)
                                if isinstance(report, dict):
                                    self._accept(report)
                            except (UnicodeDecodeError, json.JSONDecodeError):
                                pass
                        if len(buffer) > 1024 * 1024:
                            buffer = b''
            except OSError:
                with self.lock:
                    self.state = 'disconnected'
                    self.latest = None
                    self.received = 0.0
                    self.satellites_seen = None
                    self.satellites_used = None
                    self.dop = {}
            self.stop_event.wait(self.reconnect_seconds)
