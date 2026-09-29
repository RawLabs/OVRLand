import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KioskLauncherTests(unittest.TestCase):
    def test_explicit_stop_request_closes_window_but_stale_request_does_not(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'repo'
            home = Path(temporary) / 'home'
            bin_dir = Path(temporary) / 'bin'
            for path in (root / 'scripts', root / '.venv/bin', home, bin_dir):
                path.mkdir(parents=True, exist_ok=True)
            shutil.copy(ROOT / 'scripts/ovrland-kiosk.sh', root / 'scripts/ovrland-kiosk.sh')
            python = root / '.venv/bin/python'
            python.write_text('#!/bin/sh\nexit 0\n')
            python.chmod(0o755)

            started = Path(temporary) / 'chromium-started'
            chromium = bin_dir / 'chromium'
            chromium.write_text(
                '#!/bin/sh\n'
                'touch "$OVRLAND_TEST_CHROMIUM_STARTED"\n'
                "trap 'exit 0' TERM INT\n"
                'while :; do sleep 0.05; done\n'
            )
            chromium.chmod(0o755)
            marker = home / '.local/state/ovrland/stop-requested'
            marker.parent.mkdir(parents=True)
            marker.touch()  # A stale marker must be consumed at launcher startup.
            env = dict(os.environ, HOME=str(home), PATH=f'{bin_dir}:/usr/bin:/bin',
                       OVRLAND_TEST_CHROMIUM_STARTED=str(started))

            launcher = subprocess.Popen(['/bin/sh', str(root / 'scripts/ovrland-kiosk.sh')], env=env)
            try:
                deadline = time.monotonic() + 5
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(started.exists(), 'launcher did not start Chromium')
                self.assertFalse(marker.exists(), 'launcher did not clear a stale stop request')
                self.assertIsNone(launcher.poll(), 'stale request closed the new browser window')

                marker.touch()
                self.assertEqual(launcher.wait(timeout=5), 0)
                self.assertFalse(marker.exists(), 'launcher did not consume the stop request')
            finally:
                if launcher.poll() is None:
                    launcher.terminate()
                    launcher.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
