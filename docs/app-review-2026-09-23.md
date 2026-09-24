# App review and repair handoff — 2026-09-23

Most reviewed issues have received code corrections. R2's remaining recorder/export
work and the legacy player cleanup are complete. Manual browser and hardware
acceptance testing is still required before closing the review. This handoff is
not a hardware certification or a claim of power-loss durability.

## Current repair status

- Repair changes for R1–R9 are recorded below; full acceptance of every item has
  not been established. The original findings are retained as historical context
  and as acceptance criteria, rather than a list of wholly untouched defects.
- R2 has automated regression coverage for concurrent recording/export,
  responsiveness, malformed logs, and export memory growth.
- The legacy player adapter and API have been removed; the station catalog,
  browser playback, and track metadata lookup remain.
- JavaScript syntax checks pass for `static/app.js`, `static/maps.js`, and
  `static/navball.js`.
- The current full unit suite passes: **66 tests after legacy player cleanup**.
  The earlier 83-test result included 17 tests for the removed player adapter.
  Python compilation and `git diff --check` also pass.
- The attempted browser verification passed mock HTTP/WebSocket checks but
  stalled on stylesheet loading and CDP communication before the requested UI
  acceptance checks could run. Those checks remain unverified.

## Manual acceptance still required

Record the date, environment, result, and any observed failure for each check.
Use mock mode or stub system actions when checking interrupted holds.

- [ ] **Interrupted holds:** start a system-action hold, interrupt telemetry,
  hide the tab, or change the Nano session; returning with the button pressed
  must not complete the old action. Release and a fresh uninterrupted hold
  should produce exactly one simulated action.
- [ ] **Feed-loss displays:** open GPS, weather, and road details, disconnect
  telemetry, and confirm values are cleared or explicitly stale, with no
  remaining LIVE/FIX LIVE claims. Reconnect and confirm recovery.
- [ ] **Calibration guards:** attempt SET LEVEL after disconnect and with Nano
  data unavailable; the stored calibration must not change. Fresh live Nano
  telemetry should permit calibration again.
- [ ] **Forecast reuse:** use browser developer tools with controlled telemetry
  to confirm identical forecasts retain their DOM nodes, changed forecasts
  update once, and stale/live labels still change.
- [ ] **Blocked Earth popup:** block the popup from both OSM and Offline;
  confirm OSM tiles, panels, link, and Center GPS controls are restored and
  Earth can be retried.
- [ ] **Physical controls and feeds:** exercise joystick release/reconnect,
  touch controls, Nano/GPS/BLE data, and configured weather/road providers on
  the installed display.
- [ ] **Pi recording performance:** record and export a representative long
  trip on the actual storage while checking telemetry cadence, health requests,
  UI responsiveness, and long-duration stability.

## Remaining recording work

Periodic `fsync`, low-space refusal/stop, and retention remain design and
implementation follow-ups. Disk-full/close-error recovery and power-loss
persistence need testing after the intended policy is implemented. These are
not resolved merely by completing manual UI checks.

## Original review evidence and limits

- Ran `.venv/bin/python -m unittest discover -s tests -v`: **72 tests, 69 passed, 3 failures, no errors**. A second run with concise failure reporting confirmed the same results.
- Isolated, network-free reproductions confirmed feed shutdown failure, premature location relabeling, missing cumulative movement refresh, recorder lock contention, and a BLE non-object parsing exception.
- Reviewed backend routes/adapters, frontend rendering/navigation/maps, kiosk launcher, tests, and scope/status documents.
- No physical Nano/GPS/BLE testing, live provider requests, browser end-to-end run, Pi frame-rate measurement, long-duration recording soak, or power-cut test was performed. Performance findings below identify actual work/blocking paths; they are not measured Pi FPS claims.
- Locations below refer to this working tree. Find the named function if subsequent edits move a line.

## Original findings and acceptance criteria

The original priority was R1–R3, then R4–R8, followed by cleanup and robustness
work. Refer to the current status above and the repair-pass records below when
using these findings; their descriptions document the pre-repair behavior.

### R1 — High: an interrupted joystick hold can still execute a system action

**Locations:** `static/app.js:453` (`joystick`), `static/app.js:1156` (`stale`), final `visibilitychange` handler.

**Trigger:** start holding STOP APP or POWEROFF, interrupt telemetry/Nano connectivity or hide the browser, then resume with the button pressed after two seconds. The unavailable/hidden branch resets only `joySession`. The pending `systemHoldAction` and start time survive. Hold completion is checked before the new-session check, so the first resumed pressed sample can execute the old action without a new continuous hold.

