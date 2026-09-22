"""Small, bounded adapter for CLIAMP's local command interface."""
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class Cliamp:
    ACTIONS = {'toggle', 'next', 'prev', 'stop'}

    PRESETS_FILE = Path(__file__).resolve().parents[1] / 'config' / 'radio_presets.json'

    def __init__(self, executable=None, timeout=4, startup_timeout=30, presets=None,
                 config_home=None):
        self.executable = executable or self._find_executable()
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.process = None
        loaded_presets = presets if presets is not None else json.loads(self.PRESETS_FILE.read_text())
        self._presets = {preset['id']: dict(preset) for preset in loaded_presets}
        self._preset_lock = threading.Lock()
        self._active_preset_id = None
        if config_home is None:
            configured_home = os.environ.get('OVRLAND_CLIAMP_CONFIG_HOME')
            config_home = (Path(configured_home) if configured_home
                           else Path.home() / '.local' / 'state' / 'ovrland')
        self.config_home = Path(config_home)
        self.socket_path = self.config_home / 'cliamp' / 'cliamp.sock'
        self.last_error = None

    @staticmethod
    def _find_executable():
        """Find a normal shell install as well as the user-service-safe path."""
        executable = shutil.which('cliamp')
        if executable:
            return executable
        candidate = Path.home() / '.local' / 'bin' / 'cliamp'
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
        return None

    def start(self):
        """Start the private OVRLand daemon and wait for its IPC socket."""
        if not self.executable:
            self.last_error = 'CLIAMP is not installed'
            return False
        if self.process is not None and self.process.poll() is None:
            return True
        try:
            self.config_home.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            self.last_error = f'Unable to create CLIAMP config directory: {error}'
            return False
        self.last_error = None
        try:
            self.process = subprocess.Popen(
                [self.executable, '--daemon'], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True, close_fds=True, env=self._command_env(),
            )
        except OSError:
            self.process = None
            self.last_error = 'Unable to start CLIAMP'
            return False
        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.last_error = 'CLIAMP exited before its player daemon became ready'
                return False
            status = self.status()
            if status.get('ok'):
                return True
            self.last_error = status.get('error') or 'Waiting for CLIAMP player daemon'
            time.sleep(.25)
        self.last_error = 'CLIAMP took too long to initialize its player daemon'
        self.stop()
        return False

    def stop(self):
        """Stop only the daemon process created by this adapter."""
        if self.process is None:
            return
        if self.process.poll() is not None:
            self.process = None
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=1)
        finally:
            self.process = None

    def _command_env(self):
        env = os.environ.copy()
        env['XDG_CONFIG_HOME'] = str(self.config_home)
        return env

    def _run(self, *args, timeout=None):
        if not self.executable:
            return {'ok': False, 'status': 'not_installed', 'error': 'CLIAMP is not installed'}
        try:
            result = subprocess.run(
                [self.executable, *args], capture_output=True, text=True,
                timeout=self.timeout if timeout is None else timeout, check=False,
                env=self._command_env(),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return {'ok': False, 'status': 'unavailable', 'error': str(error)}
        output = result.stdout.strip()
        if result.returncode:
            message = result.stderr.strip() or output or 'CLIAMP command failed'
            status = 'not_configured' if 'unknown provider "spotify"' in message.lower() else 'not_running'
            return {'ok': False, 'status': status, 'error': message}
        if not output:
            return {'ok': True}
        try:
            return json.loads(output)
        except json.JSONDecodeError:
            return {'ok': False, 'status': 'invalid_response', 'error': 'CLIAMP returned invalid JSON'}

    def status(self):
        result = self._run('status', '--json')
        result.setdefault('status', 'ready' if result.get('ok') else 'unavailable')
        if not result.get('ok') and self.last_error and not result.get('error'):
            result['error'] = self.last_error
        with self._preset_lock:
            preset = self._presets.get(self._active_preset_id)
        if preset:
            result['preset'] = self._public_preset(preset)
        return result

    def spectrum(self):
        """Read CLIAMP's real normalized 10-band analyzer frame."""
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(str(self.socket_path))
                client.sendall(b'{"version":2,"id":"ovrland","method":"spectrum.get"}\n')
                payload = b''
                while b'\n' not in payload and len(payload) < 65536:
                    chunk = client.recv(4096)
                    if not chunk:
                        break
                    payload += chunk
            envelope = json.loads(payload.split(b'\n', 1)[0])
            result = envelope.get('result', {})
        except (OSError, ValueError, json.JSONDecodeError) as error:
            return {'ok': False, 'status': 'unavailable', 'error': str(error)}
        bands = result.get('bands')
        if not result.get('ok') or not isinstance(bands, list) or len(bands) != 10:
            return {'ok': False, 'status': 'invalid_response', 'error': 'Invalid spectrum frame'}
        try:
            result['bands'] = [min(1, max(0, float(value))) for value in bands]
        except (TypeError, ValueError):
            return {'ok': False, 'status': 'invalid_response', 'error': 'Invalid spectrum bands'}
        return result

    def control(self, action):
        if action in self.ACTIONS:
            return self._run(action)
        if action in {'volume-down', 'volume-up'}:
            amount = -2 if action == 'volume-down' else 2
            return self._remote_call('volume.adjust', {'value': amount})
        if action in {'shuffle', 'repeat'}:
            return self._remote_call(action)
        return {'ok': False, 'status': 'invalid_action', 'error': 'Unsupported music action'}

    def _remote_call(self, operation, params=None):
        """Run one V2 operation and return its completed operation result."""
        envelope = self._run('remote', 'call', '--wait', '--params',
                             json.dumps(params or {}), operation,
                             timeout=max(self.timeout, 20))
        if not envelope.get('ok'):
            return envelope
        job = envelope.get('job')
        if not isinstance(job, dict):
            return envelope
        if job.get('state') != 'succeeded':
            state = job.get('state', 'did not complete')
            return {'ok': False, 'status': 'operation_failed',
                    'error': f'CLIAMP operation {state}'}
        result = job.get('result', {'ok': True})
        if isinstance(result, str):
            try:
                result = json.loads(result)
            except json.JSONDecodeError:
                return {'ok': False, 'status': 'invalid_response',
                        'error': 'CLIAMP returned an invalid operation result'}
        if not isinstance(result, dict):
            return {'ok': False, 'status': 'invalid_response',
                    'error': 'CLIAMP returned an invalid operation result'}
        result.setdefault('ok', True)
        return result

    @staticmethod
    def _public_preset(preset):
        """Return presentation metadata without exposing playback URLs."""
        public = {key: value for key, value in preset.items()
                  if key not in {'primary_url', 'fallback_url', 'low_bandwidth_url'}}
        # Keep already-open kiosk pages compatible with the previous catalog
        # response until Chromium next reloads the updated frontend.
        public['name'] = preset['display_name']
        public['favorite'] = False
        return public

    def streams(self):
        """Return the small built-in OVRLand radio list in curated order."""
        return {'ok': True, 'streams': [self._public_preset(preset)
                                       for preset in self._presets.values()]}

    def select_stream(self, stream_id):
        """Tune an allowlisted preset, trying its fallback at most once."""
        preset = self._presets.get(stream_id)
        if preset is None:
            return {'ok': False, 'status': 'invalid_stream',
                    'error': 'Select a station from the curated OVRLand list'}
        urls = [preset['primary_url']]
        fallback = preset.get('fallback_url')
        if fallback and fallback != urls[0]:
            urls.append(fallback)
        last_error = None
        for index, url in enumerate(urls):
            result = self._remote_call('url.load', {'path': url, 'play': True})
            if result.get('ok'):
                with self._preset_lock:
                    self._active_preset_id = stream_id
                return {
                    'ok': True,
                    'stream': self._public_preset(preset),
                    'fallback_used': index > 0,
                }
            last_error = result.get('error')
        return {
            'ok': False,
            'status': 'stream_unavailable',
            'error': 'STREAM UNAVAILABLE — Check network connection.',
            'detail': last_error,
        }
