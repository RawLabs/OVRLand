# OVRLand text readability assessment and execution plan

Prepared 2026-09-27. The typography work described here was implemented on 2026-09-27. The original assessment and targets remain below as a record of the design decisions.

## Implementation result

The shared typography scale and component rules are in `static/layout.css`. Drive and Adventure now use larger instrument readings, coordinates, condition values, OBD values, labels, and status text. Expanded attitude, OBD, weather, GPS, calibration, and map views use larger type and wrap long content. OVRadio controls and System actions/logs were enlarged. `static/navball.js` enlarges the canvas markings and warnings. `static/app.js` shows the tilt status in Adventure's main attitude panel. `static/index.html` has updated CSS and JS cache versions.

The repeatable simulated browser audit is `scripts/readability_audit.py`. Run `rtk .venv/bin/python scripts/readability_audit.py` to write screenshots and `measurements.json` to a temporary directory, or pass an output directory as its first argument. It starts a localhost test server, blocks external map requests, and does not operate live service controls.

The final audit rendered 22 states at each of 1280 × 800, 1024 × 600, 1100 × 680, and 1920 × 1080. At the target 1280 × 800 viewport, Drive and Adventure each fit within the viewport without page scrolling. Expanded OBD readings are at least 48 px and Adventure coordinates at least 23 px. No horizontal overflow was measured at the target viewport. The 1024 × 600 dashboards scroll vertically; 3–4 px document overflow was measured behind some open dialogs at smaller viewports, while the dialogs themselves fit horizontally. Screenshots and measurements for this run are in `/tmp/ovr-typography-final/`.

The remaining acceptance step is a seated review on the actual Waveshare display. Record the installed browser's viewport, zoom, device pixel ratio, and eye-to-screen distance, then adjust any readings that still require leaning forward.

## Target and evidence

The owner confirmed a **10.1-inch Waveshare touchscreen, 1280 × 800**. Optimize fullscreen for this display first, then the existing Camp Mode window (nominally 1100 × 680; its browser content area may be smaller). Eye-to-screen distance is not yet specified. Font sizes below are starting design targets, subject to a seated check on the physical display. They are not a claim of measured physical legibility.

Assessment covered source styles, dynamically generated content, and isolated Chromium rendering with simulated telemetry. Measured **22 screen states at each of four CSS viewports**: 1280 × 800, 1100 × 680, 1024 × 600, and 1920 × 1080 (88 combinations). Captured 22 screenshots at 1280 × 800 and visually inspected the main tabs and representative instances of every expansion type. The four tabs are Drive, Adventure, OVRadio, and System (`camp` internally).

States include both dashboards; their map, weather/road/sunset, attitude, calibration, and OBD expansions; Adventure GPS detail; OVRadio player, station chooser, and Spotify placeholder; System; and expanded map offline/Gaia messages. External Earth/Gaia websites and map tile label rendering were not assessed. External requests were blocked, so blank map canvases in the screenshots are intentional. Weather forecasts and station names used assessment fixtures. Live service controls, recordings, calibration, and shutdown were not exercised.

Session evidence is in `/tmp/ovr-typography-audit/`: `measurements.json` and `1280-800-*.png`. The reproducible local assessment script is `/tmp/ovr_typography_audit.py`. These are temporary files; retain useful baseline images with the implementation review before they disappear. Measurement rows also include dashboard elements behind modal overlays; use the modal scope for comparisons, not aggregate text counts.

## Findings

