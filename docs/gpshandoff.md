
  ## OVRland GPS handoff

  Use gpsd as the hardware layer. The application connects to it over 127.0.0.1:2947 and reads JSON reports. GPSD supports common NMEA and binary USB receivers and prevents multiple app
  components from fighting over the serial device. GPSD documentation (https://gpsd.io/gpsd.html)

  ### 1. Install on Raspberry Pi OS

  sudo apt update
  sudo apt install gpsd gpsd-clients

  gpsd-clients exists separately on Debian/Raspberry Pi OS, unlike Arch where the tools were included differently. It provides tools such as cgps and gpspipe. Debian gpsd-clients package
  (https://packages.debian.org/gpsd-clients)

  pps-tools is only needed for precision PPS clock synchronization—not ordinary latitude/longitude fixes.

  ### 2. Find the receiver

  For USB receivers, check:

  ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
  ls -l /dev/serial/by-id/ 2>/dev/null

  Prefer a /dev/serial/by-id/... path when available because it remains stable across reboots.

  For a receiver wired to the Pi’s GPIO UART, use /dev/serial0. Enable the UART hardware and disable the serial login console through sudo raspi-config. Raspberry Pi serial configuration
  (https://www.raspberrypi.com/documentation/configuration/computers/raspberry-pi.html#enable-or-disable-serial-port)

  ### 3. Grant serial permission once

  Raspberry Pi OS normally assigns serial devices to dialout:

  sudo usermod -aG dialout "$USER"

  Log out and back in—or reboot—then verify:

  id
  test -r /dev/ttyACM0 && test -w /dev/ttyACM0 && echo "serial access ready"

  Trail Ledger used uucp on Arch. On Raspberry Pi OS, expect dialout; always confirm with ls -l DEVICE.

  No password should be required during normal application launches after this one-time setup.

  ### 4. Choose exactly one gpsd owner

  Do not mix these approaches:

  - Recommended on the Pi: systemd owns gpsd; OVRland only connects to port 2947.
  - Application-owned: disable the system service/socket, then OVRland starts and stops its own child process.

  The earlier error:

  Can't bind to IPv4/TCP port gpsd(2947), Address already in use

  meant gpsd or gpsd.socket already owned port 2947. Diagnose with:

  systemctl status gpsd.service gpsd.socket
  ss -ltnp | grep ':2947'

  If using application-owned gpsd, perform this one-time setup:

  sudo systemctl disable --now gpsd.socket gpsd.service

  Then the app may launch:

  gpsd -N -n /dev/ttyACM0

  -N keeps gpsd in the foreground so the parent app can manage it. The app must terminate only the gpsd process it started—never an existing external service.

  ### 5. Verify operation

  With gpsd running:

  gpspipe -w -n 20

  or:

  cgps -s

  Expect:

  - TPV reports
  - mode: 2 for a 2D fix or mode: 3 for a 3D fix
  - lat and lon
  - SKY reports containing satellite data

  The receiver may require several minutes under open sky for its first fix.

  gpsmon is deprecated; use cgps or gpspipe for normal testing.

  ### 6. OVRland application behavior

  The working Trail Ledger pattern is in gps-travel-journal/trail_ledger/gps_client.py:

  1. Look for /dev/ttyACM*, /dev/ttyUSB*, and on Pi /dev/serial/by-id/* or /dev/serial0.
  2. Check read/write permission before starting anything.
  3. First try connecting to 127.0.0.1:2947.
  4. If an external gpsd answers, use it and do not start another.
  5. If no server exists and the app owns GPS lifecycle, launch:

     gpsd -N -n DEVICE

  6. Connect and send:

     ?WATCH={"enable":true,"json":true};

  7. Parse newline-separated JSON:
      - TPV: position and time
      - SKY: satellites seen and used

  8. Accept a usable fix only when mode >= 2 and lat/lon exist.
  9. Prefer altitude in this order:
      - altMSL
      - altHAE
      - alt

  10. Use epx, epy, or eph for approximate horizontal accuracy.
  11. Reconnect automatically every few seconds after disconnection.
  12. Continue running normally when no receiver is present.
  13. Detect later hot-plugging.
  14. Enable “Use GPS Location” only after a valid fix.
  15. On shutdown, stop only an application-owned child gpsd.

  GPSD clients connect to port 2947 and enable JSON streaming with the WATCH request. Official client guide (https://gpsd.io/client-howto.html)

  ### Important failure meanings

  - Permission denied opening /dev/ttyACM0: user lacks the serial-device group or needs to log in again.
  - Address already in use on port 2947: another gpsd or systemd socket is already active.
  - Receiver detected but no position: it has no satellite fix yet; move outdoors.
  - No /dev/ttyACM* device: check /dev/ttyUSB*, /dev/serial/by-id/, USB power, and cabling.
  - SHM cleanup warning after startup failure: secondary fallout; fix the serial permission or competing gpsd first.