import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from adapters.airlift import (AirLiftClient, DEVICE_NAME, PRESSURE_UUID, SERVICE_UUID,
                             decode_pressure_packet, decode_status)
from scripts.check_airlift import parse_att_characteristics

UNKNOWN_UUID = 'e1fc2ca1-7e10-4f98-a8b3-0764f70ad668'


def characteristic(uuid=PRESSURE_UUID, handle=0x11, service=SERVICE_UUID, props=('read', 'notify')):
    return SimpleNamespace(uuid=uuid, handle=handle, service_uuid=service,
                           properties=list(props), obj=(f'/org/bluez/hci0/dev_test/char{handle:04x}', {}))


def connected_adapter(**kwargs):
    adapter = AirLiftClient(**kwargs)
    adapter.connected = True
    adapter.connection = 'connected'
    return adapter


class AirLiftDecoderTests(unittest.TestCase):
    def test_confirmed_captures_and_uint16_boundaries(self):
        for raw, left, right in [('00 46 01 36', 7, 31), ('00 46 00 46', 7, 7),
                                 ('00 82 00 78', 13, 12), ('00 6e 00 64', 11, 10),
                                 ('00 5a 00 50', 9, 8), ('00 00 ff ff', 0, 6553.5)]:
            with self.subTest(raw=raw):
                self.assertEqual(decode_pressure_packet(bytes.fromhex(raw)),
                                 {'left_psi': left, 'right_psi': right})
        for raw in (b'', b'\0', b'\0' * 3, b'\0' * 5):
            with self.assertRaises(ValueError):
                decode_pressure_packet(raw)

    def test_status_decoder_does_not_guess_unknown_codes(self):
        for value, expected in ((0, 'idle'), (1, 'deflating'), (2, 'inflating'), (3, 'unknown')):
            self.assertEqual(decode_status(bytes([value])), expected)
        for raw in (b'', b'\0\0'):
            with self.assertRaises(ValueError):
                decode_status(raw)

    def test_unmapped_payloads_and_wrong_service_never_become_pressure_or_state(self):
        adapter = connected_adapter(discovery=True)
        for char in (characteristic(UNKNOWN_UUID, 0x30),
                     characteristic(service='00001800-0000-1000-8000-00805f9b34fb')):
            adapter._accept(char, bytes.fromhex('00 46 01 36'), 'notification', 0)
            adapter._accept(char, b'\x02', 'notification', 0)
        self.assertEqual(adapter.snapshot()['data'], {'left_psi': None, 'right_psi': None, 'state': 'unknown'})

    def test_pressure_and_status_have_independent_freshness_and_disconnect_clears_both(self):
        adapter = connected_adapter(status_uuid=UNKNOWN_UUID)
        with patch('adapters.airlift.time.monotonic', return_value=100):
            adapter._accept(characteristic(), bytes.fromhex('00 46 01 36'), 'read', 0)
            adapter._accept(characteristic(UNKNOWN_UUID, 0x30), b'\x02', 'notification', 0)
            self.assertEqual(adapter.snapshot()['data']['state'], 'inflating')
        with patch('adapters.airlift.time.monotonic', return_value=111):
            self.assertEqual(adapter.snapshot()['status'], 'stale')
            self.assertIsNone(adapter.snapshot()['data']['left_psi'])
            self.assertEqual(adapter.snapshot()['data']['state'], 'unknown')
            adapter._accept(characteristic(), bytes.fromhex('00 46 00 46'), 'read', 0)
            self.assertEqual(adapter.snapshot()['status'], 'live')
            self.assertEqual(adapter.snapshot()['data']['state'], 'unknown')
        adapter._clear()
        # A queued callback from the previous connection must not revive old values.
        adapter.connected = True
        adapter._accept(characteristic(), bytes.fromhex('00 46 01 36'), 'notification', 0)
        self.assertIsNone(adapter.snapshot()['data']['left_psi'])
        adapter._clear()
        self.assertEqual(adapter.snapshot()['data'], {'left_psi': None, 'right_psi': None, 'state': 'disconnected'})

    def test_bad_packet_does_not_refresh_age_and_debug_logs_include_provenance(self):
        adapter = connected_adapter()
        with self.assertLogs('ovrland.airlift', level='DEBUG') as logs:
            adapter._accept(characteristic(), bytes.fromhex('00 46 01 36'), 'notification', 0)
        event = json.loads(logs.records[0].getMessage())
        for key in ('timestamp', 'uuid', 'handle', 'handle_hex', 'source', 'raw_payload', 'decoded'):
            self.assertIn(key, event)
        self.assertEqual(event['decoded']['right_psi'], 31)
        self.assertEqual(event['handle_kind'], 'bluez_declaration')
        received = adapter.pressure_received
        adapter._accept(characteristic(), b'bad', 'read', 0)
        self.assertEqual(adapter.pressure_received, received)
        self.assertEqual(adapter.snapshot()['invalid_packets'], 1)

    def test_att_map_uses_explicit_value_handle_not_declaration(self):
        output = ('handle: 0x0011, char properties: 0x12, char value handle: 0x0012, uuid: ' + PRESSURE_UUID + '\n'
                  'handle: 0x0030, char properties: 0x10, char value handle: 0x0031, uuid: ' + UNKNOWN_UUID)
        entries = parse_att_characteristics(output)
        self.assertEqual(entries[1]['att_value_handle'], 0x31)
        self.assertEqual(entries[1]['declaration_handle'], 0x30)
        self.assertEqual(entries[1]['uuid'], UNKNOWN_UUID)


