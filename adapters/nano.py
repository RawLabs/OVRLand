"""USB NDJSON adapter. Hardware IO stays out of the API and browser."""
import json
import math
import os
import select
import termios
import threading
import time
import uuid
from datetime import datetime, timezone

STALE_SECONDS = 2.0
JOYSTICK_DEADZONE = 0.03

# The Nano is mounted on its side in the vehicle.  In this mounting the board
# axes map to vehicle forward=Z, right=X, up=-Y.


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize(raw):
    if not isinstance(raw, dict) or raw.get('type') != 'joystick':
        raise ValueError('Not a Nano telemetry message')
    if not all(number(raw.get(k)) for k in ('ms', 'x', 'y')) or type(raw.get('pressed')) is not bool:
        raise ValueError('Invalid joystick message')
    if not (-1 <= raw['x'] <= 1 and -1 <= raw['y'] <= 1):
        raise ValueError('Joystick outside normalized range')
    def axis(value):
        # Ignore the small electrical jitter around center and keep the UI
        # stable at hundredth-unit precision.
        return 0.0 if abs(value) < JOYSTICK_DEADZONE else round(value, 2)
    def sensor(key, flag):
        value = raw.get(key)
        return value if raw.get(flag) is True and number(value) else None
    ax, ay, az = (sensor(k, 'imu_ok') for k in ('ax', 'ay', 'az'))
    pitch = roll = None
    if all(v is not None for v in (ax, ay, az)):
        magnitude = math.sqrt(ax * ax + ay * ay + az * az)
        # Static gravity estimate only; reject gross acceleration/free-fall.
        if 0.8 <= magnitude <= 1.2:
            vehicle_forward = az
            vehicle_right = ax
            vehicle_up = -ay
            pitch = round(math.degrees(math.atan2(vehicle_forward, vehicle_up)), 1)
            roll = round(-math.degrees(math.atan2(vehicle_right,
                                                  math.hypot(vehicle_forward, vehicle_up))), 1)
    return {
        'device_ms': raw['ms'],
        'joystick': {'x': axis(raw['x']), 'y': axis(raw['y']), 'pressed': raw['pressed']},
        'attitude': {'pitch_deg': pitch, 'roll_deg': roll,
                     'quality': 'uncalibrated_gravity_estimate', 'heading_deg': None},
        'environment': {
            'temperature_c': sensor('temp_c', 'env_ok'),
            'humidity_pct': sensor('humidity_pct', 'env_ok'),
            'pressure_kpa': sensor('pressure_kpa', 'baro_ok'),
            'altitude_m': sensor('altitude_m', 'baro_ok'),
            'light_r_raw': sensor('color_r', 'apds_ok'),
            'light_g_raw': sensor('color_g', 'apds_ok'),
            'light_b_raw': sensor('color_b', 'apds_ok'),
            'proximity_raw': sensor('proximity', 'apds_ok'),
        },
        'imu': {k: sensor(k, 'imu_ok') for k in ('ax', 'ay', 'az', 'gx', 'gy', 'gz', 'mx', 'my', 'mz')},
    }


class Nano:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread = None
        self.latest = None
        self.received = 0
        self.state = 'disconnected'
        self.session = str(uuid.uuid4())
        self.sequence = 0
        self.invalid = 0
        self.events = []
        self.event_id = 0
        self.armed = False
        self.vertical_armed = False
        self.button_released = False

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='nano-reader')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=2)

    def snapshot(self):
        with self.lock:
            age = time.monotonic() - self.received if self.received else None
            state = self.state
            if state == 'live' and age > STALE_SECONDS:
                state = 'stale'
            return {'status': state, 'age_ms': round(age * 1000) if age is not None else None,
                    'session': self.session, 'sequence': self.sequence, 'invalid_lines': self.invalid,
                    'event_id': self.event_id, 'events': list(self.events) if state == 'live' else [],
                    'data': self.latest if state == 'live' else None}

    def _accept(self, raw):
        sample = normalize(raw)
        now = time.monotonic()
        with self.lock:
            restarted = self.latest and sample['device_ms'] < self.latest['device_ms']
            if self.state != 'live' or now - self.received > STALE_SECONDS or restarted:
                self.session = str(uuid.uuid4())
                self.armed = self.button_released = False
                self.vertical_armed = False
                self.events = []
            joy = sample['joystick']
            action = None
            # Require neutral/released after a reconnect; one event per deflection.
            if abs(joy['x']) < .25:
                self.armed = True
            elif abs(joy['x']) > .65 and self.armed:
                action = 'right' if joy['x'] > 0 else 'left'
                self.armed = False
            if abs(joy['y']) < .25:
                self.vertical_armed = True
            elif abs(joy['y']) > .65 and self.vertical_armed and action is None:
                # The installed joystick reports positive Y when physically
                # pushed up; expose the user's physical directions.
                action = 'up' if joy['y'] > 0 else 'down'
                self.vertical_armed = False
            if not joy['pressed']:
                self.button_released = True
            elif self.button_released and action is None:
                action = 'select'
                self.button_released = False
            if action:
                self.event_id += 1
                self.events = (self.events + [{'id': self.event_id, 'action': action}])[-20:]
            self.sequence += 1
            sample['received_at'] = datetime.now(timezone.utc).isoformat()
            self.latest = sample
            self.received = now
            self.state = 'live'

    def _run(self):
        while not self.stop_event.is_set():
            fd = None
            old = None
            try:
                fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
                old = termios.tcgetattr(fd)
                config = termios.tcgetattr(fd)
                config[0] = config[1] = config[3] = 0
                config[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
                config[4] = config[5] = termios.B115200
                config[6][termios.VMIN] = config[6][termios.VTIME] = 0
                termios.tcsetattr(fd, termios.TCSANOW, config)
                buf = b''
                synced = False
                while not self.stop_event.is_set():
                    if not select.select([fd], [], [], .25)[0]:
                        continue
                    chunk = os.read(fd, 16384)
                    if not chunk:
                        raise OSError('Serial disconnected')
                    buf += chunk
                    while b'\n' in buf:
                        line, buf = buf.split(b'\n', 1)
                        if not synced:
                            synced = True
                            continue
                        try:
                            self._accept(json.loads(line))
                        except (ValueError, TypeError, OverflowError):
                            with self.lock:
                                self.invalid += 1
                    if len(buf) > 65536:
                        buf = b''
                        synced = False
                        with self.lock:
                            self.invalid += 1
            except (OSError, termios.error):
                with self.lock:
                    self.state = 'disconnected'
            finally:
                if fd is not None:
                    try:
                        if old is not None:
                            termios.tcsetattr(fd, termios.TCSANOW, old)
                    except (OSError, termios.error):
                        pass
                    os.close(fd)
            self.stop_event.wait(1)
