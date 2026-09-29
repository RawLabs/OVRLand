import json
import math
import os
import pty
import time
import unittest
from unittest.mock import patch

from adapters.nano import Nano, normalize


def sample(**changes):
    return {'type': 'joystick', 'ms': 100, 'x': 0., 'y': 0., 'pressed': False,
            # Side-mounted Nano: level gravity is -Y, not +Z.
            'imu_ok': True, 'ax': 0., 'ay': -1., 'az': 0.,
            'env_ok': True, 'temp_c': 25., 'humidity_pct': 40.,
            'baro_ok': True, 'pressure_kpa': 89., 'altitude_m': 1000.,
            'apds_ok': True, 'color_r': 3, **changes}


class NanoTests(unittest.TestCase):
    def test_tilt_and_failed_sensor(self):
        data = normalize(sample(ax=.5, ay=-math.sqrt(.75), env_ok=False))
        self.assertEqual(data['attitude']['pitch_deg'], 0)
        self.assertEqual(data['attitude']['roll_deg'], -30)
        self.assertIsNone(data['environment']['temperature_c'])
        self.assertIsNone(normalize(sample(ay=0, az=0))['attitude']['roll_deg'])
        self.assertIsNone(normalize(sample(ax=float('nan')))['attitude']['pitch_deg'])
        with self.assertRaises(ValueError):
            normalize(sample(x=2))

    def test_joystick_center_jitter_is_suppressed(self):
        data = normalize(sample(x=.012, y=-.021))
        self.assertEqual(data['joystick']['x'], 0.0)
        self.assertEqual(data['joystick']['y'], 0.0)
        self.assertEqual(normalize(sample(x=.127))['joystick']['x'], .13)

    def test_joystick_vertical_edges_emit_up_and_down(self):
        nano = Nano('/not-used')
        nano._accept(sample(y=0.0))
        nano._accept(sample(y=1.0))
        nano._accept(sample(y=0.0))
        nano._accept(sample(y=-1.0))
        self.assertEqual([event['action'] for event in nano.snapshot()['events']], ['up', 'down'])

    def test_joystick_edges_reconnect_and_stale(self):
        nano = Nano('/not-used')
        nano._accept(sample(x=1, pressed=True))
        self.assertEqual(nano.snapshot()['events'], [])

        nano._accept(sample())
        nano._accept(sample(x=1))
        nano._accept(sample(x=1))
        nano._accept(sample(pressed=True))
        self.assertEqual([e['action'] for e in nano.snapshot()['events']], ['right', 'select'])
        original_session = nano.snapshot()['session']
        with patch('adapters.nano.time.monotonic', return_value=nano.received + 3):
            self.assertEqual(nano.snapshot()['status'], 'stale')
            self.assertIsNone(nano.snapshot()['data'])
            nano._accept(sample(x=-1, pressed=True))
        self.assertNotEqual(nano.snapshot()['session'], original_session)
        self.assertEqual(nano.snapshot()['events'], [])

    def test_serial_fragmentation_bad_line_and_disconnect(self):
        master, slave = pty.openpty()
        nano = Nano(os.ttyname(slave))
        nano.start()
        try:
            time.sleep(.1)
            os.write(master, b'partial\ninvalid\n')
            line = json.dumps(sample()).encode() + b'\n'
            os.write(master, line[:20])
            time.sleep(.05)
            os.write(master, line[20:])
            end = time.monotonic() + 2
            while nano.snapshot()['status'] != 'live' and time.monotonic() < end:
                time.sleep(.01)
            self.assertEqual(nano.snapshot()['status'], 'live')
            self.assertEqual(nano.snapshot()['invalid_lines'], 1)
            os.close(master)
            master = None
            end = time.monotonic() + 2
            while nano.snapshot()['status'] != 'disconnected' and time.monotonic() < end:
                time.sleep(.01)
            self.assertIsNone(nano.snapshot()['data'])
        finally:
            nano.stop()
            if master is not None:
                os.close(master)
            os.close(slave)

    def test_live_api_never_uses_mock_vehicle_or_gps(self):
        import app
        with patch.object(app, 'MODE', 'live'):
            data = app.snapshot()
        self.assertIsNone(data['vehicle']['speed_mph'])
        self.assertIsNone(data['location']['latitude'])
        self.assertIsNone(data['location']['heading_deg'])
        self.assertEqual(data['source'], 'live')

    def test_ble_sensor_telemetry_has_no_dashboard_control_authority(self):
        import app
        reading = {'status': 'live', 'data': {
            'environment': {'temperature_c': 20, 'altitude_m': 0}, 'attitude': {}, 'imu': {},
            'joystick': {'x': 1, 'pressed': True}, 'received_at': 'now',
        }}
        gps = {'status': 'no_fix', 'data': None, 'last_location': None}
        with patch.object(app, 'MODE', 'live'), patch.object(app, 'NANO_TRANSPORT', 'ble'), \
             patch.object(app.nano, 'snapshot', return_value=reading), \
             patch.object(app.gps, 'snapshot', return_value=gps), \
             patch.object(app.network, 'snapshot', return_value={'status': 'unavailable'}), \
             patch.object(app.weather, 'set_location'), patch.object(app.weather, 'snapshot', return_value={'status': 'waiting'}), \
             patch.object(app.road_conditions, 'set_location'), patch.object(app.road_conditions, 'snapshot', return_value={'status': 'waiting'}):
            data = app.snapshot()
        self.assertIsNone(data['joystick'])
        self.assertEqual(data['environment']['temperature_c'], 20)


if __name__ == '__main__':
    unittest.main()
