#!/bin/sh
# Started by the desktop session. The server is managed separately by systemd.
set -eu

ovrland_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_url=http://127.0.0.1:8000/
health_url=http://127.0.0.1:8000/healthz
window_mode_url=http://127.0.0.1:8000/api/window-mode
chromium_profile="$HOME/.cache/ovrland/chromium"
stop_request_file="$HOME/.local/state/ovrland/stop-requested"
chromium_bin=$(command -v chromium || command -v chromium-browser || true)
if [ -z "$chromium_bin" ]; then
  echo "Chromium is required to open the OVRLand dashboard." >&2
  exit 1
fi

# Avoid opening Chromium's connection-error page while the service is starting.
attempt=0
ready=false
while [ "$attempt" -lt 60 ]; do
  if "$ovrland_root/.venv/bin/python" -c "
import sys
from urllib.request import urlopen
try:
    with urlopen('$health_url', timeout=1) as response:
        sys.exit(0 if response.status == 200 else 1)
except OSError:
    sys.exit(1)
"; then
    ready=true
    break
  fi
  attempt=$((attempt + 1))
  sleep 1
done

if [ "$ready" != true ]; then
  # Do not replace the desktop with Chromium's connection-error page when the
  # local service could not start.  The desktop remains usable for recovery.
  exit 1
fi

mkdir -p "$chromium_profile"
# A previous launcher may have been interrupted after a stop request. Starting
# the dashboard again consumes that old request rather than closing immediately.
rm -f "$stop_request_file"

window_mode=fullscreen
# Keep one decorated Chromium app window alive and let the window manager
# switch its EWMH fullscreen state. Restarting Chromium here disconnects radio
# streams and the dashboard's live recording session.
"$chromium_bin" --app="${app_url}?window=fullscreen&startup=1" \
  --start-fullscreen --user-data-dir="$chromium_profile" --no-first-run \
  --password-store=basic --no-default-browser-check \
  --disable-session-crashed-bubble \
  --autoplay-policy=no-user-gesture-required &
chromium_pid=$!

while kill -0 "$chromium_pid" 2>/dev/null; do
  if [ -e "$stop_request_file" ]; then
    rm -f "$stop_request_file"
    kill "$chromium_pid" 2>/dev/null || true
    wait "$chromium_pid" 2>/dev/null || true
    exit 0
  fi
  if ! "$ovrland_root/.venv/bin/python" -c "
import sys
from urllib.request import urlopen
try:
    with urlopen('$health_url', timeout=1) as response:
        sys.exit(0 if response.status == 200 else 1)
except OSError:
    sys.exit(1)
"; then
    # Keep the dashboard window alive through a service restart. Its WebSocket
    # reconnect loop recovers the view once health returns.
    sleep 1
    continue
  fi
  requested_mode=$("$ovrland_root/.venv/bin/python" -c "
from urllib.request import urlopen
try:
    with urlopen('$window_mode_url', timeout=1) as response:
        print(response.read().decode())
except OSError:
    pass
")
  if { [ "$requested_mode" = camp ] || [ "$requested_mode" = fullscreen ]; } && \
     [ "$requested_mode" != "$window_mode" ]; then
    if [ "$requested_mode" = fullscreen ]; then
      wmctrl -r 'OVRLand / Dashboards' -b add,fullscreen
    else
      wmctrl -r 'OVRLand / Dashboards' -b remove,fullscreen
      # Leave the desktop panel and recovery controls visible in Camp Mode.
      wmctrl -r 'OVRLand / Dashboards' -e 0,70,50,1100,680
    fi
    window_mode=$requested_mode
  fi
  sleep 1
done

wait "$chromium_pid"
