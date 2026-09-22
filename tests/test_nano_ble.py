import json
import unittest

from adapters.nano_ble import END, HEADER_BYTES, START, NanoBLE, PacketDecoder, expand_record


def packets(record, frame=7):
    raw = json.dumps(record).encode()
    result = []
    for index, start in enumerate(range(0, len(raw), 16)):
        part = raw[start:start + 16]
        result.append(bytes([START if index == 0 else 0, frame, index, len(part)]) + part)
    result.append(bytes([END, frame, len(result), 0]))
    return result


class PacketDecoderTests(unittest.TestCase):
    def test_reassembles_a_json_record(self):
        record = {'type': 'joystick', 'ms': 99, 'x': 0.0, 'y': -1.0, 'pressed': False}
        decoder = PacketDecoder()
        received = None
        for packet in packets(record):
            received = decoder.feed(packet) or received
        self.assertEqual(json.loads(received), record)

    def test_dropped_or_malformed_packet_is_discarded_until_next_start(self):
        record = {'type': 'joystick', 'ms': 1, 'x': 0, 'y': 0, 'pressed': False}
        stream = packets(record)
        decoder = PacketDecoder()
        decoder.feed(stream[0])
        self.assertIsNone(decoder.feed(stream[2]))
        self.assertIsNone(decoder.feed(bytes([START, 3, 1, 0])))
        received = None
        for packet in packets(record, frame=4):
            received = decoder.feed(packet) or received
        self.assertEqual(json.loads(received), record)

    def test_rejects_invalid_length(self):
        decoder = PacketDecoder()
        self.assertIsNone(decoder.feed(bytes([START, 1, 0, 5]) + b'abc'))
        self.assertEqual(HEADER_BYTES, 4)

    def test_notification_updates_the_shared_nano_state(self):
        record = {'type': 'joystick', 'ms': 2, 'x': 0.0, 'y': 0.0, 'pressed': False,
                  'imu_ok': False, 'env_ok': False, 'baro_ok': False, 'apds_ok': False}
        nano = NanoBLE()
        for packet in packets(record):
            nano._notification(None, packet)
        self.assertEqual(nano.snapshot()['status'], 'live')
        self.assertEqual(nano.snapshot()['data']['device_ms'], 2)

    def test_compact_record_expands_to_the_usb_contract(self):
        data = expand_record({'m': 10, 'x': -25, 'y': 50, 'b': 1, 'f': 15,
                              'a': [20, -1000, 5], 'e': [2534, 40, 899, 10054],
                              'l': [1, 2, 3, 4]})
        self.assertEqual(data['x'], -.25)
        self.assertEqual(data['temp_c'], 25.34)
        self.assertEqual(data['altitude_m'], 1005.4)
        self.assertTrue(data['pressed'])


if __name__ == '__main__':
    unittest.main()
