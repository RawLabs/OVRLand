# Working scope — 2026-09-13

OVRLand: Operational Vehicle Readout. LAND: Location, Awareness, Navigation,
Discovery. Drive / Adventure / Camp are modes, not separate applications.
Vehicle and hardware profiles must remain replaceable; Tacoma/Nano are the first
installation, not platform assumptions. TruckBroPlay may become an optional theme.

The control foundation is discrete Nano joystick X/Y/click input with visible
focus, not pointer emulation. New screens must define their focus and return path
under the [control contract](controls.md) before implementation.

Current checkpoint: the instrument frame supports mock previews and a live Nano
bench test. Bold numerics, bearing area, attitude indicator, compact environment
strip, route placeholders, and physical-looking mode controls target 1280×800.
Drive and Adventure now have separate layouts based on the supplied logo/theme
references, ; System provides guarded application-stop
and Pi-poweroff controls. OpenStreetMap
is embedded with local Leaflet controls, Gaia opens in a browser tab, and raster
MBTiles packages can be served offline by the Pi (none installed yet). No recorder,
OS branding, or rear-display playback is implemented. No automatic rolling-log
policy has been decided.

Future: daily OBD instruments and diagnostics; adventure trip/segment recording;
Gaia/Garmin navigation interoperability after feasibility checks; local-first connectivity with optional Starlink;
camp computing and optional independent rear screen; standalone diagnostic logging.
Do not derive rollover safety thresholds from this visual mock.

## Reference set
Reviewed repository overview/README material; examples, not dependencies or forks.
- https://github.com/brian03079/piObdDashboard — separate Python collectors feeding
  browser telemetry, plus a mock OBD generator: preserve the data/UI separation.
- https://github.com/jbuehl/carputer — Tacoma logging and vehicle-computer reference;
  revisit when defining persistent capture and opportunistic upload.
- https://github.com/RobDeGeorge/OCTAVE — broader carputer application reference;
  revisit modular application boundaries, without adopting its Qt application stack.

No repositories cloned and no source copied. Check licenses and preserve attribution
if specific code is reused later. Current FastAPI WebSocket implementation follows
its documented API: https://fastapi.tiangolo.com/advanced/websockets/ .

## Confirmed local hardware context
Nano 33 BLE Sense Rev2 detected on the Pi at /dev/ttyACM0 with persistent path:
/dev/serial/by-id/usb-Arduino_Nano_33_BLE_6645321B7A5D0D0F-if00
38 valid JSON lines, zero invalid, measured 4.9 Hz in an eight-second check.
Firmware reports joystick and IMU/environment readings. Forward=X, right=Y, up=Z.
Persistent display-level calibration is implemented; gyro bias, fusion, and
magnetic calibration remain future work. Live mode opens serial through
the Nano adapter; mock mode does not.

## Live bench progress
Nano adapter implemented separately from API/UI. Live mode clears missing GPS/OBD;
mock mode remains available. Joystick left/right focuses modes and press selects.
Static accelerometer tilt is labeled uncalibrated; heading is withheld. Environmental
readings and raw light counts are exposed. Two-second stale timeout and reconnect.

The Pi uses wlan0 for its internet route. The secondary camera Wi-Fi connection has been removed from the application configuration and is available for other uses.

Protocol research reference: https://github.com/keowu/sjcam (AVIOCTRL client).
Only protocol facts were used in a temporary connectivity probe; no upstream
firmware or full client was copied, installed, or run. Compatibility remains partial.

Verification: the current Python suite covers Nano USB/BLE decoding and state,
offline maps, system endpoints, and frontend wiring; real HTTP/static resources and WebSocket
live Nano feed passed. Isolated Chromium render with an actual telemetry snapshot
passed 1280x800 fit, 390px phone width, mode buttons, and injected joystick selection.
Full browser navigation remained blocked by a headless Chromium stall, so isolated
render checks do not establish end-to-end browser networking. Physical test pending.
