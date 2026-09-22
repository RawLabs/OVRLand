import unittest
from unittest.mock import AsyncMock, patch
from fastapi import Request

import app


def local_request():
    return Request({'type': 'http', 'scheme': 'http', 'path': '/api/system/poweroff-pi',
                    'root_path': '', 'query_string': b'', 'client': ('127.0.0.1', 1234),
                    'server': ('127.0.0.1', 8000),
                    'headers': [(b'host', b'127.0.0.1:8000'),
                                (b'origin', b'http://127.0.0.1:8000')]})


class ShutdownRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_telemetry_websocket_sends_snapshots(self):
        ws = AsyncMock()
        with patch.object(app.asyncio, 'sleep', side_effect=app.WebSocketDisconnect()):
            await app.stream(ws)
        ws.accept.assert_awaited_once_with()
        ws.send_json.assert_awaited_once()

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
        try:
            app.MODE = 'live'
            with patch('app.shutil.which', return_value='/usr/bin/systemctl'), patch('app.subprocess.Popen') as poweroff:
                poweroff.return_value.poll.return_value = None
                result = await app.system_action('poweroff-pi', local_request())
            self.assertEqual(result, {'status': 'powering-off', 'action': 'poweroff-pi'})
            poweroff.assert_called_once_with(['/usr/bin/systemctl', 'poweroff'], start_new_session=True, close_fds=True)
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
                         patch.object(app, 'stop_app') as stop, \
                         patch.object(app, 'power_off_pi') as power:
                        self.assertEqual(await self.post(action, **case), 403)
                        stop.assert_not_called()
                        power.assert_not_called()

    async def test_local_dashboard_controls_remain_available(self):
        for peer, host in (('127.0.0.1', '127.0.0.1:8000'),
                           ('127.0.0.1', 'localhost:8000'), ('::1', '[::1]:8000')):
            for mode in ('live', 'mock'):
                for action in ('stop-app', 'poweroff-pi'):
                    with self.subTest(peer=peer, mode=mode, action=action), \
                         patch.object(app, 'MODE', mode), \
                         patch.object(app, 'stop_app') as stop, \
                         patch.object(app, 'power_off_pi', return_value=True) as power:
                        self.assertEqual(await self.post(action, peer, host, f'http://{host}'), 200)
                        self.assertEqual(stop.call_count, int(mode == 'live' and action == 'stop-app'))
                        self.assertEqual(power.call_count, int(mode == 'live' and action == 'poweroff-pi'))

    async def test_unknown_action_and_poweroff_failure_keep_status_codes(self):
        self.assertEqual(await self.post('unknown'), 404)
        with patch.object(app, 'MODE', 'live'), patch.object(app, 'power_off_pi', return_value=False):
            self.assertEqual(await self.post('poweroff-pi'), 503)

    async def test_window_mode_rejects_untrusted_requests(self):
        scope = dict(local_request().scope)
        scope.update(method='POST', path='/api/window-mode/camp', client=('10.42.0.3', 1234))
        scope['headers'] = [(b'host', b'127.0.0.1:8000'), (b'origin', b'http://evil.example')]
        response = app.set_window_mode('camp', Request(scope))
        self.assertEqual(response.status_code, 403)


if __name__ == '__main__':
    unittest.main()
