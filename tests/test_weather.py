import threading
import time
import unittest
from unittest.mock import patch

from adapters.weather import Weather


def result(latitude, longitude, source):
    return {'status': 'live', 'latitude': latitude, 'longitude': longitude,
            'location_source': source, 'updated_at': 'now'}


class WeatherPublicationTests(unittest.TestCase):
    def test_small_gps_jitter_publishes_the_coordinates_actually_fetched(self):
        weather = Weather(51, -114, refresh_seconds=60)
        entered, release = threading.Event(), threading.Event()

        def fetch(latitude, longitude, source):
            entered.set()
            release.wait(2)
            return result(latitude, longitude, source)

        with patch.object(weather, '_fetch', side_effect=fetch):
            weather.start()
            try:
                self.assertTrue(entered.wait(1))
                weather.set_location(51.00001, -114, 'default')
                release.set()
                deadline = time.monotonic() + 1
                while weather.snapshot()['status'] != 'live' and time.monotonic() < deadline:
                    time.sleep(.01)
                snapshot = weather.snapshot()
                self.assertEqual(snapshot['status'], 'live')
                self.assertEqual((snapshot['latitude'], snapshot['longitude']), (51, -114))
            finally:
                release.set()
                weather.stop()

    def test_superseded_location_is_stale_until_prompt_replacement(self):
        weather = Weather(51, -114, refresh_seconds=60)
        entered, release = threading.Event(), threading.Event()
        calls = []

        def fetch(latitude, longitude, source):
            calls.append((latitude, longitude, source))
            if len(calls) == 1:
                entered.set()
                release.wait(2)
            return result(latitude, longitude, source)

        with patch.object(weather, '_fetch', side_effect=fetch):
            weather.start()
            try:
                self.assertTrue(entered.wait(1))
                weather.set_location(51.2, -114, 'gps')
                release.set()
                deadline = time.monotonic() + 1
                while len(calls) < 2 and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertGreaterEqual(len(calls), 2)
                current = weather.snapshot()
                self.assertEqual(current['status'], 'live')
                self.assertEqual((current['latitude'], current['location_source']),
                                 (51.2, 'gps'))
            finally:
                release.set()
                weather.stop()

    def test_failed_refresh_marks_cached_weather_stale(self):
        weather = Weather(51, -114)
        weather.state = result(51, -114, 'default')
        try:
            with patch.object(weather, '_fetch', side_effect=OSError('offline')):
                weather.start()
                weather.refresh_event.set()
                deadline = time.monotonic() + 1
                while weather.snapshot()['status'] == 'live' and time.monotonic() < deadline:
                    time.sleep(.01)
            self.assertEqual(weather.snapshot()['status'], 'stale')
        finally:
            weather.stop()
