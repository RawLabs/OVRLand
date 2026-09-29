import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from adapters.alberta_511 import Alberta511


class Alberta511Tests(unittest.TestCase):
    def make_feed(self):
        return Alberta511('secret-key', 51.04, -114.07)

    def finish(self, feed):
        feed.stop_event.set()
        feed.refresh_event.set()

    def result(self, latitude, longitude, source):
        return {'status': 'live', 'updated_at': 'test', 'latitude': latitude,
                'longitude': longitude, 'location_source': source}

    def test_gps_jitter_during_request_does_not_discard_success(self):
        feed = self.make_feed()
        feed.set_location(51.04, -114.07, 'gps')

        def fetch(lat, lon, source):
            feed.set_location(lat + .0001, lon + .0001, source)
            self.finish(feed)
            return self.result(lat, lon, source)

        feed._fetch = fetch
        feed._run()
        snapshot = feed.snapshot()
        self.assertEqual(snapshot['status'], 'live')
        self.assertEqual(snapshot['latitude'], 51.04)
        self.assertEqual(snapshot['diagnostics']['discarded_results'], 0)

    def test_material_move_or_source_change_retries_without_publishing_old_result(self):
        for latitude, source in ((52, 'default'), (51.04, 'gps')):
            with self.subTest(latitude=latitude, source=source):
                feed = self.make_feed()
                requests = []

                def fetch(lat, lon, origin):
                    requests.append((lat, lon, origin))
                    if len(requests) == 1:
                        feed.set_location(latitude, lon, source)
                    else:
                        self.assertEqual(feed.snapshot()['status'], 'waiting')
                        self.finish(feed)
                    return self.result(lat, lon, origin)

                feed._fetch = fetch
                with self.assertLogs('adapters.alberta_511', level='WARNING'):
                    feed._run()
                self.assertEqual(len(requests), 2)
                self.assertEqual(feed.snapshot()['location_source'], source)
                self.assertEqual(feed.snapshot()['diagnostics']['discarded_results'], 1)

    def test_cached_report_becomes_stale_as_soon_as_location_changes(self):
        feed = self.make_feed()
        previous = self.result(51.04, -114.07, 'gps')
        feed.state = previous

        feed.set_location(52, -113, 'gps')

        snapshot = feed.snapshot()
        self.assertEqual(snapshot['status'], 'stale')
        self.assertEqual(snapshot['latitude'], previous['latitude'])
        self.assertEqual(snapshot['longitude'], previous['longitude'])
        self.assertEqual(snapshot['location_source'], 'gps')
        self.assertTrue(feed.refresh_event.is_set())

    def test_http_failure_is_diagnosable_without_leaking_key(self):
        feed = self.make_feed()

        def fetch(*args):
            self.finish(feed)
            raise HTTPError('https://example.test/?key=secret-key', 403,
                            'secret-key rejected', {}, None)

        feed._fetch = fetch
        with self.assertLogs('adapters.alberta_511', level='WARNING') as logs:
            feed._run()
        snapshot = feed.snapshot()
        self.assertEqual(snapshot['status'], 'unavailable')
        self.assertEqual(snapshot['diagnostics']['last_error']['http_status'], 403)
        self.assertEqual(snapshot['diagnostics']['attempts'], 1)
        self.assertEqual(snapshot['diagnostics']['failures'], 1)
        self.assertNotIn('secret-key', json.dumps(snapshot) + str(logs.output))

    def test_success_after_failure_clears_current_error(self):
        feed = self.make_feed()
        attempts = []

        def fetch(lat, lon, source):
            attempts.append(1)
            if len(attempts) == 1:
                feed.refresh_event.set()
                raise TimeoutError('secret-key')
            self.finish(feed)
            return self.result(lat, lon, source)

        feed._fetch = fetch
        with self.assertLogs('adapters.alberta_511', level='WARNING'):
            feed._run()
        snapshot = feed.snapshot()
        self.assertEqual(snapshot['status'], 'live')
        self.assertIsNone(snapshot['diagnostics']['last_error'])
        self.assertEqual(snapshot['diagnostics']['attempts'], 2)
        self.assertEqual(snapshot['diagnostics']['failures'], 1)

    def test_unknown_response_is_not_misreported_as_no_roads(self):
        feed = self.make_feed()
        with patch('adapters.alberta_511.urlopen', return_value=io.BytesIO(b'{"error":"denied"}')):
            with self.assertRaises(ValueError):
                feed._fetch(51.04, -114.07, 'default')
        with patch('adapters.alberta_511.urlopen', return_value=io.BytesIO(b'{"data":[]}')):
            self.assertEqual(feed._fetch(51.04, -114.07, 'default')['report_status'],
                             'no_report_nearby')


if __name__ == '__main__':
    unittest.main()