**Repair:** introduce one `cancelSystemHold()` helper. Call it on feed loss, missing/non-live joystick data, session changes, visibility changes, and navigation away from the system action. Validate the session before evaluating hold completion. Require release and a new select event after interruptions.

**Acceptance:** use synthetic telemetry and stub `runSystemAction`; press, disconnect for over two seconds, reconnect pressed: zero calls. Release and start a fresh uninterrupted two-second hold: exactly one call. Repeat for hidden-tab and Nano-session changes.

### R2 — High: GPX export and recording writes can block the API event loop

**Locations:** `app.py:192` (`recording_sampler`); `adapters/recording.py:61`–69 and `:137` (`gps_track`).

**Evidence:** GPX parsing holds the recorder's shared lock over the entire file. The async sampler synchronously calls `is_recording()` and `append()`, both taking that lock. Although the export endpoint runs in a worker thread, the sampler blocks the event loop waiting for it. An isolated test with two artificially slowed JSON reads blocked `is_recording()` for 0.301 seconds. Larger files or slow storage extend this directly. Every append also performs synchronous disk write/flush on the event loop. GPX builds its complete XML tree in memory, so memory rises with track length.

**Impact:** interrupted 5 Hz telemetry, stalled HTTP requests and delayed controls. The kiosk health poll has a one-second timeout and can close the browser during the stall.

**Repair:** move recorder I/O to a dedicated worker or awaited thread operation; keep any queue bounded and expose write failures. Under a short lock, flush and capture the export file/byte boundary; parse that immutable prefix outside the recorder lock. Stream GPX output or create a temporary export file incrementally instead of retaining all points in memory. Preserve malformed-tail handling and GPS-only filtering.

**Acceptance:** while exporting a representative multi-hour log with an injected slow reader, keep recording and run an event-loop heartbeat. Assert telemetry continues near its 200 ms cadence and health requests stay below the launcher's timeout. Test concurrent stop/export and malformed final JSONL lines. Measure export memory as file size increases.

### R3 — High: weather and road workers consume their own shutdown signal

**Locations:** `adapters/weather.py:160`–182; `adapters/alberta_511.py:150`–168; both `set_location`/`stop` methods.

**Evidence:** one event serves both shutdown and refresh. Each worker waits, then unconditionally clears it. Calling `stop()` while it is waiting wakes another fetch instead of ending the worker. Stubbed-fetch reproductions showed both threads alive after `stop()` returned. There is also a timing window where a refresh signal at the loop condition ends the worker entirely.

**Repair:** separate permanent stop state from refresh wakeup. `stop()` sets stop and wakes the wait; the worker checks stop before fetching again. Never clear stop inside the loop. Account for the 8/10-second network timeout in shutdown behavior, and make start/stop idempotent.

**Acceptance:** stop while waiting and while fetch is blocked; release the fake fetch and verify termination with no further request. Location changes should refresh without terminating the worker. Repeat start/stop without leaked threads.

### R4 — Medium: feed location provenance and movement refresh are incorrect

**Locations:** `adapters/weather.py:40`–51, `:170`–175; `adapters/alberta_511.py:65`–76, `:160`–165.

**Evidence:** `set_location()` immediately changes the cached result's `location_source`, before fetching conditions for that location. A reproduced cached result retained coordinates `(51, -114)` while changing to `location_source='gps'`. Failed fetches also relabel retained data. Separately, movement is compared with the immediately preceding GPS update, not the location of the last fetch. One hundred 0.001-degree updates, totaling 0.1 degree, never signaled refresh. The periodic refresh still runs, but the intended movement threshold does not work during normal incremental driving.

**Repair:** separate requested location from published observation location. Compare movement against last requested/fetched coordinates. Publish provenance, coordinates, values, and observation time atomically on successful fetch. Keep old provenance on failure and mark stale/pending when location changes. Discard or clearly label results from superseded requests. Replace hardcoded `CALGARY DEFAULT` frontend labels with configured fallback coordinates or a configured name.

**Acceptance:** default → distant GPS → failed fetch must never label default values as GPS observations. Gradual movement crossing the threshold causes refresh. Configured non-Calgary fallback is labeled accurately.

### R5 — Medium: feed-loss cleanup leaves live-looking detail data and usable old calibration

**Locations:** `static/app.js:1156` (`stale`), `:637` (`applyCurrentCalibration`), `:998` (`renderWeatherDetail`), `renderGpsDetail`.

**Problem:** feed loss clears `[data-value]` and some instruments, but not GPS-detail fields, weather/road fields, their LIVE labels, or `window.latestTelemetry`. Calibration reads that retained object and can save a stale attitude reference. The general connection banner changes, but detailed values still claim live status.

