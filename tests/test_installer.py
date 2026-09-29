import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class KioskInstallerTests(unittest.TestCase):
    def test_install_remove_and_application_menu_recovery_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / 'home with spaces'
            repo = Path(temporary) / 'repo with spaces'
            stub_bin = Path(temporary) / 'bin'
            home.mkdir()
            stub_bin.mkdir()
            (repo / 'scripts').mkdir(parents=True)
            (repo / 'deploy').mkdir()
            (repo / '.venv/bin').mkdir(parents=True)
            shutil.copy(ROOT / 'scripts/install_kiosk.sh', repo / 'scripts/install_kiosk.sh')
            for template in ('ovrland.service.in', 'ovrland-kiosk.desktop.in', 'ovrland.desktop.in'):
                shutil.copy(ROOT / 'deploy' / template, repo / 'deploy' / template)
            python = repo / '.venv/bin/python'
            python.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} "$@"\n')
            python.chmod(0o755)
            for command in ('wmctrl', 'chromium', 'systemctl'):
                stub = stub_bin / command
                stub.write_text('#!/bin/sh\nexit 0\n')
                stub.chmod(0o755)
            env = dict(os.environ, HOME=str(home), PATH=f'{stub_bin}:/usr/bin:/bin')
            script = repo / 'scripts/install_kiosk.sh'
            installed = subprocess.run(['/bin/sh', str(script), 'install'], env=env,
                                       capture_output=True, text=True, timeout=10)
            self.assertEqual(installed.returncode, 0, installed.stderr)
            application = home / '.local/share/applications/ovrland.desktop'
            service = home / '.config/systemd/user/ovrland.service'
            autostart = home / '.config/autostart/ovrland-kiosk.desktop'
            self.assertTrue(application.is_file())
            self.assertIn(f'{repo}/scripts/ovrland-launch.sh', application.read_text())
            self.assertIn(f'"{repo}/.venv/bin/python"', service.read_text())
            self.assertTrue(autostart.is_file())
            removed = subprocess.run(['/bin/sh', str(script), 'remove'], env=env,
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(removed.returncode, 0, removed.stderr)
            self.assertFalse(application.exists())
            self.assertFalse(service.exists())
            self.assertFalse(autostart.exists())

            missing_bin = Path(temporary) / 'missing-bin'
            missing_bin.mkdir()
            for command, target in (('dirname', '/usr/bin/dirname'), ('wmctrl', None)):
                stub = missing_bin / command
                stub.write_text(f'#!/bin/sh\nexec {target} "$@"\n' if target else '#!/bin/sh\nexit 0\n')
                stub.chmod(0o755)
            missing_env = dict(env, PATH=str(missing_bin))
            failed = subprocess.run(['/bin/sh', str(script), 'install'], env=missing_env,
                                    capture_output=True, text=True, timeout=10)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn('Missing Chromium', failed.stderr)
            self.assertFalse(service.exists())
            self.assertFalse(autostart.exists())
            self.assertFalse(application.exists())


if __name__ == '__main__':
    unittest.main()
