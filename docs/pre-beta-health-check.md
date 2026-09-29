# Pre-beta health check — 2026-09-29

## Release assessment

The working tree contains the code changes for the reviewed repair register and
adds validation tooling, CI, and operational guidance. This is a **pre-beta
candidate, not a beta sign-off**: browser interaction on Chromium and acceptance
on the installed Pi have not been run in this environment. The checked-in tree
also has pre-existing local changes and has not been recorded as a clean
candidate commit. Keep release status open until the acceptance tasks below are
complete and the result is tied to a commit.

The register below is organized into 22 dispatchable tasks. R01–R09 retain the
original review identifiers in [the app review](app-review-2026-09-23.md). R10–R22
cover the implementation and pre-beta gates completed or identified during
this pass.

## Task register

| ID | Priority | Task / result | Status |
|---|---|---|---|
| R01 | P1 | Cancel interrupted System STOP/POWEROFF holds; bind a hold to the current session and require release before rearming. | Implemented; Node unit coverage added. Physical control acceptance open under R19. |
| R02 | P1 | Keep recording I/O and GPX export off the event loop; use bounded snapshots and streaming output. | Implemented; concurrency, bounded-memory, and response tests pass in the full validation run. |
| R03 | P1 | Separate permanent weather/511 shutdown from refresh wakeups; stop workers cleanly. | Implemented; adapter regression coverage present. |
| R04 | P1 | Keep feed coordinates and provenance tied to the successful observation; refresh after cumulative movement; configure fallback location naming. | Implemented; weather regression coverage present. |
| R05 | P1 | Clear or mark detail data stale on feed loss and prevent calibration from using stale Nano data. | Implemented; frontend contract checks present. Browser acceptance open under R18/R19. |
| R06 | P2 | Avoid rebuilding unchanged forecast cards on each telemetry frame while still updating live/stale labels. | Implemented with a data signature and DOM reuse. Browser interaction check open under R18. |
| R07 | P2 | Restore the OSM map and controls when an Earth popup is blocked. | Implemented; browser interaction check open under R18. |
| R08 | P2 | Align tests and project documentation with the current browser-radio, GPS, recording, and navigation behavior. | Implemented; docs and frontend checks updated. |
| R09 | P2 | Reject malformed BLE record shapes without escaping the notification error boundary. | Implemented; malformed-frame tests added. |
| R10 | P1 | Serialize GPS fix persistence and keep slow persistence outside the GPS state lock. | Implemented; GPS thread/race tests updated. |
| R11 | P1 | Bound BLE fragment assembly by packet count, bytes, and age; keep BLE telemetry from authorizing joystick control. | Implemented; framing and control-authority tests added. |
| R12 | P1 | Mark cached road reports stale immediately when the requested location changes, clear stale details on recovery, and use the last GPS fix consistently as feed fallback. | Implemented; adapter regression covers the pending-refresh interval. Browser feed-loss/recovery checks remain in R18/R19. |
| R13 | P1 | Protect recordings with a configurable 256 MiB free-space reserve, five-second sync interval, and clean-stop sync. | Implemented; low-space and sync tests present. Power-cut durability remains unverified under R19. |
| R14 | P1 | Recover incomplete/corrupt recording logs safely; bound row size in recovery and GPX export; serialize ZIP exports and release the export permit when the response closes. | Implemented; recovery, oversized-row, malformed-row, export and cleanup tests pass. |
| R15 | P1 | Restrict browser controls and WebSocket connections to loopback with validated Host and exact same-origin checks; add security response headers. | Implemented; hostile-origin/Host tests present. |
| R16 | P1 | Bound poweroff wait and move slow adapter shutdown off the server event loop; protect sampler and adapter cleanup; signal the kiosk to close on an intentional app stop. | Implemented; shutdown and launcher signal tests pass. Actual poweroff intentionally not exercised. |
| R17 | P2 | Make kiosk install/recovery predictable: validate prerequisites, render paths safely, install a recovery menu item, and keep Chromium open during transient health failures. | Implemented; installer tests cover paths with spaces and missing prerequisites. Pi install check remains part of R19. |
| R18 | P1 | Run browser smoke, viewport, navigation, stale-feed, popup, hold-cancel, and readability acceptance; repair any failures. | Tooling implemented in `scripts/check_live.py` and `scripts/readability_audit.py`; **not run** because Chromium is unavailable here. Assign to browser/Pi test owner. |
| R19 | P0 | Complete installed-device acceptance: screen and viewport, joystick/touch, Nano/GPS/BLE, configured feeds, long recording/export, reboot and power-cut recovery, and Pi responsiveness. | **Open.** No serial, GPIO, or gpsd device/socket is exposed in this environment. Requires the target Pi, display, peripherals, and representative storage. |
| R20 | P1 | Establish repeatable CI, run the full validation gate, audit the pinned Python dependencies, and record a clean candidate revision. | CI and `scripts/validate.sh` added. Full validation passes; `pip-audit` found no known vulnerabilities in `requirements.lock.txt` on 2026-09-29. **Partial:** create a clean candidate revision after reviewing the dirty tree. |
| R21 | P2 | Verify radio track-metadata error handling and ensure playback metadata failures do not leave stale track claims. | Implemented; Node regression test added. |
| R22 | P2 | Confirm installation, operator controls, recovery steps, and supported/deferred capabilities are described consistently for handoff. | README and controls guide updated; final Pi walkthrough is part of R19. |