1. **Adventure has substantial unused room around important readings.** At 1280 × 800 the attitude and location side panels are roughly 310 px wide and 494 px tall. Pitch/roll values remain around 20 px, labels 8 px; location coordinates are 11 px with 9 px labels. Altitude is 28 px. These can grow substantially inside the existing panel arrangement.
2. **Opening a module often enlarges its container rather than its text.** The expanded attitude sphere grows to about 520 px, but pitch/roll remain 20–21 px and bearing 20 px. Expanded OBD occupies a large dialog but retains 15 px readings and 9 px labels. Both leave large areas empty.
3. **The stylesheet has competing font-size overrides.** `style.css` is followed by `layout.css`, which contains older compositions, breakpoint overrides, two later readability passes, and a final weather adjustment. Some later rules restore 6–10 px text. Increasing a parent font will not affect many explicitly sized descendants.
4. **Drive is the limiting layout.** Its condition and vehicle strips occupy approximately the right 45% of the workspace. The wind value already ellipsizes with ordinary fixture data. Adventure uses the full width for these strips and can support larger type more easily.
5. **The existing GPS expansion is a useful starting point.** It already uses 14 px labels, 22 px detail values, and 34 px coordinates at the target viewport. Most other expanded modules fall well below this.
6. **System allocates more emphasis to its heading/RGB string than its actions.** Capture buttons use 10 px type; recording/export controls 11 px; power controls 13 px; status 10 px. The rendered page is already about 1140 px tall at 1280 × 800. Its power-button group stacks into one column despite having space across the screen.
7. **Touch-target size and text size are different issues.** Several 40–88 px tall controls still contain 9–13 px lettering. Their text can increase without expanding the buttons much.
8. **Header and auxiliary text need deliberate treatment.** Source statuses are 9 px, panel headings commonly 9 px, and the long joystick help line remains 8 px. The Internet source label can break awkwardly across lines. More letter spacing makes short, narrow cells harder to fit.
9. **Canvas text is outside the CSS typography system.** `navball.js` draws into a 320 × 320 canvas, with small internal labels and an 11 px logical warning. When displayed below 320 px wide those labels get smaller still. Enlarging CSS text will not fix them.
10. At the target fullscreen viewport the assessed dashboards had no document-level horizontal overflow. Smaller assessed viewports already showed roughly 3–23 px of horizontal overflow in some Drive/detail states. Treat that as an existing fit problem to resolve when adjusting text, rather than accepting further overflow.

## Design targets

Use a small shared typography scale, with explicit component variants for compact dashboards and expanded modules. All values below are **CSS pixels at 100% browser zoom**. Confirm the installed browser's viewport and device pixel ratio before final approval.

| Role | Initial target |
| --- | --- |
| Main dashboard pitch, roll, bearing, altitude | 32–40 px; altitude can reach 44 px in Adventure |
| Compact strip numeric values | Drive 22–24 px; Adventure 26–30 px |
| Expanded primary values | 44–56 px |
| Expanded secondary measurements | 24–28 px |
| Dashboard field labels | 14 px minimum; 16 px where space permits |
| Expanded field labels | 16–18 px |
| Action/button text | 16–18 px; 18 px for System power controls |
| Units | 14–16 px; 18–20 px beside expanded primary values |
| Instructions, failure messages, substantive status | 16–18 px |
| Auxiliary provenance, timestamps, compact source status | 12–14 px |
| Main navigation tabs | 18–20 px |
| Detail titles | 28–34 px, allowing room for values and controls |

These are role-specific targets. Existing 40–52 px titles do not need to get larger. Attribution and decorative lettering embedded in the brand artwork are separate from operational readings. Keep attribution visible and usable; 11–12 px is a practical initial target for its compact map corner.

Use tabular numerals for changing readings. Keep the existing type families initially; reduce excessive tracking in long labels rather than compressing or shrinking text. Use normal tracking for prose and roughly 0–0.5 px for dense labels. Give labels/body text a 1.25–1.4 line height and numeric values approximately 1.1–1.2. Preserve existing alert colors, and use the normal text color for operational information currently treated as faint metadata.

## Screen-by-screen work

### Shared header, navigation, and footer

- `nav button`: 17 px at 1280 currently; aim for 18–20 px and reduce the existing 2 px letter spacing. Keep four tabs in their present order and the active/focus indications.
- `.header-sources`: labels 11 px and states 9 px currently. Aim for 12–14 px labels/states, allocate enough width for INTERNET, and wrap statuses at words. Reclaim small amounts of header gap/logo space only if necessary; keep the clock visible.
- `h1`, `.label`, `.demo span`: promote section/panel headings to 14–16 px and connection messages to 12–14 px. The clock at 24 px needs little change.
- `.event-strip`: 10 px at this viewport; target 14–16 px with an auto-sized line box. Failures and held-action feedback must be readable.
- `.joystick-strip`: target 12–14 px for states/help. Allow the help to wrap or use a shorter equivalent instruction, with the complete meaning retained. Budget its height explicitly so it does not push the dashboards below the fullscreen viewport.

### Adventure dashboard — first priority

