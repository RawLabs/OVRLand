import threading
import unittest

from adapters.alberta_511 import Alberta511
from adapters.nano_ble import expand_record
from adapters.weather import Weather


class FeedWorkerTests(unittest.TestCase):
    def check_stop_and_location_refresh(self, feed):
        fetched = threading.Event()
        requests = []

        def fetch(latitude, longitude, source):
            requests.append((latitude, longitude, source))
            fetched.set()
            return {'status': 'live', 'latitude': latitude, 'longitude': longitude,
                    'location_source': source, 'updated_at': 'test'}

        feed._fetch = fetch
        feed.start()
        self.assertTrue(fetched.wait(1))
        feed.stop()
        self.assertFalse(feed.thread.is_alive())
        self.assertEqual(len(requests), 1)

        feed.stop_event.clear()
        feed.start()
        self.assertTrue(feed.thread.is_alive())
        feed.set_location(52, -115, 'gps')
        self.assertTrue(feed.refresh_event.wait(1))
        self.assertEqual(feed.snapshot()['location_source'], 'default')
        feed.stop()

    def test_weather_worker_stops_and_does_not_relabel_cached_default(self):
        self.check_stop_and_location_refresh(Weather(51, -114, refresh_seconds=60))

    def test_511_worker_stops_and_does_not_relabel_cached_default(self):
        self.check_stop_and_location_refresh(Alberta511('test-key', 51, -114, refresh_seconds=60))

    def test_gradual_location_updates_compare_to_last_fetch_position(self):
        feed = Weather(51, -114)
        feed._refresh_latitude, feed._refresh_longitude = 51, -114
        for index in range(1, 101):
            feed.set_location(51 + index * .001, -114, 'default')
        self.assertTrue(feed.refresh_event.is_set())


class BleValidationTests(unittest.TestCase):
    def test_non_object_json_records_are_rejected_as_value_errors(self):
        for value in (None, [], 4, 'text'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                expand_record(value)


if __name__ == '__main__':
    unittest.main()