## Verification evidence

- `rtk scripts/validate.sh` completed successfully outside the sandbox:
  **96 Python tests and 84 subtests passed**, all **14 Node tests passed**, and
  Python compilation, JavaScript syntax, and shell syntax checks passed. The
  sandbox stalls on asyncio thread-wakeup tests, so the complete gate was run
  outside it. GitHub Actions runs the same validation script on Ubuntu 24.04
  with Python 3.12 and Node 22.
- `pip-audit 2.10.1` checked the committed dependency lock at SHA-256
  `484414ea3e7239b35d2d76b567b459d77984d634f2444519b1cbd8bb2cbb82fd` and
  reported no known vulnerabilities. This is a point-in-time result for those
  locked dependencies, not a general security certification.
- Base revision inspected: `24922afdb7b49cf7e9fd4fabf1adb9eef4bacbe0`.
  The working tree is dirty and includes existing local edits as well as this
  repair pass; no commit or tag was created.
- Chromium/Chromium Browser, `/dev/serial/by-id`, `/dev/ttyACM0`,
  `/dev/gpiochip0`, and `/dev/gpsd.sock` are unavailable here. No browser,
  physical-control, real-provider, Pi-load, clean-reboot, or power-cut result is
  claimed.

## Assignment queue

1. **Browser test owner — R18:** run `rtk scripts/check_live.py` and
   `rtk scripts/readability_audit.py` on the Pi with Chromium. Exercise the
   manual cases in [the readability plan](readability-plan-2026-09-27.md),
   including interrupted holds, stale-feed recovery, calibration guards,
   forecast DOM reuse, and blocked popup recovery. Record browser version,
   viewport, result, and evidence; fix any reproducible failures.
2. **Hardware/operations owner — R19:** follow the checklist in
   [the app review](app-review-2026-09-23.md) and the device setup in
   [hardware notes](hardware.md). Test installed startup/recovery, real controls
   and sensors, weather/road configuration, long recording/export on target
   media, and clean reboot. Do a controlled power-cut/recovery test only on
   disposable test data and record what survives.
3. **Release owner — R20:** review the complete diff while preserving existing
   local changes, then produce a clean candidate revision and attach the
   validation and audit evidence. Keep the status at pre-beta until R18–R20 are
   closed.

## Decisions captured in code

- BLE stays telemetry-only for joystick authority.
- Recording keeps a 256 MiB free-space reserve and syncs at most five seconds
  apart, with a sync on clean stop.
- Weather movement refresh uses the configured coordinate threshold; display
  fallback naming comes from `OVRLAND_DEFAULT_LOCATION_NAME`.
- Existing unresolved scope remains explicit: OBD live data, route calculation,
  gyro/magnetometer fusion, and bundled offline map data are not part of this
  pre-beta repair set.