| Area | Current at 1280 × 800 | Planned treatment |
| --- | --- | --- |
| Pitch/roll | Labels 8 px; readings 20 px | Labels 14–16; readings 36–40; units 14–16. Use the current right-hand numeric column and its vertical room. |
| Bearing | Label 8 px; reading 20 px | Label 14; reading 32–36. Preserve its existing bottom position. |
| Location | Coordinate values 11 px, labels/status 9 px | Coordinates 22–26; labels/status 14–16; altitude 40–44 and unit 16. Keep latitude/longitude stacked and increase their spacing modestly. |
| Weather/road/sunset | Weather 19 px; summary 8; source 6; road 10; cabin 10; wind 14; sunset 18 | Temperature 28–30; summary/labels 14; road 18–22; cabin 22–24; wind 22–24; sunset 26–28. Provenance 12–14 or clearly available in the expanded view if compact space is insufficient. |
| OBD band | Readings 15 px; labels/units around 9 | Readings 28–30; labels 14; units 14–16. Preserve the six-field order. |

Keep the existing left attitude / center map / right location arrangement and column proportions. First enlarge text within the existing boxes. If the condition strip needs more vertical space, start with a row height of about 80 px instead of 58 px, reclaiming the difference from the middle row within the existing workspace height. Confirm the field labels/values fit before selecting a final height.

Coordinates should retain their current data precision. Permit line breaks between label and value, not within a minus sign or decimal number. At narrow widths, the existing expansion is the place for larger complete coordinates; do not silently alter telemetry accuracy to fit text.

### Drive dashboard

- Enlarge pitch/roll to 36–40 px, bearing to 32–36 px, and their labels to 14–16 px. There is room around the existing central sphere; do not enlarge the sphere first.
- Give the narrower condition strip its own layout rules. Use 22–24 px main values and 14 px labels. Permit wind/gust to occupy separate lines and road status to wrap at words; preserve complete units and status meaning.
- If a single condition row cannot fit, group its existing cells into two compact rows **inside the same top-right region**, targeting about 96–104 px overall. Keep the map and attitude in their existing regions. Do not solve the narrowness by dropping back to 8–10 px type.
- OBD readings should be 22–24 px, with 14 px labels. Keep six measurements, allow ENGINE LOAD to wrap, and put units on a separate line where needed. Start with the current 88 px band; allow approximately 96 px only if measured fit requires it.
- Scope the Drive exceptions explicitly. Adventure should not inherit smaller typography merely because Drive has less width.

### Maps, dashboard and full-screen expansion

- `.map-toolbar button` and `.detail-controls button`: currently around 9 px at the target size; aim for 14–16 px dashboard and 16–18 px expanded.
- Allow the embedded map toolbar to wrap to a second row if labels need it. Preserve source selection and Center GPS. Keep the full-screen toolbar and close action visible when its controls wrap.
- Map status/location text: 9 px to 12–14 px; failure messages 14–16 px. Let status and the Open Map link stack locally when necessary.
- Gaia/offline explanatory text: 11–13 px to 18 px; message heading 16 px to 24–28 px; associated actions 16–18 px.
- Preserve map attribution. Changes here apply to OVRLand controls, not text baked into raster map tiles. A future map-label project would require its own assessment.

### Expanded attitude and calibration

- Add explicit expanded selectors for `.detail-module-panel.trail-attitude` and the expanded Drive panel. Both should show pitch, roll, and bearing at 48–56 px, labels 18 px, and units 18–20 px.
- Use the large open area beside the sphere. Align readings into a clear column/group; keep all three visible together at 1280 × 800.
- The sphere already reaches 520 px. Constrain it to the available dialog height if enlarged controls would force essential readings below the fold. Favor a slightly smaller sphere over smaller numbers.
- Keep the existing DOM tilt-status label visible at 16–18 px in normal/unavailable/caution/alarm states. Review `navball.js` separately: canvas markings and warnings need size-aware drawing or a readable DOM counterpart, not just CSS changes.
- Calibration prose: 13 px to 18 px; the `!important` 10 px calibration note to 16 px; confirmation/cancel buttons to 16–18 px. Keep the two-second power-control behavior and calibration interaction semantics unchanged.

### Expanded weather, road, and sunset

