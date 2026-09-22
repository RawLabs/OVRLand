# OVRLand
Operational Vehicle Readout — Location • Awareness • Navigation • Discovery.

“Rally-game HUD meets real overland instrument panel.”

## Run
Python/FastAPI + WebSocket + vanilla HTML/CSS/JS. No frontend build; map controls
and theme assets are bundled locally. Online map tiles require internet.

The joystick control foundation is deliberately limited to **X, Y, and center
click**—not mouse emulation or keyboard shortcuts. See the [control contract](docs/controls.md)
before adding a screen or control path.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock.txt
# Live Nano bench test (default):
.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
# Or mock layout preview (no hardware opened):
OVRLAND_MODE=mock .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

Open http://127.0.0.1:8000 on the Pi. The service is deliberately loopback-only:
it is not exposed to passenger devices or the vehicle network. Stop-app and
Pi-poweroff controls require that direct loopback connection. Keep proxy headers
disabled and do not proxy these system endpoints: authorization relies on the
direct loopback peer. Until the optional kiosk setup below is installed, this is a
manually launched preview. Run one worker so only one adapter reads the serial
port. Close other serial monitors first.

## Remote maintenance

For maintenance from a laptop or development phone when the Pi display is
unavailable, use SSH port forwarding rather than binding the dashboard to the
Ethernet or Wi-Fi network:

```bash
ssh -N -L 8000:127.0.0.1:8000 ovrld@10.42.0.2
```

Open http://127.0.0.1:8000 on the maintenance device. The SSH connection carries
the dashboard traffic to the Pi's local-only service, so all dashboard controls,
including the guarded system controls, retain their normal behavior.

## Full-screen startup on the Pi

The dashboard can start automatically with the Pi's graphical session as a
dedicated Chromium kiosk window. It runs the service only on `127.0.0.1`, so the
startup display is local to the Pi. From the repository root, install it once:

```bash
bash scripts/install_kiosk.sh
```

The dedicated OVRLand Chromium profile uses Chromium's basic local password
store. This avoids an `Unlock Login Keyring` prompt blocking kiosk startup on
Pi desktop sessions that use automatic login. OVRLand does not store website
passwords in this profile.

Keep this Chromium profile dedicated to OVRLand. Gaia and Earth / Discovery are
intentional map windows opened by the dashboard; use a separate browser for
ordinary internet use on the Pi.

This installs a per-user systemd service and desktop autostart entry; it does not
need `sudo`. Reboot or log out and back in to verify the boot flow. `Alt+F4` closes
the kiosk window for parked maintenance; it is deliberately not auto-restarted by
the desktop launcher. The bottom-right **CAMP MODE** control relaunches OVRLand in
a smaller, decorated desktop window; the same control then reads **FULL SCREEN**
and returns to kiosk mode. Choosing **STOP APP** from the System screen also closes
the OVRLand window and returns to the desktop. The initial kiosk launch plays
`media/audio/voice/OVRLand-Start.wav` once. Moving between Camp Mode and full
screen does not replay the startup voice. Opening Camp Mode plays
`media/audio/voice/OVRLand-Fullscreen-Exit.wav` while a **WARNING — CO-PILOT USE
ONLY** overlay is visible; the overlay clears when the voice ends.

To remove the startup setup, run:

```bash
bash scripts/install_kiosk.sh remove
```

If a kiosk session ever prevents normal desktop use, press `Ctrl+Alt+F2`, sign
in at the text console, run the removal command above from the repository, then
run `sudo reboot`. This removes only OVRLand's per-user service and autostart
entry; it does not alter the Pi desktop configuration.

## Live bench test
- Nano temperature, humidity, pressure, barometric altitude estimate, raw RGB light,
  joystick, and accelerometer pitch/roll feed the common telemetry API.
