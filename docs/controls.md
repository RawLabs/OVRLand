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
Dashboard        X/Y = nearest module in that direction
                 click = open module
Top edge         Y up = mode tabs
Bottom edge      Y down = recording controls
Footer           X = choose control    click = activate control
                 Y up = return to focused module
```

Joystick movement follows the visible positions of modules, so all four
directions move to the closest reachable module in that direction. Left/right
wraps to the opposite edge when no module lies in that direction. Focus stays
visible. Every module and button must also work by touch; touching a module opens
its detail, while touching a control activates that control directly. Touch must
not be required to complete any joystick path.

The first joystick Down enters the dashboard at its first module. Up from the
upper edge returns to the mode tabs; Down from the lower edge focuses Record in
the footer. X selects Record, Export Log, or GPS Track, and Up returns to the
last focused module. In System, the first module toggles between Camp Mode and
Full Screen; shutdown controls still require their two-second hold. Detail
controls retain a visible Back action and are directly touchable.

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

The Music tab stays idle until you choose a curated station; selecting a station
starts playback directly in the browser. It retains the separate
optional `SPOTIFY` module. Opening Curated Radio focuses Play / Pause and exposes this
control row:

```text
PREVIOUS STATION | PLAY / PAUSE | NEXT STATION | CURATED RADIO
VOLUME - | VOLUME + | STOP | BACK TO DASHBOARD
```

Selecting `CURATED RADIO` loads OVRLand's small static preset list:

```text
OPEN ROAD | PACIFIC DRIVE | INDIE ROAD | OLD HIGHWAY | RETRO RUN
BACKROADS | TRAIL FOLK | TRAIL MODE | CAMP CHILL | NIGHT CAMP
STARGAZING | ORBITAL CAMP | GARAGE SOUL | OVRLAND AFTER DARK
BACK TO PLAYER
```

X moves across either row and click activates the focused action or tunes the
focused station. Y up moves focus to the explicit Back action. A station plays
from its configured direct audio URL in the browser. The screen reports whether
the stream failed due to network access or unsupported audio format, and updates
the current song title from provider metadata when it is available. Local media
remains out of scope.
