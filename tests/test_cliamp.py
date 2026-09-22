import json
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from pathlib import Path

from adapters.cliamp import Cliamp


class CliampTests(unittest.TestCase):
    def test_finds_user_local_binary_when_service_path_omits_it(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / '.local' / 'bin' / 'cliamp'
            executable.parent.mkdir(parents=True)
            executable.touch()
            executable.chmod(0o755)
            with patch('adapters.cliamp.shutil.which', return_value=None), \
                 patch('adapters.cliamp.Path.home', return_value=Path(directory)):
                self.assertEqual(Cliamp().executable, str(executable))

    @patch('adapters.cliamp.socket.socket')
    def test_spectrum_reads_and_clamps_ten_real_bands(self, socket_factory):
        client = socket_factory.return_value.__enter__.return_value
        client.recv.side_effect = [json.dumps({'version': 2, 'ok': True, 'result': {'ok': True, 'bands': [-1, .1, .2, .3, .4, .5, .6, .7, .8, 2]}}).encode() + b'\n']
        result = Cliamp('/usr/bin/cliamp').spectrum()
        self.assertTrue(result['ok'])
        self.assertEqual(result['bands'][0], 0)
        self.assertEqual(result['bands'][-1], 1)
        client.sendall.assert_called_once_with(b'{"version":2,"id":"ovrland","method":"spectrum.get"}\n')

    @patch('adapters.cliamp.time.monotonic', side_effect=[0, 0, 1])
    @patch('adapters.cliamp.time.sleep')
    @patch('adapters.cliamp.subprocess.Popen')
    @patch.object(Cliamp, 'status')
    def test_start_owns_daemon_when_none_is_running(self, status, popen, _sleep, _monotonic):
        status.side_effect = [{'ok': False}, {'ok': True}]
        popen.return_value.poll.return_value = None
        with tempfile.TemporaryDirectory() as directory:
            player = Cliamp('/usr/bin/cliamp', config_home=directory)
            self.assertTrue(player.start())
            popen.assert_called_once_with(
                ['/usr/bin/cliamp', '--daemon'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True,
                env=popen.call_args.kwargs['env'])
            self.assertEqual(popen.call_args.kwargs['env']['XDG_CONFIG_HOME'],
                             str(player.config_home))

    @patch('adapters.cliamp.subprocess.Popen')
    def test_start_does_not_duplicate_its_owned_daemon(self, popen):
        player = Cliamp('/usr/bin/cliamp')
        popen.return_value.poll.return_value = None
        player.process = popen.return_value
        self.assertTrue(player.start())
        popen.assert_not_called()

    def test_stop_cleanly_terminates_only_owned_daemon(self):
        player = Cliamp('/usr/bin/cliamp')
        process = Mock()
        process.poll.return_value = None
        player.process = process
        player.stop()
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=3)
        self.assertIsNone(player.process)

    @patch('adapters.cliamp.subprocess.run')
    def test_status_uses_machine_readable_output(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = json.dumps({'ok': True, 'state': 'playing'})
        run.return_value.stderr = ''
        player = Cliamp('/usr/bin/cliamp')
        result = player.status()
        self.assertEqual(result['state'], 'playing')
        self.assertEqual(run.call_args.args[0], ['/usr/bin/cliamp', 'status', '--json'])
        self.assertEqual(run.call_args.kwargs['env']['XDG_CONFIG_HOME'],
                         str(player.config_home))

    @patch('adapters.cliamp.subprocess.run')
    def test_volume_adjustment_uses_fixed_json_arguments(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = '{"ok":true}'
        run.return_value.stderr = ''
        Cliamp('/usr/bin/cliamp').control('volume-up')
        command = run.call_args.args[0]
        self.assertEqual(command[-1], 'volume.adjust')
        self.assertEqual(json.loads(command[-2])['value'], 2)

    @patch.object(Cliamp, '_run')
    def test_remote_call_unwraps_completed_v2_job(self, run):
        run.return_value = {
            'ok': True,
            'job': {'state': 'succeeded', 'result': {'ok': True, 'repeat': 'all'}},
        }
        result = Cliamp('/usr/bin/cliamp').control('repeat')
        self.assertEqual(result['repeat'], 'all')
        self.assertEqual(run.call_args.args[-1], 'repeat')
        self.assertEqual(run.call_args.kwargs['timeout'], 20)

    def test_curated_catalog_has_requested_order_and_public_metadata(self):
        player = Cliamp('/usr/bin/cliamp')
        streams = player.streams()['streams']
        self.assertEqual(len(streams), 14)
        self.assertEqual([stream['display_name'] for stream in streams[:3]],
                         ['Open Road', 'Pacific Drive', 'Indie Road'])
        self.assertEqual(streams[-1]['display_name'], 'OVRLand After Dark')
        self.assertEqual(streams[8]['station_name'], 'Groove Salad')
        self.assertEqual(streams[8]['name'], 'Camp Chill')
        self.assertNotIn('primary_url', streams[0])
        self.assertNotIn('fallback_url', streams[0])
        expected_smoke_urls = {
            'open_road': 'http://radioparadise.com/m3u/aac-128.m3u',
            'pacific_drive': 'https://kexp.streamguys1.com/kexp160.aac',
            'camp_chill': 'https://somafm.com/groovesalad.pls',
            'backroads': 'https://somafm.com/bootliquor.pls',
            'trail_mode': 'https://somafm.com/secretagent.pls',
            'stargazing': 'https://somafm.com/deepspaceone.pls',
        }
        self.assertEqual({key: player._presets[key]['primary_url']
                          for key in expected_smoke_urls}, expected_smoke_urls)

    @patch.object(Cliamp, '_remote_call', return_value={'ok': True})
    def test_curated_stream_uses_cliamp_url_loader(self, remote_call):
        player = Cliamp('/usr/bin/cliamp')
        result = player.select_stream('camp_chill')
        self.assertTrue(result['ok'])
        self.assertFalse(result['fallback_used'])
        remote_call.assert_called_once_with('url.load', {
            'path': 'https://somafm.com/groovesalad.pls', 'play': True,
        })
        self.assertEqual(player.status()['preset']['display_name'], 'Camp Chill')

    @patch.object(Cliamp, '_remote_call')
    def test_curated_stream_tries_fallback_once(self, remote_call):
        remote_call.side_effect = [
            {'ok': False, 'error': 'playlist unavailable'},
            {'ok': True},
        ]
        result = Cliamp('/usr/bin/cliamp').select_stream('backroads')
        self.assertTrue(result['ok'])
        self.assertTrue(result['fallback_used'])
        self.assertEqual(remote_call.call_count, 2)
        self.assertEqual(remote_call.call_args_list[1].args, ('url.load', {
            'path': 'https://ice.somafm.com/bootliquor', 'play': True,
        }))

    @patch.object(Cliamp, '_remote_call', return_value={'ok': False, 'error': 'offline'})
    def test_unavailable_stream_fails_after_primary_and_fallback(self, remote_call):
        result = Cliamp('/usr/bin/cliamp').select_stream('trail_mode')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'stream_unavailable')
        self.assertEqual(remote_call.call_count, 2)
        self.assertIn('Check network connection', result['error'])

    @patch.object(Cliamp, '_remote_call')
    def test_invalid_stream_never_reaches_cliamp(self, remote_call):
        invalid = Cliamp('/usr/bin/cliamp').select_stream('not-curated')
        self.assertFalse(invalid['ok'])
        self.assertEqual(invalid['status'], 'invalid_stream')
        remote_call.assert_not_called()

    def test_only_allowlisted_actions_are_accepted(self):
        result = Cliamp('/usr/bin/cliamp').control('arbitrary-command')
        self.assertFalse(result['ok'])
        self.assertEqual(result['status'], 'invalid_action')


if __name__ == '__main__':
    unittest.main()
