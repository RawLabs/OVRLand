# Development checkpoint

OVRLand — Operational Vehicle Readout.
Location • Awareness • Navigation • Discovery.

## Implemented
- FastAPI service, shared JSON snapshot API and 5 Hz WebSocket delivery.
- Vanilla browser instrument frame targeting 1280×800, with a narrow-screen layout.
- Live mode by default; explicit mock mode for hardware-independent UI work.
- Independent Nano USB reader with bounded buffers, malformed-line rejection,
  disconnect retry, two-second freshness timeout, and source status.
- Live temperature, humidity, pressure, barometric altitude, raw RGB/proximity and
  IMU values in the API. Screen displays environmental readings, RGB and tilt.
- Complete joystick navigation across tabs, modules, expanded-module controls,
  footer controls, and explicit return paths.
- Drive and Adventure dashboards plus a System screen with guarded stop-app and
  Pi-poweroff actions.
- Persistent display-level attitude calibration, Nano BLE transport, offline
  raster MBTiles, and optional per-user kiosk startup.
- Independent gpsd telemetry and JSONL recording with GPS-only GPX export.
- Open-Meteo weather and optional Alberta 511 road-condition feeds.

- Browser radio with a curated station catalog and cached provider track metadata.
  The legacy player daemon and control API have been removed.
- Recorder I/O runs off the event loop; GPX export reads a fixed log prefix and
  writes points incrementally to a temporary file.

## Repair verification

The repair register, verification limits, and acceptance queue are in the
[pre-beta health check](pre-beta-health-check.md). The project is published at
[RawLabs/OVRLand](https://github.com/RawLabs/OVRLand). Automated validation passed
for published checkpoint `f0183cd` in
[GitHub Actions](https://github.com/RawLabs/OVRLand/actions/runs/36527242889).

The project remains pre-beta. Full browser acceptance and installed-Pi testing
remain open, including physical joystick/touch behavior, live sensor updates,
startup/recovery, long recording/export, and controlled power-cut durability.
Mock screenshots demonstrate the interface; they do not close these gates.

## Limits and next steps
1. Complete the browser and target-device acceptance tasks in the pre-beta health check.
2. Add gyro bias/fusion and magnetometer calibration; current pitch/roll remain
   gravity estimates, display-level zeroing is available, and heading remains unavailable.
3. Refine mode layouts in small steps, then add OBD through an adapter.
4. Decide recording retention separately; test recording power-cut durability on the target device.

OBD remains unavailable. GPS and recording are implemented. Online and offline map display is
implemented; no offline package is bundled. Live mode leaves missing values
unavailable. Barometric altitude is a firmware estimate, not a GPS fix. Light values
are raw sensor counts, not lux. Rear-screen entertainment, OS branding, navigation
portals, and standalone diagnostic logging remain future scope.

## Resume
Run and optional kiosk-install instructions are in ../README.md. The checked-in
per-user systemd/autostart templates can launch the service and Chromium at login.
Do not run multiple workers/readers against the same Nano.
Hardware is enabled by default. Use `OVRLAND_MODE=mock` for a simulated preview.