- Introduce expanded condition-summary styles. The summary currently inherits the compact dashboard's 6–19 px type despite the much wider dialog. Use temperature 36–40 px, road/wind/sunset 24–28 px, labels 16 px, and provenance 14 px.
- Current-condition cards: labels 10 px to 16 px; values 13 px to 24–28 px. Replace the fixed five-column assumption with a width-aware grid, initially three or four columns at 1280 depending on card content. Wind and precipitation summaries need wrapping or wider spans.
- Daily cards: values 16 px to 26–28 px; text/details 10–12 px to 16 px. Keep two days side by side if they fit; allow individual detail lines to wrap.
- Hourly cards: temperature 20 px to 26–28 px; time/details 10–12 px to 14–16 px. Start with four columns instead of six and permit vertical scrolling in the existing dialog. Keep all 12 hours available.
- Preserve units, stale/unavailable states, 511 failure reasons, observation times, and GPS/default provenance. Ellipsis must not conceal an essential weather/road value or error category.

### Expanded GPS/location

- This is already the most readable detailed telemetry module. Increase coordinates from 34 px to 36–40 px, altitude from 36 to 44–48 px, labels from 14 to 16 px, and GPS diagnostic values from 22 to 24–28 px.
- Increase the card minimum width if needed so long accuracy labels and timestamps can wrap naturally. Keep the existing scrollable diagnostic list and its receiver-confidence note.
- Do not apply a global `.coordinates` rule that accidentally weakens this existing expansion. It has deliberately more specific styles than the compact location panel.

### Expanded OBD

- This is the largest easy improvement. `.detail-module-panel.vehicle-strip` currently renders the compact 15 px row in a very large empty area.
- Give the six readings a three-column, two-row arrangement inside the same dialog. Use 44–52 px values, 18 px labels, and 18 px units. Two columns are appropriate for narrower windows.
- Preserve field order, bindings, and unavailable values. This is a presentation change; it must not add simulated vehicle readings to live mode.

### OVRadio, expanded player, station chooser, and Spotify

- Main track/source titles are already approximately 45 px at 1280; keep them near that size. Increase artist/station text from 11–14 px to 20–22 px, playback state from 12 to 16 px, and volume/availability from 9–10 to 14–16 px.
- Expanded player controls currently use 9 px text. Use 16–18 px and allow two orderly rows of controls while keeping Back visible. Retain existing playback and navigation behavior.
- Station choices use those same tiny buttons. Use 16–18 px labels, generous multiline buttons, and a wrapping grid for long names. Do not rely on hover-only titles for the station's primary name.
- Spotify's large title is already sufficient; enlarge its 14 px description to 20 px and 9 px configuration state to 16 px. Retain the existing placeholder behavior.

### System, recording, and ambient calibration

- Capture buttons 10 px to 16–18 px; export/record actions 11 px to 16 px; power/window actions 13 px to 18 px; action feedback 10 px to 16–18 px.
- Ambient help/logs 9 px to 14–16 px; recording helper text 9 px to 14 px. Let log entries and long export labels wrap.
- The 52 px page heading and up-to-32 px RGB string are already large. A 32–36 px page heading and 24–28 px RGB string would free room while making the actions more prominent.
- Give `.system-actions` an explicit available width, such as `min(860px, 100%)`, so its existing three controls can use three columns on the target display. Preserve control order; retain a single column where needed on narrow screens.
- System already scrolls. Keep vertical scrolling and focus visibility rather than shrinking all text to force every log and control above the fold. Preserve the recent touch-hold fix (`touch-action: none`, context-menu suppression, pointer capture, cancellation).

## Implementation sequence for the executing agent

1. **Establish baseline and protect current work.** Read repository instructions and `git status`. There are existing edits across backend, configuration, frontend, scripts, and tests, including the 511 and touch fixes. Preserve them. Confirm browser zoom, actual CSS viewport, and device pixel ratio on the Waveshare. Capture the four tabs and expansion types before editing.
2. **Define the typography scale and organize its cascade.** Add role variables in `static/layout.css`, e.g. label, auxiliary text, body, action, compact value, main value, detail value. Review the late “readability” and final weather overrides and consolidate the affected font rules instead of appending another conflicting pass. Scope dashboard versus expanded rules explicitly. Keep existing geometry/responsive rules unless a measured fit issue calls for a local change.
3. **Implement Adventure first.** Enlarge attitude/location and the two bands. Compare at 1280 × 800 before touching Drive. Settle the principal label/value scale here.
4. **Implement shared expansions.** Fix attitude, OBD, weather, GPS, calibration, and map typography. `openDetail()` moves the original panel into `#detail-body`; it does not clone it. Selectors relying on its former dashboard ancestor can stop matching. Use `.detail-module-panel` plus its component class, and verify closing restores the compact layout.
5. **Fit Drive and shared chrome.** Apply local strip wrapping and, only if needed, modest row-height adjustments. Enlarge header/status/footer text while fitting the complete fullscreen dashboard. Verify the shared map resizes after opening/closing detail.
6. **Finish OVRadio and System.** Cover radio idle/playing/error, station selection, Spotify placeholder, ambient history, record/export states, window mode, and hold feedback. Perform checks with stubbed actions, not actual shutdown or calibration writes.
7. **Validate and deliver.** Run the checks below, inspect before/after images at native resolution, fix content-fit failures, and bump the touched CSS/JS cache query versions in `static/index.html`. Deliver a concise change summary and screenshots for the target display. Finish with a seated touchscreen review.

