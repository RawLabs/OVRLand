# Development checkpoint — 2026-09-23

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

Most reviewed issues have received code corrections. The
[repair handoff](app-review-2026-09-23.md) records current automated evidence,
original findings, and the manual acceptance checklist. The current full suite
passes 66 tests after legacy player cleanup; Python compilation and JavaScript
syntax checks pass. Browser UI acceptance, physical controls, Pi
performance, and recording power-loss durability remain unverified.

## Earlier bench evidence
- Real Nano stream: initial sample measured 4.9 Hz, with 38 valid JSON messages and
  no parse errors. API delivery frequency is separate from hardware sample rate.
- The Python suite passes coverage for sensor normalization, joystick state,
  USB fragmentation/disconnect, BLE packet decoding, offline maps, system endpoints,
  frontend wiring, and exclusion of mock GPS/OBD data from live mode.
- Running HTTP routes, static assets and WebSocket delivered live Nano data.
- Isolated Chromium rendering with an actual API snapshot passed 1280×800 fit,
  390-pixel phone width, mode buttons and injected joystick selection.

Full headless browser navigation stalled on this Pi. The isolated render check
bypasses browser networking; it is not a full end-to-end browser test. Physical
joystick feel, touch controls, and on-screen live updates still need user review.

## Limits and next steps
1. Complete the handoff browser checklist and bench-test controls and readings on the real screen.
2. Add gyro bias/fusion and magnetometer calibration; current pitch/roll remain
   gravity estimates, display-level zeroing is available, and heading remains unavailable.
3. Refine mode layouts in small steps, then add OBD through an adapter.
4. Implement agreed recording sync/low-space policies, decide retention, and test durability.

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

Checkpoint is local Git history; no remote publication is configured by this task.