class AirLiftBLETests(unittest.IsolatedAsyncioTestCase):
    async def test_scan_matches_exact_name_or_explicit_address(self):
        scanner = SimpleNamespace(find_device_by_filter=AsyncMock(return_value=None))
        adapter = AirLiftClient()
        await adapter.scan(scanner)
        predicate = scanner.find_device_by_filter.call_args.args[0]
        self.assertTrue(predicate(SimpleNamespace(name=None), SimpleNamespace(local_name=DEVICE_NAME)))
        self.assertFalse(predicate(SimpleNamespace(name='WirelessAir-other'), SimpleNamespace(local_name=None)))
        adapter.address = 'AA:BB:CC:DD:EE:FF'
        self.assertTrue(predicate(SimpleNamespace(address='aa:bb:cc:dd:ee:ff'), None))

    async def test_session_reads_and_subscribes_without_control_writes_and_cleans_up_on_cancel(self):
        adapter = AirLiftClient(discovery=True)
        chars = [characteristic(), characteristic(UNKNOWN_UUID, 0x30)]
        client = SimpleNamespace(
            services=[SimpleNamespace(characteristics=chars)], is_connected=True,
            connect=AsyncMock(), disconnect=AsyncMock(), start_notify=AsyncMock(),
            read_gatt_char=AsyncMock(return_value=bytes.fromhex('00 46 01 36')),
            write_gatt_char=AsyncMock(), write_gatt_descriptor=AsyncMock())
        device = SimpleNamespace(address='AA:BB:CC:DD:EE:FF')
        scanner = SimpleNamespace(find_device_by_filter=AsyncMock(return_value=device))
        task = asyncio.create_task(adapter._session(lambda *args, **kwargs: client, scanner))
        try:
            for _ in range(50):
                if adapter.snapshot()['pressure_packets']:
                    break
                await asyncio.sleep(.01)
            reading = adapter.snapshot()
            self.assertEqual(reading['data']['left_psi'], 7)
            self.assertEqual(reading['data']['right_psi'], 31)
            self.assertEqual(reading['data']['state'], 'unknown')
            self.assertEqual(client.start_notify.await_count, 2)
            self.assertEqual(len(reading['characteristics']), 2)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
        client.disconnect.assert_awaited_once()
        client.write_gatt_char.assert_not_called()
        client.write_gatt_descriptor.assert_not_called()
        self.assertEqual(adapter.snapshot()['data']['state'], 'disconnected')

    async def test_busy_peer_retries_with_bounded_backoff(self):
        adapter = AirLiftClient()
        waits = []

        async def pause(seconds):
            waits.append(seconds)
            if len(waits) == 4:
                raise asyncio.CancelledError

        with patch.object(adapter, '_session', AsyncMock(side_effect=OSError('busy'))), \
             patch('adapters.airlift.asyncio.sleep', side_effect=pause), \
             self.assertLogs('ovrland.airlift', level='WARNING'):
            with self.assertRaises(asyncio.CancelledError):
                await adapter._run(None, None)
        self.assertEqual(waits, [15, 30, 60, 60])
        self.assertEqual(adapter.snapshot()['data']['state'], 'disconnected')

    async def test_disabled_adapter_never_opens_ble(self):
        adapter = AirLiftClient(enabled=False)
        with patch('adapters.airlift.threading.Thread') as thread:
            adapter.start()
            thread.assert_not_called()
        self.assertEqual(adapter.snapshot()['status'], 'disabled')

    async def test_subscription_failure_disconnects_and_clears_old_readings(self):
        adapter = AirLiftClient()
        client = SimpleNamespace(services=[], connect=AsyncMock(), disconnect=AsyncMock())
        scanner = SimpleNamespace(find_device_by_filter=AsyncMock(return_value=SimpleNamespace(address='test')))
        with self.assertRaises(ValueError):
            await adapter._session(lambda *args, **kwargs: client, scanner)
        client.disconnect.assert_awaited_once()
        self.assertIsNone(adapter.snapshot()['data']['left_psi'])

    async def test_app_lifecycle_starts_only_in_live_mode_and_stops_on_failure(self):
        import app
        from contextlib import ExitStack
        for mode in ('live', 'mock'):
            with self.subTest(mode=mode), ExitStack() as stack:
                stack.enter_context(patch.object(app, 'MODE', mode))
                adapters = [stack.enter_context(patch.object(app, name))
                            for name in ('nano', 'gps', 'network', 'airlift', 'cliamp')]
                with self.assertRaises(RuntimeError):
                    async with app.lifespan(app.app):
                        raise RuntimeError('test cleanup')
                for source in adapters[:-1]:
                    self.assertEqual(source.start.call_count, int(mode == 'live'))
                    self.assertEqual(source.stop.call_count, int(mode == 'live'))
                adapters[-1].stop.assert_called_once()


class AirLiftTelemetryTests(unittest.TestCase):
    def test_live_snapshot_never_leaks_mock_pressure(self):
        import app
        adapter = AirLiftClient(enabled=False)
        with patch.object(app, 'airlift', adapter), patch.object(app, 'MODE', 'live'):
            data = app.snapshot()
        self.assertIsNone(data['suspension']['left_psi'])
        self.assertEqual(data['suspension']['state'], 'disconnected')
        self.assertEqual(data['sources']['airlift'], 'disabled')
        adapter.connected = True
        adapter._accept(characteristic(), bytes.fromhex('00 46 01 36'), 'notification', 0)
        with patch.object(app, 'airlift', adapter), patch.object(app, 'MODE', 'live'):
            data = app.snapshot()
        self.assertEqual(data['suspension']['right_psi'], 31)
        self.assertEqual(data['sources']['airlift'], 'live')
        with patch.object(app, 'MODE', 'mock'):
            data = app.snapshot()
        self.assertEqual(data['sources']['airlift'], 'mock')
        self.assertEqual(data['suspension']['left_psi'], 7)


if __name__ == '__main__':
    unittest.main()
