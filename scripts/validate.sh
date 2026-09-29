#!/bin/sh
set -eu

python=.venv/bin/python
if [ ! -x "$python" ]; then
  python=python3
fi

"$python" -m compileall -q app.py adapters
"$python" -m pytest -q
node --check static/app.js
node --test tests/test_system_hold.cjs tests/test_radio_metadata.cjs
sh -n scripts/install_kiosk.sh scripts/ovrland-kiosk.sh scripts/ovrland-launch.sh
