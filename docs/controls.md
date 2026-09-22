# Control contract

OVRLand is designed from one primitive controller, not from desktop mouse or
keyboard assumptions.

## Primitive input

The Nano joystick exposes only these discrete, release-gated input events:

| Input | Meaning |
| --- | --- |
| X negative / positive | Left / right |
| Y positive / negative | Up / down |
| Center switch | Click / select |

No joystick action moves a mouse cursor, emits a global OS mouse event, emulates a
keyboard, or depends on a steering-wheel controller or motion remote. Touch is a
separate direct-manipulation input for a copilot; it must not be required to
complete a joystick control path.

## Navigation rule

Every screen or overlay must declare a small focus model before controls are
implemented:

1. What receives focus when the screen opens.
2. What X and Y do in that state.
3. What click activates.
4. The visible, joystick-reachable way back to the previous state.
5. Which actions are unavailable and why.

Focus must always be visible. A click activates the focused control; it must not
rely on the position of an invisible cursor.

## Current dashboard model

```text
Mode tabs        X = change tab       click = select tab
    Y down
Top module row   X = change module    click = open module
    Y down
Lower module row X = change module    click = open module
    Y down
Footer           X = choose control   click = activate control
    Y up
Lower module row Y up = top module row
    Y up
Top module row   Y up = mode tabs
```

The selected Map module uses its own expanded-map state rather than mouse
emulation. Its control row is:

```text
OSM | GAIA | EARTH / DISCOVERY | OFFLINE | CENTER GPS | BACK TO DASHBOARD
```

X moves across this row and click activates it. `BACK TO DASHBOARD` returns focus
to the Map module. `CENTER GPS` appears only with a valid position. Panning and
zooming remain optional touchscreen operations.

The expanded Vehicle Attitude module exposes `CALIBRATE LEVEL | BACK TO
DASHBOARD`. Selecting calibration opens a confirmation state with `SET CURRENT
POSITION AS LEVEL | CANCEL`; setting level saves a display offset without
changing raw telemetry.

Every other expanded module opens with `BACK TO DASHBOARD` visibly focused. Click
returns to its source module; Y up also moves focus to that explicit Back action.

Air Suspension is a read-only module in Drive and Adventure. X selects it in the
module row and click opens live left/right pressures and status. The detail opens
with `BACK TO DASHBOARD` focused; X/Y keep the single Back action reachable and
click returns to the originating card. Touch can open the same detail. Pressure
adjustment is unavailable in this implementation; no increase/decrease actions
or BLE pressure commands are exposed.

The Music tab exposes the CLIAMP-backed `CURATED RADIO` module and retains the
separate optional `SPOTIFY` module. Spotify currently opens its existing status
detail and Back path; it is not routed through the radio implementation. Opening
Curated Radio focuses Play / Pause and exposes this control row:

```text
PREVIOUS | PLAY / PAUSE | NEXT | CURATED RADIO | VOLUME - | VOLUME +
SHUFFLE | REPEAT | STOP | BACK TO DASHBOARD
```

Selecting `CURATED RADIO` loads OVRLand's small static preset list:

```text
OPEN ROAD | PACIFIC DRIVE | INDIE ROAD | OLD HIGHWAY | RETRO RUN
BACKROADS | TRAIL FOLK | TRAIL MODE | CAMP CHILL | NIGHT CAMP
STARGAZING | ORBITAL CAMP | GARAGE SOUL | OVRLAND AFTER DARK
BACK TO PLAYER
```

X moves across either row and click activates the focused action or tunes the
focused station. Y up moves focus to the explicit Back action. A station load
tries its configured primary URL, then one fallback URL, and returns control with
`STREAM UNAVAILABLE` if both fail. CLIAMP resolves the SomaFM PLS URLs and exposes
available ICY now-playing metadata. Local media remains out of scope.
