# Air Lift WirelessAir — read-only integration

The rear suspension card is available in Drive and Adventure, including a
joystick-accessible detail with Back. It shows left/right PSI to one decimal
place and Idle, Inflating, Deflating, Disconnected, or Unknown. The initial status
UUID is **unmapped**, so connected telemetry reports Unknown until configured.
Mock mode shows explicitly simulated 7.0/7.0 PSI and never opens BLE.

## Confirmed protocol

- Device name: `WirelessAir-095789` (exact match; no matching by service alone).
- Service: `0003abcd-0000-1000-8000-00805f9b0131`.
- Measured pressure UUID: `00031234-0000-1000-8000-00805f9b0131`.
- Captured pressure ATT value handle: `0x0012` (informational; access uses UUID).
- Pressure payload: exactly four bytes, two big-endian uint16 values divided by
  ten. `00 46 01 36` = left 7.0 PSI, right 31.0 PSI.
- Captured status ATT value handle: `0x0031`, UUID not yet confirmed.
- A confirmed status UUID accepts exactly one byte: 00 idle, 01 deflating,
  02 inflating. Other single-byte values produce Unknown.
- `e1fc2ca1-7e10-4f98-a8b3-0764f70ad668` and
  `8070d7a0-8c69-47fc-81e3-3f76dc93bac6` are not pressure sources. Discovery logs
  their payloads without assigning meanings or publishing them as measurements.

These protocol facts come from the supplied Android HCI captures. Target-pressure
encoding alone is not a control protocol. There are no pressure adjustment
endpoints, UI controls, characteristic writes, pairing attempts, or control
commands in this adapter. Bleak's notification subscription can configure the
standard CCCD descriptor through the OS; that is notification setup, not a
pressure command. No application code writes characteristics or descriptors.

## Truck test and status mapping

Close the official app and release the handheld remote's connection before
testing. Only run one OVRLand/probe BLE client at a time. The adapter does not
disconnect another controller, change system Bluetooth settings, or claim to know
whether a connection failure means a busy remote, range loss, or powered-off unit.

Start a bounded discovery/telemetry probe (exit 0 when pressures were received,
2 when none were received or a probe error occurred):

```bash
.venv/bin/python scripts/check_airlift.py --seconds 45
```

It scans by exact name, connects, enumerates all characteristic UUIDs and backend
handles, and subscribes/reads within the Air Lift service. It also probes
characteristics at backend handles 0x0030/0x0031 for status investigation, without
decoding them. Each payload log includes UTC timestamp, UUID, service, backend
handle and kind, `notification` or `read`, raw hex, and decoded pressure where
applicable. Discovery alone does not enable status decoding. The connection log
includes the device MAC. `--address AA:BB:CC:DD:EE:FF` selects a known device
explicitly if its advertisement omits the name.

**Pi handle distinction:** Bleak 1.1.1 derives a handle from BlueZ's `charXXXX`
object path, which is the characteristic declaration handle. It is not the ATT
value handle from an HCI notification. We label this `bluez_declaration` and do
not silently add one or treat a nearby handle as a confirmed mapping. See the
[BlueZ implementation](https://github.com/bluez/bluez/blob/master/src/gatt-client.c)
and [Bleak notification API](https://bleak.readthedocs.io/en/stable/api/client.html#bleak.BleakClient.start_notify).

After the first probe exits, use its MAC for exact read-only ATT enumeration:

```bash
.venv/bin/python scripts/check_airlift.py --address AA:BB:CC:DD:EE:FF --att-map
```

This uses the system `gatttool --characteristics` (installed on this Pi), with a
25-second timeout and no BLE value writes. Supply `--address-type random` if the
device advertises a random address; the default is public. It reports declaration
and value handles separately, and prints the UUID whose **value handle** equals
`0x0031`. Failure or no match leaves the UUID unknown. This command exits after
enumeration; it does not start a second concurrent Bleak connection. Share the
`status_handle_mapping` record and payload logs to verify the mapping. Handles
can change with firmware; retain the verified UUID rather than hard-coding a
runtime ATT handle.

Once the mapping is verified, test it with:

```bash
.venv/bin/python scripts/check_airlift.py --status-uuid CONFIRMED_UUID --seconds 45
```

## Dashboard configuration

BLE is opt-in, to avoid taking a single-controller connection during unrelated
dashboard use. With the existing service stopped, enable the dashboard adapter:

```bash
OVRLAND_AIRLIFT_ENABLED=1 OVRLAND_AIRLIFT_DISCOVERY=1 \
  .venv/bin/uvicorn app:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

For the kiosk service, set environment overrides with `systemctl --user edit
ovrland.service`, then restart it when ready:

```ini
[Service]
Environment=OVRLAND_AIRLIFT_ENABLED=1
Environment=OVRLAND_AIRLIFT_DISCOVERY=1
```

Optional variables:

| Variable | Purpose |
| --- | --- |
| `OVRLAND_AIRLIFT_ADDRESS` | Exact BLE MAC instead of name matching |
| `OVRLAND_AIRLIFT_STATUS_UUID` | Verified status UUID; omit while unknown |
| `OVRLAND_AIRLIFT_DISCOVERY=1` | GATT inventory and raw discovery logging |
| `OVRLAND_AIRLIFT_DEBUG=1` | Raw/decoded payload logs without extra discovery subscriptions |
| `OVRLAND_AIRLIFT_ENABLED=0` | Release/disable this adapter at next startup |

Read logs with `journalctl --user -u ovrland.service -f`. Disable discovery/debug
after testing to avoid continuous raw payload logs. No trip history or recording
is added; log retention follows the host's existing logging configuration.

## Telemetry and connection behavior

`GET /api/telemetry` and `/ws/telemetry` expose:

```json
{
  "suspension": {"left_psi": 7.0, "right_psi": 31.0, "state": "unknown"},
  "sources": {"airlift": "live"}
}
```

The `airlift` metadata contains connection status, pressure age/UTC receive time,
configured status UUID, GATT inventory, packet counters, and connection errors.
Known readable characteristics are polled every two seconds as well as subscribing
to notifications, so unchanged pressures can stay fresh when reads are supported.
Pressure and status expire independently after ten seconds; absent/stale pressures
are null, never zero or copied from the mock fixture. Stale status becomes Unknown.
Disconnect immediately clears both readings, and old connection callbacks cannot
revive them. A lost browser telemetry feed clears the card too.

Failed connections use 15-, 30-, then 60-second delays (capped at 60), with an
eight-second scan and bounded connection/I/O timeouts. Shutdown cancels pending
scan/read/backoff work and disconnects the adapter. This behavior is tested with
fake BLE peers; actual radio reception, firmware compatibility, and status UUID
mapping still require the truck test.
