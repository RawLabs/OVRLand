# Development hardware

## Pi and display
Raspberry Pi 4, Raspberry Pi OS 64-bit Desktop per project setup.
Hostname/user: ovrland / ovrld. Development Ethernet: Pi 10.42.0.2, laptop 10.42.0.1.
SSH: `ssh ovrld@10.42.0.2`. VNC is used during development.
Target screen: 1280×800. Chromium kiosk installation is deferred.

Observed Wi-Fi arrangement: wlan0 retains the internet default route. Keep network credentials out of docs, source files and commits.

## Nano 33 BLE Sense Rev2
Persistent USB device:
`/dev/serial/by-id/usb-Arduino_Nano_33_BLE_6645321B7A5D0D0F-if00`

115200 baud, newline-delimited JSON. About 4.9 Hz measured in the initial Pi check;
the earlier firmware expectation was 20 Hz. Live adapter does not write commands.

| Joystick connection | Nano pin |
| --- | --- |
| GND | GND |
| +5V label | 3V3 supply |
| VRX | A0 |
| VRY | A1 |
| SW | D2, active-low |

Observed raw center approximately 518. Normalized X: left=-1, right=+1.
Normalized Y: up=+1, down=-1. Button: pressed=true when pushed.

Mounting convention: +X forward (USB toward front), +Y right, +Z up.
Firmware publishes forward_g=ax, right_g=ay, up_g=az.
Live tilt uses acceleration only; motion affects it. The dashboard supports a
persistent display-level offset; gyro bias, sensor fusion, and magnetometer
calibration remain pending.

Firmware covers BMI270 acceleration/gyro, BMM150 magnetometer, HS3003 temperature/
humidity, LPS22HB pressure/altitude, APDS9960 proximity/color/gesture, and joystick.
Microphone PDM buffering/streaming is not implemented.

The versioned wireless sketch is `firmware/ovrland-nano/ovrland-nano.ino`. It keeps
the USB JSON stream and advertises an `OVRLand Nano` BLE GATT service with reliable
20-byte telemetry indications. Compile first; uploading replaces the current firmware.
After upload, start OVRLand with `OVRLAND_NANO_TRANSPORT=ble`; optionally set
`OVRLAND_NANO_BLE_ADDRESS` to the Nano's BLE address to skip service scanning.
The Pi is a BLE central; no Bluetooth pairing or serial profile is used.

User-provided laptop source path: `/home/thinkpad/Work/ovrland-nano/ovrland-nano.ino`.
That sketch is not copied into this app repository.
FQBN: `arduino:mbed_nano:nano33ble`; reported core version: 4.6.0.

## Planned inputs
USB GPS and USB OBD-II use separate future adapters. Nano BLE transport is
implemented and selected with `OVRLAND_NANO_TRANSPORT=ble`.
Touchscreen USB, Nano, GPS, OBD and the added Wi-Fi interface require a fresh USB
port/power inventory before vehicle installation; the original four-port allocation
predated the second Wi-Fi adapter. Powered hub/CSI/wireless choices remain open.