**Repair:** invalidate the latest actionable telemetry on disconnect; clear or explicitly mark every detail panel stale. Check freshness and live Nano status inside calibration execution, not only when building buttons. Update calibration controls when availability changes.

**Acceptance:** open each detail panel, disconnect telemetry, and verify no LIVE/FIX LIVE label remains. Attempt SET LEVEL after disconnect: no local-storage write. Reconnect restores values and permits a fresh calibration.

### R6 — Medium: weather forecasts are rebuilt five times per second

**Locations:** `static/app.js:998`–1054; unconditional call at `:1062`.

**Problem:** every telemetry frame clears and recreates both dashboards' daily and hourly forecast cards, including hidden details. With two daily and twelve hourly cards per dashboard, this is 140 cards and roughly 860 elements created per second, even though weather normally changes every 15 minutes. This causes unnecessary allocation/DOM work on the Pi and can disturb interaction with forecast content.

**Repair:** cache a weather revision/value signature and render forecast cards only when their data changes. Update availability/provenance labels separately so stale transitions are not suppressed by an unchanged `updated_at`. Cache stable DOM references where useful. Keep joystick and sensor updates at the existing cadence.

**Acceptance:** feed 100 identical weather payloads within changing sensor snapshots. Forecast node identities stay unchanged; one changed forecast updates once; stale/live transitions still update labels. Profile on the Pi before claiming a frame-rate improvement.

### R7 — Medium: blocked Earth popup leaves a blank map marked OpenStreetMap

**Locations:** `static/maps.js:55`–70 (`openEarth`), `:82`–116 (`choose`).

**Trigger:** block popups and select Earth. `choose('earth')` removes the OSM/offline layer. On `window.open()` failure, `openEarth()` only changes `source`, button state, and status. It never restores OSM tiles or the other map controls.

**Repair:** use the complete `choose('osm')` transition on failure, then show the blocked-popup message. Verify this path does not recurse into Earth opening.

**Acceptance:** stub `window.open` to return null from both OSM and Offline. Confirm OSM layer is attached, panels/link/center controls match OSM, and retry remains available.

### R8 — Medium: tests and project status describe the previous application

**Locations:** `tests/test_frontend_contract.py:70`, `:90`–107, `:141`–154; `scripts/check_live.py` navigation expectations; `docs/scope.md`; `docs/status.md`; README final next-steps paragraph.

**Observed failures:** old music shuffle/repeat/API expectations, previous dashboard module order, and old meter naming. Docs say GPS/recording are unconnected, while both are implemented. These are maintenance defects; missing shuffle for a live radio stream is not itself a product defect.

**Repair:** align assertions and smoke-check module order with the current control contract and browser-radio design. Replace brittle source-string assertions with behavioral navigation/control tests where practical. Update docs to separate implemented GPS/recording from deferred OBD, route calculation, and rear-display support. Add deterministic tests for the currently uncovered recording, weather, 511, and metadata adapters, starting with R1–R7 regressions.

**Acceptance:** all 72 existing tests pass with reviewed expectations; add the targeted regression tests above. No checks are simply removed to obtain green output. README, scope, and status agree about current capabilities.

### R9 — Low: BLE malformed JSON objects escape validation

**Locations:** `adapters/nano_ble.py:61`–66 (`expand_record`), `_notification` exception handler.

**Evidence:** `expand_record([])` raises `AttributeError` because `.get()` is called before the dictionary check. Valid JSON values such as arrays/null therefore escape the intended invalid-packet handling; callback errors do not increment the invalid counter. This does not by itself establish a permanent BLE disconnection.

**Repair:** validate dictionary type before any `.get()` access and raise `ValueError` for unsupported shapes. Keep a deliberate notification exception boundary.

**Acceptance:** array, null, number, string, malformed compact object, then a valid packet: invalid counter increases appropriately and valid telemetry is accepted afterward.

## Old code and planned stubs

**Legacy player cleanup completed:** the daemon adapter and unused status, spectrum, stream-selection, and player-control endpoints were removed. Browser radio uses a pure catalog adapter for `/api/music/streams` and the existing cached provider lookup for `/api/music/now-playing/{stream_id}`. Station metadata and direct browser playback URLs remain in `config/radio_presets.json`.

**Explicitly deferred, not defects:** OBD live readings, route calculation/navigation interoperability, local media/rear display, gyro/magnetometer fusion, and automatic ambient-light theme selection. Offline MBTiles absence and 511 `KEY REQUIRED` are configuration states. Do not fill these with fabricated readings or implement them as incidental cleanup.

