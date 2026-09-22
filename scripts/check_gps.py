#!/usr/bin/env python3
"""Read-only USB GPS smoke test for the Pi; does not start the dashboard."""
import argparse
import glob
import sys
import time

import serial


def devices():
    paths = glob.glob('/dev/serial/by-id/*') + glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')
    return list(dict.fromkeys(paths))


def valid_sentence(line):
    line = line.strip()
    if not line.startswith('$') or '*' not in line:
        return None
    body, checksum = line[1:].rsplit('*', 1)
    try:
        calculated = 0
        for character in body:
            calculated ^= ord(character)
        if int(checksum[:2], 16) != calculated:
            return None
    except ValueError:
        return None
    return body.split(',')


def coordinate(value, hemisphere):
    if not value or not hemisphere:
        return None
    degrees = int(float(value) / 100)
    minutes = float(value) - degrees * 100
    result = degrees + minutes / 60
    return -result if hemisphere in ('S', 'W') else result


def main():
    parser = argparse.ArgumentParser(description='Check a USB NMEA GPS on the Pi')
    parser.add_argument('device', nargs='?', help='serial path; defaults to the first USB GPS candidate')
    parser.add_argument('--baud', type=int, default=9600)
    parser.add_argument('--seconds', type=float, default=30)
    args = parser.parse_args()
    candidates = [args.device] if args.device else devices()
    if not candidates:
        print('No /dev/serial/by-id, /dev/ttyUSB*, or /dev/ttyACM* device found.', file=sys.stderr)
        return 2
    print('Candidates:', ', '.join(candidates))
    for path in candidates:
        try:
            with serial.Serial(path, args.baud, timeout=1) as port:
                print(f'Reading {path} at {args.baud} baud for {args.seconds:g}s (read-only)…')
                deadline = time.monotonic() + args.seconds
                sentences = fixes = 0
                while time.monotonic() < deadline:
                    fields = valid_sentence(port.readline().decode('ascii', 'ignore'))
                    if not fields:
                        continue
                    sentences += 1
                    kind = fields[0][-3:]
                    if kind == 'GGA' and len(fields) > 9:
                        lat = coordinate(fields[2], fields[3]); lon = coordinate(fields[4], fields[5])
                        if fields[6] not in ('', '0') and lat is not None and lon is not None:
                            fixes += 1
                            print(f'FIX lat={lat:.6f} lon={lon:.6f} quality={fields[6]} satellites={fields[7] or "?"} altitude_m={fields[9] or "?"}')
                    elif kind == 'RMC' and len(fields) > 8 and fields[2] == 'A':
                        lat = coordinate(fields[3], fields[4]); lon = coordinate(fields[5], fields[6])
                        if lat is not None and lon is not None:
                            print(f'RMC lat={lat:.6f} lon={lon:.6f} speed_knots={fields[7] or "?"} heading={fields[8] or "?"}')
                print(f'Valid NMEA sentences: {sentences}; position fixes: {fixes}')
                return 0 if fixes else 1
        except (OSError, serial.SerialException) as error:
            print(f'{path}: {error}', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
