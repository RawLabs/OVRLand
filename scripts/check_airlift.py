#!/usr/bin/env python3
"""Bounded read-only WirelessAir probe; never starts dashboard hardware adapters."""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters.airlift import AirLiftClient, DEVICE_NAME


def parse_att_characteristics(output):
    """gatttool explicitly distinguishes declaration and ATT value handles."""
    pattern = (r'handle:\s*(0x[0-9a-f]+),\s*char properties:\s*(0x[0-9a-f]+),\s*'
               r'char value handle:\s*(0x[0-9a-f]+),\s*uuid:\s*([0-9a-f-]+)')
    return [{'declaration_handle': int(declaration, 16),
             'att_value_handle': int(value, 16), 'uuid': uuid.lower()}
            for declaration, _props, value, uuid in re.findall(pattern, output, re.I)]


async def map_att_handles(address, address_type):
    # One read-only connection, completed before Bleak takes its own connection.
    process = await asyncio.create_subprocess_exec(
        'gatttool', '-b', address, '-t', address_type, '--characteristics',
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=25)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.communicate()
        raise
    entries = parse_att_characteristics(stdout.decode(errors='replace'))
    if process.returncode or not entries:
        raise RuntimeError(stderr.decode(errors='replace').strip() or 'No ATT characteristics returned')
    for entry in entries:
        print(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                          'event': 'att_mapping', 'source': 'gatttool_characteristic_discovery',
                          **entry, 'att_value_handle_hex': f"0x{entry['att_value_handle']:04x}"}), flush=True)
    owners = [item for item in entries if item['att_value_handle'] == 0x0031]
    print(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                      'event': 'status_handle_mapping', 'att_value_handle': '0x0031',
                      'uuid': owners[0]['uuid'] if len(owners) == 1 else None,
                      'verified_handle_mapping': len(owners) == 1}), flush=True)
    return entries


async def run(args):
    from bleak import BleakClient, BleakScanner
    if args.att_map:
        await map_att_handles(args.address, args.address_type)
        return 0
    adapter = AirLiftClient(address=args.address, status_uuid=args.status_uuid, discovery=True)
    try:
        await asyncio.wait_for(adapter._run(BleakClient, BleakScanner), timeout=args.seconds)
    except asyncio.TimeoutError:
        pass
    result = adapter.snapshot()
    print(json.dumps({'timestamp': datetime.now(timezone.utc).isoformat(),
                      'event': 'probe_complete', 'telemetry': result}), flush=True)
    return 0 if result['pressure_packets'] else 2


def main():
    parser = argparse.ArgumentParser(description=f'Read-only BLE discovery/telemetry for {DEVICE_NAME}')
    parser.add_argument('--address', help='Optional BLE MAC; otherwise match the exact device name')
    parser.add_argument('--seconds', type=float, default=45, help='Probe duration (default: 45 seconds)')
    parser.add_argument('--status-uuid', help='Confirmed status UUID only; unset keeps state unknown')
    parser.add_argument('--att-map', action='store_true',
                        help='Only enumerate exact ATT handles with gatttool; requires --address')
    parser.add_argument('--address-type', choices=('public', 'random'), default='public',
                        help='Address type for --att-map; use the device discovery information')
    args = parser.parse_args()
    if not 0 < args.seconds <= 3600:
        parser.error('--seconds must be between 0 and 3600')
    if args.att_map and not (args.address and re.fullmatch(r'(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}', args.address)):
        parser.error('--att-map requires a BLE MAC in --address')
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    logging.getLogger('ovrland.airlift').setLevel(logging.DEBUG)
    try:
        return asyncio.run(run(args))
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'Air Lift probe failed: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