**Recording durability decisions still needed:** JSONL `flush()` does not provide a bounded power-loss persistence guarantee; no `fsync` policy is implemented. Logs have no size/free-space guard, and retention is explicitly undecided. Add configurable low-space refusal/stop and visible errors without silently deleting recordings. Choose a documented periodic sync interval off the event loop; test injected disk-full/close errors, recovery from a partial tail, and graceful shutdown. Treat retention/deletion as a separate product decision. At 5 Hz, daily storage is average encoded row bytes × 432,000; measure real full-forecast payloads before setting capacity expectations.

## Instructions for the repair agent

1. Read repository instructions and preserve all pre-existing working-tree changes. Work on one numbered repair at a time.
2. Add its smallest meaningful failing regression, implement the bounded change, and run that test plus related suites.
3. Keep hardware/provider access mocked in automated regression tests. Do not trigger poweroff, start an actual player, or alter kiosk installation while testing.
4. Run the full unittest suite after repairs. Then perform browser behavior checks for hold cancellation, feed loss, calibration, forecast node reuse, and popup fallback.
5. Report exact changes and test evidence. Leave physical controls, power-cut durability, and Pi performance as unverified until actually exercised.

## Repair pass — 2026-09-23

Implemented R1–R9 in this working tree: interrupted holds are canceled and session changes are checked before hold timing; recorder appends run in a worker thread and GPX parsing no longer holds the recorder lock; weather/511 refresh and shutdown events are separate; feed movement compares against the last requested coordinates and cached provenance is retained until a matching fetch succeeds; feed loss clears detailed values and invalidates calibration input; forecast DOM updates are signature-gated; blocked Earth popups restore OSM; old frontend contract expectations and stale scope/status statements were updated; BLE record shape is validated before access. Added targeted worker/BLE regression tests.

Verification for this repair pass: **76 unit tests pass**; Python compileall and `git diff --check` pass. At that stage, JavaScript parser checks could not run because `node` was unavailable; both checks subsequently passed as recorded below. Browser interaction, physical joystick/session behavior, Pi performance, and recording power-loss durability remain unverified. Recording retention/free-space and periodic fsync policy remain product follow-up items as described above.


## R2 completion pass — 2026-09-23

Completed the remaining R2 implementation. The async sampler now awaits worker-thread
operations for recorder state checks and write-error handling as well as appends;
lifespan shutdown also awaits recorder stop in a worker thread. The sampler awaits
each operation, so it does not accumulate a write queue.

GPX export flushes the active recording and captures an open file's byte boundary
under the recorder lock, then parses only that prefix outside the lock. Concurrent
append/stop cannot extend the export. XML is written one point at a time to a
temporary file in the recording directory and delivered in 64 KiB chunks with
cleanup on response completion/disconnect. Export memory is proportional to a
single JSONL row/point, rather than the whole track. Temporary disk usage grows
with GPX size; allocation/write failures return HTTP 503. GPS-only filtering,
consecutive fix deduplication, XML escaping, and malformed-tail handling remain.

Added seven deterministic regression tests covering fixed-boundary concurrent
append/stop, malformed data and tails, GPS filtering, temporary response-file
cleanup, export failure responses, sampler lock/error responsiveness, and slow
export alongside recording, WebSocket telemetry and an ASGI HTTP telemetry request.
Memory regression compares 1,000 with 36,000 synthetic fixes (two hours at 5 Hz)
and requires peak traced Python allocation growth below 512 KiB. The slow-reader
test requires telemetry gaps below 400 ms and an HTTP response within 800 ms.
These are automated synthetic checks, not a physical Pi/browser performance claim.

Verification: **83 unit tests pass**; Python compilation and `git diff --check`
pass. Async thread-wakeup tests required execution outside the filesystem/network
sandbox because sandboxed wakeups stalled, including a minimal `asyncio.to_thread`
probe. Browser interaction, physical controls, real-storage performance and
power-loss durability remain unverified. Retention, low-space policy and periodic
fsync remain separate follow-up decisions.


## JavaScript syntax follow-up — 2026-09-23

Node.js was installed after the repair pass. `node --check static/app.js` and
`node --check static/maps.js` both pass. Browser behavior, physical controls,
Pi performance, and recording power-loss durability remain unverified as stated
above.

## Commit checkpoint verification — 2026-09-23

After legacy player cleanup, the full unit suite passes **66 tests**. Python
compilation, `git diff --check`, and Node.js syntax checks for `static/app.js`,
`static/maps.js`, and `static/navball.js` pass. README, status, and scope now link
to the manual acceptance checklist. Browser/hardware acceptance and recording
policy work remain open as listed above.