Expected files: mainly `static/layout.css`; limited `static/app.js` changes if markup needs separate value/unit lines or explicit expansion identity; `static/navball.js` for canvas text only if needed; `static/index.html` for cache versions and any necessary small semantic changes. Review `static/style.css` for inherited rules without broadly reformatting the minified file. Backend and data formats should not need changes.

## Validation and acceptance

- Primary acceptance viewport: **1280 × 800 at 100% zoom**, with all four tabs and every expansion type listed above. Secondary: actual Camp Mode content viewport, nominal 1100 × 680. Regression sizes: 1024 × 600, 900/901 px breakpoint boundary, 540 px, and 1920 × 1080.
- Keep the existing dashboard regions and module/navigation order. Local card/toolbar wrapping and small row-height adjustments are allowed. Avoid global browser zoom or CSS transforms as a substitute for typography work.
- Drive and Adventure must fit the target fullscreen viewport without page scrolling or horizontal overflow. Expanded weather/GPS and System may scroll vertically; controls and content must remain reachable. No modal horizontal overflow.
- At the target size, operational field labels should be at least 14 px; dashboard pitch/roll/bearing/altitude at least 32 px; compact numeric strip values at least 22 px; road-condition text at least 18 px; and controls at least 16 px except embedded map controls (14–16 px). Coordinates and expanded measurements follow their component targets above. Document any exception with a screenshot and reason. Auxiliary provenance can use 12 px; key failures and warnings require larger text.
- Compare **computed** font sizes, not only declared CSS. Include labels, units, pseudo-element source labels, `small` elements, generated controls, and canvas text. Verify text rendering at the final device pixel ratio.
- Test representative long values: negative pitch/roll; three-digit bearings; full signed GPS coordinates; five-digit altitude; five-digit RPM; units; wind/gust together; “FEED UNAVAILABLE,” “WAITING FOR LOCATION,” “NO REPORT NEARBY,” 511 HTTP errors; long road/station/artist names; metadata unavailable; no GPS; no Nano; OBD unavailable; and recording/export failure text. Use fixtures; retain live data semantics.
- Confirm important values/units are never ellipsized or clipped. Keep labels with their values; use word wrapping for prose. Do not reduce fonts automatically to fit long states.
- Check the expanded attitude in normal, missing-data, caution, and alarm states. Ensure the warning, pitch, roll, and bearing remain readable together.
- Verify open/close cycles restore each moved module, telemetry still updates, map sizing recovers, radio controls remain reachable, and joystick focus tracks wrapped controls correctly.
- Run the existing frontend checks and safe touch regression checks: `rtk .venv/bin/python -m unittest tests.test_frontend_contract`, `rtk node --test tests/test_system_hold.cjs`, and `rtk node --check static/app.js` (also navball if edited). Add browser assertions for actual overflow, critical font sizes, and restoration of moved modules where meaningful; source-string assertions alone cannot verify readability.
- Review on the physical screen from the normal seated position. Record eye-to-screen distance, zoom, viewport, and whether pitch/roll/bearing, road condition, and key actions can be read without leaning forward. Adjust within the planned typography scale before sign-off.

## Priority and scope boundary

**P1:** Adventure attitude/location; expanded attitude/OBD; shared controls; weather and 511 status. These combine the largest readability improvement with substantial available room.

**P2:** Drive strips and header; weather/GPS detail grids; map controls/status; OVRadio controls; System actions and logs.

**P3:** Canvas markings, compact helper text, responsive fit polish, and seated validation.

The intended outcome is the same OVRLand app with substantially more readable text. Preserve the visual theme, map providers, features, telemetry behavior, module order, power-control safeguards, and existing unrelated edits. Avoid spending this pass restyling legacy gauges that the active desktop compositions hide; assess their visibility first.
