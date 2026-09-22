import socket
import unittest
from unittest.mock import MagicMock, patch

from adapters.network import Network


class NetworkTests(unittest.TestCase):
    def test_reachability_probe_uses_configured_endpoint(self):
        adapter = Network(host='203.0.113.10', port=8443, timeout_seconds=3)
        connection = MagicMock()
        with patch('adapters.network.socket.create_connection', return_value=connection) as create:
            adapter._check()
        create.assert_called_once_with(('203.0.113.10', 8443), timeout=3)
        connection.__enter__.assert_called_once()

    def test_failed_probe_marks_network_unavailable(self):
        adapter = Network(interval_seconds=0)
        def fail_and_stop():
            adapter.stop_event.set()
            raise socket.timeout

        with patch.object(adapter, '_check', side_effect=fail_and_stop):
            adapter._run()
        self.assertEqual(adapter.snapshot()['status'], 'unavailable')


if __name__ == '__main__':
    unittest.main()