- Tilt is an **uncalibrated static gravity estimate**, affected by acceleration.
  The Nano is mounted on its side; the adapter rotates its axes into vehicle
  coordinates (forward=Z, right=X, up=-Y). Positive pitch means nose up; positive
  roll means right side up. The Tilt-Oh-Shit meter shows an amber visual caution
  at 20° and a red visual alarm at 30° of displayed pitch or roll. These are
  driver-reference bands only, not validated rollover limits, and there is no
  vehicle control output, fused yaw, or heading.
  The Vehicle Attitude detail can save the current position as a persistent
  display-level offset; the raw accelerometer telemetry remains unchanged.
- Barometric altitude comes from firmware and its pressure reference; it is not GPS
  altitude. APDS RGB counts are raw values, not lux or a daylight classification.
- In **System**, use **Capture Day**, **Capture Dusk**, and **Capture Night** while
  the sensor is exposed to the actual vehicle lighting. Each tap records raw RGB
  counts and relative brightness in `config/ambient_light_calibration.json`; the
  saved references are for setting vehicle-specific night thresholds later and do
  not yet alter the display theme or brightness.
- Joystick left/right moves the white focus outline across Drive, Adventure, and
  System while the tab layer is active. Press activates the highlighted tab. Down
  enters the tab's upper module row, then its lower row, then Camp Mode; Up follows
  that same path in reverse. Left/right stays within the current module row, and
  press opens the focused module detail. Every expanded module has a visible `BACK
  TO DASHBOARD` action; press it to return. Expanded Map uses its own left/right
  control row for its source options and Back. Return to center between moves.
  X/Y and button state are visible below the panes.
  Mode selections are local to each visible browser; only the front display should
  use this bench control path. A separate rear-display role remains future work.
- The System tab has separate hold-for-two-seconds controls to stop OVRLand or
  power off the Pi. Mock mode simulates both actions without changing the host.
- OVRLand starts and owns a private headless CLIAMP instance with the app, using a
  persistent OVRLand-only profile at `~/.local/state/ovrland` by default (override
  with `OVRLAND_CLIAMP_CONFIG_HOME`). It terminates that process during application
  shutdown. The Music screen
  reads its now-playing state and exposes a small static set of OVRLand radio
  presets, transport, volume, shuffle, repeat, and stop through joystick detail
  rows. CLIAMP resolves M3U/PLS presets; each station has at most one automatic
  fallback attempt. Presets live in `config/radio_presets.json` so SomaFM entries
  can be removed or replaced without coupling the Music architecture to SomaFM.
  Spotify remains a separate optional portal; local music/video remains deferred.
- Invalid JSON is dropped. After two seconds without valid Nano data, values clear.
  Unplug/replug is retried. Joystick requires neutral/release after reconnect; old
  control events are not replayed on browser connection. No serial commands sent.
- GPS connects to a system-owned gpsd on `127.0.0.1:2947`, reconnects after
  disconnects, and remains unavailable rather than substituting demo values when
  gpsd or a valid fix is absent. OBD remains unavailable in live mode.
- Internet status checks a short TCP connection to `1.1.1.1:443` every 15 seconds
  and reports `CONNECTED` or `UNAVAILABLE` in the source strip. Override the
  check target with `OVRLAND_NETWORK_CHECK_HOST` and
  `OVRLAND_NETWORK_CHECK_PORT` when the vehicle network requires another route.
- Air Lift WirelessAir has an opt-in, read-only BLE adapter and rear suspension
  card with left/right PSI. Set `OVRLAND_AIRLIFT_ENABLED=1` to connect; the unknown
  status UUID stays unmapped until verified. See [Air Lift discovery and truck
  testing](docs/airlift.md) for raw logs and exact ATT handle mapping. No pressure
  adjustment commands are implemented.
- Recording remains disabled. Map controls support online OSM and installed offline
  packages; no trip or telemetry history is stored.

Override `OVRLAND_NANO_DEVICE` to choose another serial device. Default:
`/dev/serial/by-id/usb-Arduino_Nano_33_BLE_6645321B7A5D0D0F-if00`.

