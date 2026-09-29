import asyncio
import json
import tempfile
import threading
import time
from types import SimpleNamespace
import tracemalloc
import unittest
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

import app
from adapters.recording import Recording, GPX_NAMESPACE
from starlette.datastructures import Headers, URL


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

    def test_gpx_export_skips_oversized_rows_with_a_bounded_read(self):
        self.recorder.append(fix(1))
        self.recorder.stop()
        path = self.recorder.log_path(self.identifier)
        oversized = json.dumps({'type': 'telemetry', 'snapshot': fix(99),
                                'padding': 'x' * 1200}).encode() + b'\n'
        valid = fix(2)
        valid['location']['longitude'] = -113.9
        with path.open('ab') as stream:
            stream.write(oversized)
            stream.write(json.dumps({'type': 'telemetry', 'snapshot': valid}).encode() + b'\n')

        with patch('adapters.recording.MAX_LOG_ROW_BYTES', 1024):
            points = self.points(self.recorder.gps_track(self.identifier))

        self.assertEqual(len(points), 2)
        self.assertEqual(points[-1].attrib['lon'], '-113.9')

    def test_summary_recovery_skips_oversized_rows_and_continues(self):
        self.recorder.append(fix(1))
        self.recorder.stop()
        path = self.recorder.log_path(self.identifier)
        oversized = json.dumps({'type': 'telemetry', 'snapshot': fix(99),
                                'padding': 'x' * 1200}).encode() + b'\n'
        with path.open('ab') as stream:
            stream.write(oversized)
            stream.write(json.dumps({'type': 'telemetry', 'snapshot': fix(2)}).encode() + b'\n')

        with patch('adapters.recording.MAX_LOG_ROW_BYTES', 1024):
            status = Recording(self.directory.name).status()

        self.assertEqual(status['summary']['fix_count'], 2)
        self.assertIn('row exceeded', status['summary']['recovery_warning'])

    def test_trip_summary_counts_distinct_valid_fixes_and_survives_restart(self):
        first = fix(1)
        first['gps']['gps_time'] = '2026-09-23T12:00:00Z'
        second = fix(2)
        second['gps']['gps_time'] = '2026-09-23T12:00:10Z'
        second['location']['longitude'] = -113.999
        jump = fix(3)
        jump['gps']['gps_time'] = '2026-09-23T12:00:20Z'
        jump['location']['longitude'] = -112
        for sample in (first, first, second, jump):
            self.recorder.append(sample)
        active = self.recorder.status()['summary']
        self.assertEqual(active['fix_count'], 3)
        self.assertGreater(active['distance_km'], 0.05)
        self.assertLess(active['distance_km'], 0.1)
        self.assertEqual(active['moving_seconds'], 10)
        self.recorder.stop()
        saved = Recording(self.directory.name).status()['summary']
        self.assertEqual(saved['fix_count'], active['fix_count'])
        self.assertAlmostEqual(saved['distance_km'], active['distance_km'])
        self.assertIsNotNone(saved['stopped_at'])

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

    def test_status_recovers_usable_rows_and_marks_corrupt_or_interrupted_log(self):
        self.recorder.stop()
        path = self.recorder.log_path(self.identifier)
        with path.open('ab') as stream:
            stream.write(b'{"type":"telemetry","snapshot":null}\n\xff\n{"partial":')
        status = Recording(self.directory.name).status()
        self.assertIsNotNone(status['summary'])
        self.assertIn('corrupt', status['summary']['recovery_warning'])
        self.assertEqual(status['recording'], False)

    def test_slow_status_reconstruction_does_not_hold_recorder_lock(self):
        self.recorder.append(fix())
        self.recorder.stop()
        self.recorder._summary_id = None
        entered, release = threading.Event(), threading.Event()
        loads = json.loads
        statuses = []

        def slow_load(line):
            entered.set()
            if not release.wait(3):
                raise TimeoutError('status reader was not released')
            return loads(line)

        reader = threading.Thread(target=lambda: statuses.append(self.recorder.status()))
        with patch('adapters.recording.json.loads', side_effect=slow_load):
            reader.start()
            try:
                self.assertTrue(entered.wait(1))
                start = time.monotonic()
                self.recorder.start()
                self.recorder.append({'source': 'mock'})
                self.assertLess(time.monotonic() - start, .2)
            finally:
                release.set()
                reader.join(3)
        self.assertFalse(reader.is_alive())
        self.assertTrue(statuses)

    def test_start_refuses_to_consume_configured_free_space_reserve(self):
        recorder = Recording(self.directory.name, min_free_bytes=1024)
        with patch('adapters.recording.shutil.disk_usage',
                   return_value=SimpleNamespace(free=1023)):
            with self.assertRaises(OSError):
                recorder.start()
        self.assertFalse(recorder.is_recording())

    def test_periodic_and_clean_stop_sync_recording(self):
        recorder = Recording(self.directory.name, min_free_bytes=0, sync_interval_seconds=1)
        with patch('adapters.recording.os.fsync') as fsync:
            recorder.start()
            with patch('adapters.recording.time.monotonic', return_value=time.monotonic() + 2):
                recorder.append({'source': 'mock'})
            recorder.stop()
        self.assertGreaterEqual(fsync.call_count, 3)

    def test_zip_export_holds_single_export_permit_until_client_close(self):
        self.recorder.append(fix())
        self.recorder.stop()
        archive = self.recorder.export_all()
        try:
            with self.assertRaises(BlockingIOError):
                self.recorder.export_all()
            with ZipFile(archive) as zipped:
                rows = zipped.read(zipped.namelist()[0]).splitlines()
            self.assertGreaterEqual(len(rows), 3)
        finally:
            archive.close()
        self.assertTrue(self.recorder.check_export())

    def test_active_raw_log_export_captures_a_fixed_prefix(self):
        self.recorder.append(fix())
        stream, boundary = self.recorder.log_snapshot(self.identifier)
        try:
            self.recorder.append(fix(2))
            raw = stream.read(boundary)
        finally:
            stream.close()
        self.assertEqual(len(raw.splitlines()), 2)
        self.assertGreater(self.recorder.log_path(self.identifier).stat().st_size, boundary)

    def test_header_and_close_failures_leave_recorder_detached(self):
        class BrokenFile:
            def write(self, _value):
                raise OSError('disk full')
            def close(self):
                raise OSError('close failed')

        self.recorder.stop()
        failed = Recording(self.directory.name, min_free_bytes=0)
        with patch('pathlib.Path.open', return_value=BrokenFile()):
            with self.assertRaisesRegex(OSError, 'disk full'):
                failed.start()
        self.assertFalse(failed.is_recording())
        self.assertIn('disk full', failed.status()['error'])
        self.assertIn('close failed', failed.status()['error'])


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
                client = SimpleNamespace(host='127.0.0.1')
                headers = Headers({'host': '127.0.0.1:8000',
                                    'origin': 'http://127.0.0.1:8000'})
                url = URL('ws://127.0.0.1:8000/ws/telemetry')

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
                             'query_string': b'', 'headers': [(b'host', b'127.0.0.1:8000')],
                             'http_version': '1.1',
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

    async def test_export_disk_failure_returns_503(self):
        with patch.object(app.recordings, 'gps_track', side_effect=OSError('disk full')):
            self.assertEqual(app.recording_gps_track('test').status_code, 503)


class RecordingResponseTests(unittest.TestCase):
    def test_export_response_streams_and_closes_tempfile(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recording(directory)
            identifier = recorder.start()['recording_id']
            recorder.append(fix())
            recorder.stop()
            output = recorder.gps_track(identifier)
            async def run_inline(function, *args):
                return function(*args)
            with patch.object(app.recordings, 'gps_track', return_value=output), \
                 patch.object(app.asyncio, 'to_thread', side_effect=run_inline):
                response = app.recording_gps_track(identifier)
                async def consume():
                    body = b''.join([chunk async for chunk in response.body_iterator])
                    await response.background()
                    return body
                loop = asyncio.new_event_loop()
                try:
                    body = loop.run_until_complete(consume())
                finally:
                    loop.close()
            self.assertEqual(response.status_code, 200)
            self.assertTrue(output.closed)
            self.assertEqual(len(ElementTree.fromstring(body).findall('.//{%s}trkpt' % GPX_NAMESPACE)), 1)
