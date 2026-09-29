import unittest
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from fastapi import Request
from starlette.datastructures import Headers, URL
from starlette.responses import Response

import app


def local_request():
    return Request({'type': 'http', 'scheme': 'http', 'path': '/api/system/poweroff-pi',
                    'root_path': '', 'query_string': b'', 'client': ('127.0.0.1', 1234),
                    'server': ('127.0.0.1', 8000),
                    'headers': [(b'host', b'127.0.0.1:8000'),
                                (b'origin', b'http://127.0.0.1:8000')]})


class ShutdownRequestTests(unittest.IsolatedAsyncioTestCase):
    def test_stop_request_creates_launcher_signal(self):
        with tempfile.TemporaryDirectory() as directory:
            signal_file = Path(directory) / 'state' / 'stop-requested'
            with patch.object(app, 'STOP_REQUEST_FILE', signal_file):
                self.assertTrue(app.request_kiosk_stop())
            self.assertTrue(signal_file.is_file())

    async def test_stop_app_does_not_stop_service_if_launcher_signal_fails(self):
        with patch.object(app, 'MODE', 'live'), \
             patch.object(app, 'request_kiosk_stop', return_value=False), \
             patch.object(app, 'stop_app') as stop:
            result = await app.system_action('stop-app', local_request())
        self.assertEqual(result.status_code, 503)
        stop.assert_not_called()

    async def test_telemetry_websocket_sends_snapshots(self):
        ws = AsyncMock()
        ws.client = SimpleNamespace(host='127.0.0.1')
        ws.url = URL('ws://127.0.0.1:8000/ws/telemetry')
        ws.headers = Headers({'host': '127.0.0.1:8000', 'origin': 'http://127.0.0.1:8000'})
        with patch.object(app.asyncio, 'sleep', side_effect=app.WebSocketDisconnect()):
            await app.stream(ws)
        ws.accept.assert_awaited_once_with()
        ws.send_json.assert_awaited_once()

    async def test_websocket_rejects_untrusted_peer_host_and_origin(self):
        for peer, host, origin in (
            ('10.0.0.2', '127.0.0.1:8000', 'http://127.0.0.1:8000'),
            ('127.0.0.1', 'attacker.example', 'http://attacker.example'),
            ('127.0.0.1', '127.0.0.1:8000', 'null'),
            ('127.0.0.1', '127.0.0.1:8000', None),
            ('127.0.0.1', '127.0.0.1:8000', ['http://127.0.0.1:8000', 'http://evil']),
        ):
            with self.subTest(peer=peer, host=host, origin=origin):
                ws = AsyncMock()
                ws.client = SimpleNamespace(host=peer)
                ws.url = URL(f'ws://{host}/ws/telemetry')
                headers = {'host': host}
                if origin:
                    headers['origin'] = origin if isinstance(origin, str) else ','.join(origin)
                ws.headers = Headers(headers)
                await app.stream(ws)
                ws.close.assert_awaited_once_with(code=1008)
                ws.accept.assert_not_awaited()

    async def test_window_mode_can_switch_between_supported_modes(self):
        original_mode = app.window_mode
        try:
            self.assertEqual(app.set_window_mode('camp', local_request()), {'status': 'switching', 'mode': 'camp'})
            self.assertEqual(app.get_window_mode().body, b'camp')
            self.assertEqual(app.set_window_mode('fullscreen', local_request()), {'status': 'switching', 'mode': 'fullscreen'})
        finally:
            app.window_mode = original_mode

    async def test_unknown_window_mode_is_rejected(self):
        response = app.set_window_mode('unknown', local_request())
        self.assertEqual(response.status_code, 404)

    async def test_poweroff_control_starts_system_command(self):
        original_mode = app.MODE
        async def run_inline(function, *args):
            return function(*args)
        try:
            app.MODE = 'live'
            with patch('app.shutil.which', return_value='/usr/bin/systemctl'), \
                 patch('app.subprocess.Popen') as poweroff, \
                 patch.object(app.asyncio, 'to_thread', side_effect=run_inline) as offload:
                poweroff.return_value.wait.return_value = 0
                result = await app.system_action('poweroff-pi', local_request())
            self.assertEqual(result, {'status': 'powering-off', 'action': 'poweroff-pi'})
            poweroff.assert_called_once_with(['/usr/bin/systemctl', 'poweroff'], start_new_session=True, close_fds=True)
            offload.assert_awaited_once_with(app.power_off_pi)
        finally:
            app.MODE = original_mode

    async def test_mock_mode_never_runs_poweroff(self):
        original_mode = app.MODE
        try:
            app.MODE = 'mock'
            with patch('app.subprocess.Popen') as poweroff:
                result = await app.system_action('poweroff-pi', local_request())
            self.assertEqual(result, {'status': 'simulated', 'action': 'poweroff-pi'})
            poweroff.assert_not_called()
        finally:
            app.MODE = original_mode


class SystemAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_global_host_guard_and_dashboard_anti_framing_headers(self):
        for path in ('/api/telemetry', '/api/recording/status', '/static/index.html'):
            request = SimpleNamespace(headers=Headers({'host': 'attacker.example'}),
                                      url=URL(f'http://attacker.example{path}'))
            next_layer = AsyncMock(return_value=Response())
            response = await app.local_host_and_frame_policy(request, next_layer)
            self.assertEqual(response.status_code, 421)
            next_layer.assert_not_awaited()
        for path in ('/', '/static/index.html'):
            request = SimpleNamespace(headers=Headers({'host': '127.0.0.1:8000'}),
                                      url=URL(f'http://127.0.0.1:8000{path}'))
            response = await app.local_host_and_frame_policy(request, AsyncMock(return_value=Response()))
            self.assertEqual(response.headers['content-security-policy'], "frame-ancestors 'none'")
            self.assertEqual(response.headers['x-frame-options'], 'DENY')

    async def post(self, action, peer='127.0.0.1', host='127.0.0.1:8000',
                   origin='http://127.0.0.1:8000', extra_headers=()):
        scope = dict(local_request().scope)
        scope.update(method='POST', http_version='1.1',
                     path=f'/api/system/{action}',
                     client=(peer, 1234) if peer else None)
        scope['headers'] = [(b'host', host.encode()), *extra_headers]
        if origin is not None:
            scope['headers'].append((b'origin', origin.encode()))
        messages = []

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(message):
            messages.append(message)

        await app.app(scope, receive, send)
        return next(message['status'] for message in messages
                    if message['type'] == 'http.response.start')

    async def test_untrusted_requests_never_dispatch_system_actions(self):
        cases = [
            {'peer': '10.42.0.3'},
            {'peer': '::ffff:10.42.0.3'},
            {'peer': None},
            {'peer': 'localhost'},
            {'origin': None},
            {'origin': 'null'},
            {'origin': 'http://evil.example'},
            {'origin': 'http://127.0.0.1:9000'},
            {'host': 'evil.example', 'origin': 'http://evil.example'},
            {'origin': 'http://127.0.0.1:8000@evil.example'},
            {'extra_headers': [(b'origin', b'http://evil.example')]},
            {'peer': '10.42.0.3', 'extra_headers': [
                (b'x-forwarded-for', b'127.0.0.1'),
                (b'forwarded', b'for=127.0.0.1;host=127.0.0.1:8000')]},
        ]
        for mode in ('live', 'mock'):
            for action in ('stop-app', 'poweroff-pi'):
                for case in cases:
                    with self.subTest(mode=mode, action=action, case=case), \
                         patch.object(app, 'MODE', mode), \
                         patch.object(app, 'request_kiosk_stop', return_value=True) as request_stop, \
                         patch.object(app, 'stop_app') as stop, \
                         patch.object(app, 'power_off_pi') as power:
                        expected = 421 if case.get('host') == 'evil.example' else 403
                        self.assertEqual(await self.post(action, **case), expected)
                        request_stop.assert_not_called()
                        stop.assert_not_called()
                        power.assert_not_called()

    async def test_local_dashboard_controls_remain_available(self):
        async def run_inline(function, *args):
            return function(*args)
        for peer, host in (('127.0.0.1', '127.0.0.1:8000'),
                           ('127.0.0.1', 'localhost:8000'), ('::1', '[::1]:8000')):
            for mode in ('live', 'mock'):
                for action in ('stop-app', 'poweroff-pi'):
                    with self.subTest(peer=peer, mode=mode, action=action), \
                         patch.object(app, 'MODE', mode), \
                         patch.object(app, 'request_kiosk_stop', return_value=True) as request_stop, \
                         patch.object(app, 'stop_app') as stop, \
                         patch.object(app, 'power_off_pi', return_value=True) as power, \
                         patch.object(app.asyncio, 'to_thread', side_effect=run_inline):
                        self.assertEqual(await self.post(action, peer, host, f'http://{host}'), 200)
                        self.assertEqual(stop.call_count, int(mode == 'live' and action == 'stop-app'))
                        self.assertEqual(request_stop.call_count, int(mode == 'live' and action == 'stop-app'))
                        self.assertEqual(power.call_count, int(mode == 'live' and action == 'poweroff-pi'))

    async def test_unknown_action_and_poweroff_failure_keep_status_codes(self):
        self.assertEqual(await self.post('unknown'), 404)
        async def run_inline(function, *args):
            return function(*args)
        with patch.object(app, 'MODE', 'live'), patch.object(app, 'power_off_pi', return_value=False), \
             patch.object(app.asyncio, 'to_thread', side_effect=run_inline):
            self.assertEqual(await self.post('poweroff-pi'), 503)

    async def test_window_mode_rejects_untrusted_requests(self):
        scope = dict(local_request().scope)
        scope.update(method='POST', path='/api/window-mode/camp', client=('10.42.0.3', 1234))
        scope['headers'] = [(b'host', b'127.0.0.1:8000'), (b'origin', b'http://evil.example')]
        response = app.set_window_mode('camp', Request(scope))
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
