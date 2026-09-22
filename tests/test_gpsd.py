import json
import time
import unittest
from unittest.mock import MagicMock, patch

from adapters.gpsd import GPSD, WATCH, normalize_tpv


class GPSDTests(unittest.TestCase):
    def test_fix_loss_clears_location_immediately_and_recovers(self):
        gps = GPSD()
        fix = {'class': 'TPV', 'mode': 3, 'lat': 40.1, 'lon': -111.2, 'track': 27}
        gps._accept(fix)
        self.assertEqual(gps.snapshot()['status'], 'live')

        gps._accept({'class': 'TPV', 'mode': 1})
        reading = gps.snapshot()
        self.assertEqual(reading['status'], 'no_fix')
        self.assertIsNone(reading['data'])
        self.assertIsNone(reading['age_ms'])

        import app
        with patch.object(app, 'MODE', 'live'), \
             patch.object(app, 'gps', gps), \
             patch.object(app.nano, 'snapshot', return_value={'status': 'unavailable', 'data': None}):
            data = app.snapshot()
        self.assertEqual(data['sources']['gps'], 'no_fix')
        for key in ('latitude', 'longitude', 'heading_deg'):
            self.assertIsNone(data['location'][key])

        gps._accept(dict(fix, lat=40.2))
        self.assertEqual(gps.snapshot()['status'], 'live')
        self.assertEqual(gps.snapshot()['data']['latitude'], 40.2)

    def test_disconnect_clears_fix_before_reconnect(self):
        for failure in (b'', OSError('connection reset')):
            with self.subTest(failure=failure):
                gps = GPSD(reconnect_seconds=0)
                connection = MagicMock()
                connection.__enter__.return_value = connection
                report = {'class': 'TPV', 'mode': 3, 'lat': 40.1, 'lon': -111.2}
                connection.recv.side_effect = [json.dumps(report).encode() + b'\n', failure]
                gps._accept({'class': 'SKY', 'satellites': [{'used': True}]})
                between_connections = []

                def reconnect():
                    between_connections.append(gps.snapshot())
                    gps.stop_event.set()
                    return connection

                with patch('adapters.gpsd.socket.create_connection') as connect:
                    # Capture state when the next connection starts, before any new fix.
                    connect.side_effect = lambda *args, **kwargs: (
                        connection if connect.call_count == 1 else reconnect())
                    gps._run()

                reading = between_connections[0]
                self.assertEqual(reading['status'], 'disconnected')
                self.assertIsNone(reading['data'])
                self.assertIsNone(reading['age_ms'])
                self.assertIsNone(reading['satellites_seen'])
                self.assertIsNone(reading['satellites_used'])
                self.assertEqual(gps.snapshot()['status'], 'connected')
                self.assertIsNone(gps.snapshot()['data'])

    def test_normalize_requires_fix_and_prefers_msl_altitude(self):
        self.assertIsNone(normalize_tpv({'class': 'TPV', 'mode': 1, 'lat': 1, 'lon': 2}))
        fix = normalize_tpv({'class': 'TPV', 'mode': 3, 'lat': 38.5, 'lon': -109.5,
                             'alt': 3, 'altHAE': 4, 'altMSL': 5, 'track': 361,
                             'epy': 8, 'epx': 7})
        self.assertEqual(fix['altitude_m'], 5)
        self.assertEqual(fix['accuracy_m'], 7)
        self.assertEqual(fix['heading_deg'], 1)

    def test_reads_watch_stream_and_sky(self):
        reports = [
            {'class': 'SKY', 'satellites': [{'used': True}, {'used': False}]},
            {'class': 'TPV', 'mode': 3, 'lat': 40.1, 'lon': -111.2, 'altHAE': 1500},
        ]

        class Connection:
            def __init__(self):
                self.chunks = [b''.join(json.dumps(item).encode() + b'\n' for item in reports)]
                self.sent = None
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def settimeout(self, _): pass
            def sendall(self, data): self.sent = data
            def recv(self, _):
                if self.chunks:
                    return self.chunks.pop(0)
                time.sleep(.01)
                raise TimeoutError

        connection = Connection()
        gps = GPSD(reconnect_seconds=.05)
        with patch('adapters.gpsd.socket.create_connection', return_value=connection):
            gps.start()
            try:
                deadline = time.monotonic() + 2
                while gps.snapshot()['data'] is None and time.monotonic() < deadline:
                    time.sleep(.01)
                reading = gps.snapshot()
                self.assertEqual(connection.sent, WATCH)
                self.assertEqual(reading['data']['latitude'], 40.1)
                self.assertEqual(reading['satellites_seen'], 2)
                self.assertEqual(reading['satellites_used'], 1)
            finally:
                gps.stop()

    def test_optional_numbers_fall_back_to_first_valid_value(self):
        cases = [
            ({'altHAE': 1500, 'epy': 5}, 1500, 5),
            ({'alt': -20, 'eph': 8}, -20, 8),
            ({'altMSL': None, 'altHAE': 100, 'epx': None, 'epy': 3}, 100, 3),
            ({'altMSL': float('nan'), 'altHAE': float('inf'), 'alt': 12,
              'epx': True, 'epy': 'bad', 'eph': 4}, 12, 4),
            ({'altMSL': 0, 'altHAE': 100, 'epx': 0, 'epy': 3}, 0, 0),
            ({}, None, None),
        ]
        for fields, altitude, accuracy in cases:
            with self.subTest(fields=fields):
                fix = normalize_tpv({'class': 'TPV', 'mode': 3, 'lat': 40,
                                     'lon': -111, **fields})
                self.assertEqual(fix['altitude_m'], altitude)
                self.assertEqual(fix['accuracy_m'], accuracy)

    def test_live_snapshot_uses_fix_and_preserves_baro_without_gps_altitude(self):
        import app
        nano_reading = {
            'status': 'live', 'data': {
                'environment': {'altitude_m': 1234},
                'attitude': {}, 'imu': {}, 'joystick': None, 'received_at': 'now',
            },
        }
        gps_reading = {
            'status': 'live', 'age_ms': 1, 'satellites_seen': 8, 'satellites_used': 5,
            'data': {'latitude': 40.1, 'longitude': -111.2, 'altitude_m': None,
                     'heading_deg': 27, 'accuracy_m': 4, 'mode': 2, 'gps_time': None,
                     'received_at': 'now'},
        }
        with patch.object(app, 'MODE', 'live'), \
             patch.object(app.nano, 'snapshot', return_value=nano_reading), \
             patch.object(app.gps, 'snapshot', return_value=gps_reading):
            data = app.snapshot()
        self.assertEqual(data['location']['latitude'], 40.1)
        self.assertEqual(data['location']['altitude_m'], 1234)
        self.assertEqual(data['location']['altitude_source'], 'barometric')
        self.assertEqual(data['gps']['accuracy_m'], 4)

    def test_altitude_provenance_follows_selected_reading(self):
        import app
        for baro, gps_altitude, expected_altitude, expected_source in (
            (1234, 1500, 1500, 'gps'),
            (1234, 0, 0, 'gps'),
            (0, None, 0, 'barometric'),
            (None, 1500, 1500, 'gps'),
            (None, None, None, None),
        ):
            with self.subTest(baro=baro, gps_altitude=gps_altitude):
                nano_reading = {'status': 'live', 'data': {
                    'environment': {'altitude_m': baro}, 'attitude': {},
                    'imu': {}, 'joystick': None, 'received_at': 'now',
                }}
                gps_reading = {'status': 'live', 'data': {
                    'latitude': 40, 'longitude': -111, 'altitude_m': gps_altitude,
                }}
                with patch.object(app, 'MODE', 'live'), \
                     patch.object(app.nano, 'snapshot', return_value=nano_reading), \
                     patch.object(app.gps, 'snapshot', return_value=gps_reading):
                    data = app.snapshot()
                self.assertEqual(data['location']['altitude_m'], expected_altitude)
                self.assertEqual(data['location']['altitude_source'], expected_source)

        with patch.object(app, 'MODE', 'mock'):
            self.assertEqual(app.snapshot()['location']['altitude_source'], 'mock')
        with patch.object(app, 'MODE', 'live'), \
             patch.object(app.nano, 'snapshot', return_value={'status': 'unavailable', 'data': None}), \
             patch.object(app.gps, 'snapshot', return_value={'status': 'no_fix', 'data': None}):
            data = app.snapshot()
        self.assertIsNone(data['location']['altitude_m'])
        self.assertIsNone(data['location']['altitude_source'])


if __name__ == '__main__':
    unittest.main()