## Pi GPS setup and smoke test

Install and enable gpsd on Raspberry Pi OS, configuring it for the stable
`/dev/serial/by-id/...` receiver path when one is available:

```bash
sudo apt update
sudo apt install gpsd gpsd-clients
gpspipe -w -n 20
```

OVRLand is a gpsd client and does not open the receiver or launch/terminate gpsd.
It consumes TPV and SKY reports, requires `mode >= 2` plus latitude/longitude,
and exposes satellite counts and approximate accuracy in the telemetry `gps`
metadata. The dashboard and Center GPS map control update when a valid fix arrives.

For direct serial troubleshooting while gpsd is stopped, the older read-only NMEA
checker remains available:

```bash
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/check_gps.py --seconds 30
```

It checks `/dev/serial/by-id/*`, `/dev/ttyUSB*`, and `/dev/ttyACM*`, validates NMEA
checksums, and reports latitude, longitude, fix quality, satellites, altitude,
speed, and heading. A fix normally requires a view of the sky; indoors it may
report valid NMEA sentences but zero position fixes. If permission is denied, add
the Pi user to the serial-device group (`sudo usermod -aG dialout "$USER"`) and
log in again. The checker does not start or change the dashboard and sends no
serial commands.

## Boundaries and contract
`adapters/nano.py` owns serial IO and normalization; `app.py` owns the common
snapshot and API; the browser never opens hardware. Future sources get independent
adapters. `GET /api/telemetry` and `/ws/telemetry` share schema version 1, with units
in field names. The socket sends snapshots at 5 Hz; that is not a claim about sensor
sampling rate. Source status and Nano sample age/receive timestamp identify freshness.
Only the latest sample and a bounded 20-event joystick history are kept in memory.
In mock mode, `static/mock.json` supplies stable, explicitly simulated readings.

## Verification
```bash
.venv/bin/python -m unittest discover -s tests -v
```
Tests cover normalization, failed sensors, serial fragmentation/malformed input,
disconnects, stale data, joystick edge handling, BLE packet decoding, offline maps,
system controls, frontend element wiring, and avoiding mock GPS/OBD in live mode.
Real HTTP and WebSocket checks verified live Nano updates. Full headless browser
navigation has stalled on this Pi; isolated browser rendering verifies the UI using
an actual API snapshot. Physical touch and joystick feel still need user testing.

Next: verify the physical controls, connect GPS through its own adapter, then refine the vehicle integrations separately. Dedicated mode layouts and persistent
display-level calibration are implemented; gyro and magnetometer calibration remain future work.
See [scope and references](docs/scope.md), [checkpoint status](docs/status.md),
and [hardware setup](docs/hardware.md).

## Dashboards and maps
Drive and Adventure are separate dashboards styled from the supplied OVRLand
logo/theme references. Drive uses round performance gauges; Adventure emphasizes
the map, field conditions, and larger orientation instruments. System provides guarded stop-app and Pi-poweroff controls. Unknown readings remain blank.

The map source buttons select **OpenStreetMap**, **Gaia**, **Earth / Discovery**,
or **Offline**. OSM is
an interactive online map; Center GPS uses telemetry when coordinates are valid.
The initial browse view follows the region in the supplied Gaia link; it is not a
claimed vehicle location. Gaia opens that link in its own browser tab for sign-in.
Earth / Discovery opens the free Google Earth web app in a touch-capable Chromium
popup sized to cover the dashboard map panel; it needs internet and is not embedded
or billed through Google Maps Platform. Gaia's mobile offline downloads do not make
its website work offline.

Offline uses a raster MBTiles package stored on the Pi. No package is installed
by default. See [offline map setup](maps/README.md). Leaflet 1.9.4 is bundled locally
(with its license and official JS/CSS checksums verified), so offline map controls
do not require a CDN. OSM tiles are not prefetched or bulk-downloaded. No route
calculation is implemented by these map controls.
