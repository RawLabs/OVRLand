import asyncio
import json
import tempfile
import threading
import time
import tracemalloc
import unittest
from unittest.mock import patch
from xml.etree import ElementTree

import app
from adapters.recording import Recording, GPX_NAMESPACE


def fix(number=1):
    return {'source': 'live', 'sources': {'gps': 'live'},
            'gps': {'received_at': number}, 'timestamp': '2026-09-23T12:00:00Z',
            'location': {'latitude': 51, 'longitude': -114,
                         'altitude_m': 1000, 'altitude_source': 'gps'}}


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.recorder = Recording(self.directory.name)
        self.identifier = self.recorder.start()['recording_id']
        self.addCleanup(self.recorder.stop)

    def points(self, output):
        with output:
            return ElementTree.parse(output).findall('.//{%s}trkpt' % GPX_NAMESPACE)

    def test_export_filters_duplicates_non_live_and_malformed_tail(self):
        self.recorder.append(fix())
        self.recorder.append(fix())
        for change in ({'source': 'mock'}, {'sources': {'gps': 'stale'}},
                       {'location': {'latitude': 91, 'longitude': 0}}):
            self.recorder.append(fix(2) | change)
        self.recorder.append(fix(3) | {'timestamp': 'a<&b'})
        self.recorder.stop()
        with self.recorder.log_path(self.identifier).open('ab') as stream:
            stream.write(b'null\n[]\ninvalid\n\xff\n{"partial":')
        points = self.points(self.recorder.gps_track(self.identifier))
        self.assertEqual(len(points), 2)
        self.assertEqual(points[0].find('{%s}ele' % GPX_NAMESPACE).text, '1000')
        self.assertEqual(points[1].find('{%s}time' % GPX_NAMESPACE).text, 'a<&b')
        self.assertIsNone(self.recorder.gps_track('../invalid'))

    def test_export_boundary_excludes_concurrent_append_and_stop(self):
        self.recorder.append(fix())
        entered, release = threading.Event(), threading.Event()
        loads = json.loads
        result = []
        errors = []

        def slow_load(line):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('test reader not released')
            return loads(line)

        def export():
            try:
                result.append(self.recorder.gps_track(self.identifier))
            except BaseException as error:
                errors.append(error)

        with patch('adapters.recording.json.loads', side_effect=slow_load):
            worker = threading.Thread(target=export)
            worker.start()
            try:
                self.assertTrue(entered.wait(1))
                # Both operations must complete while parsing remains blocked.
                self.recorder.append(fix(2))
                self.recorder.stop()
            finally:
                release.set()
                worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)
        self.assertEqual(len(self.points(result[0])), 1)

    def test_export_memory_does_not_grow_with_track_length(self):
        self.recorder.stop()
        path = self.recorder.log_path(self.identifier)
        peaks = []
        for count in (1000, 36000):  # Two hours at 5 Hz.
            with path.open('w') as stream:
                for index in range(count):
                    stream.write(json.dumps({'type': 'telemetry', 'snapshot': fix(index)}) + '\n')
            tracemalloc.start()
            try:
                with self.recorder.gps_track(self.identifier) as output:
                    output.seek(0, 2)
                    self.assertGreater(output.tell(), count * 50)
                peaks.append(tracemalloc.get_traced_memory()[1])
            finally:
                tracemalloc.stop()
        self.assertLess(peaks[1], peaks[0] + 512 * 1024)


class RecordingAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_sampler_lock_wait_and_failure_leave_event_loop_responsive(self):
        entered, release = threading.Event(), threading.Event()
        loop_thread = threading.get_ident()
        calls = []

        class SlowRecorder:
            def is_recording(self):
                calls.append(('check', threading.get_ident()))
                entered.set()
                release.wait(2)
                return True

            def append(self, snapshot):
                calls.append(('append', threading.get_ident()))
                raise OSError('disk full')

            def fail(self, error):
                calls.append(('fail', threading.get_ident()))
                time.sleep(.25)

        with patch.object(app, 'recordings', SlowRecorder()), patch.object(app, 'snapshot', return_value={}):
            sampler = asyncio.create_task(app.recording_sampler())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                start = time.monotonic()
                await asyncio.sleep(.03)
                self.assertLess(time.monotonic() - start, .2)
                release.set()
                await asyncio.sleep(.05)
                start = time.monotonic()
                await asyncio.sleep(.03)
                self.assertLess(time.monotonic() - start, .2)
                await asyncio.sleep(.3)
            finally:
                release.set()
                sampler.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await sampler
        self.assertTrue({'check', 'append', 'fail'} <= {name for name, _ in calls})
        self.assertTrue(all(thread != loop_thread for _, thread in calls))

    async def test_slow_export_allows_recording_telemetry_and_http_health(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recording(directory)
            identifier = recorder.start()['recording_id']
            for index in range(20):
                recorder.append(fix(index))
            loads = json.loads
            entered = threading.Event()

            def slow_load(line):
                entered.set()
                time.sleep(.025)
                return loads(line)

            ticks = []

            class Socket:
                async def accept(self):
                    pass

                async def send_json(self, data):
                    ticks.append(time.monotonic())

            with patch.object(app, 'recordings', recorder), patch.object(app, 'snapshot', side_effect=fix), \
                    patch('adapters.recording.json.loads', side_effect=slow_load):
                export = asyncio.create_task(asyncio.to_thread(recorder.gps_track, identifier))
                sampler = asyncio.create_task(app.recording_sampler())
                telemetry = asyncio.create_task(app.stream(Socket()))
                try:
                    self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                    scope = {'type': 'http', 'asgi': {'version': '3.0'}, 'method': 'GET',
                             'scheme': 'http', 'path': '/api/telemetry', 'root_path': '',
                             'query_string': b'', 'headers': [], 'http_version': '1.1',
                             'server': ('127.0.0.1', 8000), 'client': ('127.0.0.1', 1)}
                    messages = []

                    async def receive():
                        return {'type': 'http.request', 'body': b''}

                    async def send(message):
                        messages.append(message)

                    await asyncio.wait_for(app.app(scope, receive, send), timeout=.8)
                    self.assertEqual(messages[0]['status'], 200)
                    output = await asyncio.wait_for(export, timeout=3)
                    output.close()
                    self.assertGreaterEqual(len(ticks), 3)
                    self.assertLess(max(b - a for a, b in zip(ticks, ticks[1:])), .4)
                finally:
                    for task in (sampler, telemetry):
                        task.cancel()
                    await asyncio.gather(sampler, telemetry, return_exceptions=True)
                    await asyncio.to_thread(recorder.stop)
            rows = recorder.log_path(identifier).read_text().splitlines()
            self.assertGreater(len(rows), 22)  # New sampler rows during export.

    async def test_export_response_streams_and_closes_tempfile(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recording(directory)
            identifier = recorder.start()['recording_id']
            recorder.append(fix())
            recorder.stop()
            output = recorder.gps_track(identifier)
            with patch.object(app.recordings, 'gps_track', return_value=output):
                response = app.recording_gps_track(identifier)
            body = b''.join([chunk async for chunk in response.body_iterator])
            self.assertEqual(response.status_code, 200)
            self.assertTrue(output.closed)
            self.assertEqual(len(ElementTree.fromstring(body).findall('.//{%s}trkpt' % GPX_NAMESPACE)), 1)
            await response.background()

    async def test_export_disk_failure_returns_503(self):
        with patch.object(app.recordings, 'gps_track', side_effect=OSError('disk full')):
            self.assertEqual(app.recording_gps_track('test').status_code, 503)
