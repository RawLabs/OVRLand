#!/bin/sh
# Started by the desktop session. The server is managed separately by systemd.
set -eu

ovrland_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app_url=http://127.0.0.1:8000/
health_url=http://127.0.0.1:8000/api/telemetry
window_mode_url=http://127.0.0.1:8000/api/window-mode
chromium_profile="$HOME/.cache/ovrland/chromium"

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

window_mode=fullscreen
startup_launch=true
launch_chromium() {
  startup_parameter=
  if [ "$startup_launch" = true ]; then
    startup_parameter='&startup=1'
  fi
  if [ "$window_mode" = fullscreen ]; then
    chromium --kiosk --app="${app_url}?window=fullscreen${startup_parameter}" \
      --user-data-dir="$chromium_profile" --no-first-run \
      --password-store=basic \
      --no-default-browser-check --disable-session-crashed-bubble \
      --autoplay-policy=no-user-gesture-required &
  else
    # A normal decorated window leaves the panel and desktop reachable.  The
    # size fits the target 1280x800 display without covering its recovery UI.
    chromium --app="${app_url}?window=camp" --window-size=1100,680 \
      --window-position=70,50 --user-data-dir="$chromium_profile" \
      --no-first-run --password-store=basic --no-default-browser-check \
      --disable-session-crashed-bubble \
      --autoplay-policy=no-user-gesture-required &
  fi
  chromium_pid=$!
  startup_launch=false
}

# Keep Chromium tied to the service and relaunch it when the dashboard asks to
# move between true kiosk mode and the recoverable Camp Mode desktop window.
launch_chromium

while kill -0 "$chromium_pid" 2>/dev/null; do
  if ! "$ovrland_root/.venv/bin/python" -c "
import sys
from urllib.request import urlopen
try:
    with urlopen('$health_url', timeout=1) as response:
        sys.exit(0 if response.status == 200 else 1)
except OSError:
    sys.exit(1)
"; then
    kill "$chromium_pid" 2>/dev/null || true
    break
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
    kill "$chromium_pid" 2>/dev/null || true
    wait "$chromium_pid" 2>/dev/null || true
    window_mode=$requested_mode
    launch_chromium
  fi
  sleep 1
done

wait "$chromium_pid"
