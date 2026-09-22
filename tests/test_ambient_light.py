import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from fastapi import Request

import app
from adapters.ambient_light import AmbientLightCalibration, brightness


def local_request():
    return Request({'type': 'http', 'scheme': 'http',
                    'path': '/api/ambient-light/calibration/night', 'root_path': '',
                    'query_string': b'', 'client': ('127.0.0.1', 1234),
                    'server': ('127.0.0.1', 8000),
                    'headers': [(b'host', b'127.0.0.1:8000'),
                                (b'origin', b'http://127.0.0.1:8000')]})


class AmbientLightCalibrationTests(unittest.TestCase):
    def test_capture_persists_raw_rgb_and_relative_brightness(self):
        with tempfile.TemporaryDirectory() as directory:
            calibration = AmbientLightCalibration(Path(directory) / 'ambient.json')
            entry = calibration.capture('night', [3, 4, 3],
                                        datetime(2026, 9, 21, tzinfo=timezone.utc))
            self.assertEqual(entry['brightness_raw'], 3.7)
            self.assertEqual(calibration.entries(), [entry])
            self.assertEqual(json.loads(calibration.path.read_text())['entries'], [entry])

    def test_brightness_requires_complete_numeric_rgb(self):
        self.assertEqual(brightness([10, 20, 30]), 18.6)
        self.assertIsNone(brightness([10, None, 30]))
        self.assertIsNone(brightness([10, 20]))

    def test_capture_endpoint_uses_latest_live_nano_reading(self):
        with tempfile.TemporaryDirectory() as directory:
            calibration = AmbientLightCalibration(Path(directory) / 'ambient.json')
            nano = {'status': 'live', 'data': {'environment': {
                'light_r_raw': 3, 'light_g_raw': 4, 'light_b_raw': 3,
            }}}
            with patch.object(app, 'ambient_light_calibration', calibration), \
                    patch.object(app.nano, 'snapshot', return_value=nano):
                result = app.capture_ambient_light_calibration('night', local_request())
            self.assertEqual(result['entry']['condition'], 'night')
            self.assertEqual(result['entry']['rgb'], [3, 4, 3])
            self.assertEqual(len(result['entries']), 1)

    def test_capture_endpoint_requires_complete_live_rgb(self):
        with patch.object(app.nano, 'snapshot', return_value={'status': 'disconnected', 'data': None}):
            result = app.capture_ambient_light_calibration('day', local_request())
        self.assertEqual(result.status_code, 409)


if __name__ == '__main__':
    unittest.main()
