"""Small reachability probe for the Pi's internet-facing connection."""
import socket
import threading


class Network:
    def __init__(self, host='1.1.1.1', port=443, interval_seconds=15, timeout_seconds=2):
        self.host = host
        self.port = port
        self.interval_seconds = interval_seconds
        self.timeout_seconds = timeout_seconds
        self.stop_event = threading.Event()
        self.thread = None
        self.lock = threading.Lock()
        self.status = 'checking'

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='network-check')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.timeout_seconds + 1)

    def snapshot(self):
        with self.lock:
            return {'status': self.status}

    def _check(self):
        with socket.create_connection((self.host, self.port), timeout=self.timeout_seconds):
            pass

    def _run(self):
        while not self.stop_event.is_set():
            try:
                self._check()
                status = 'connected'
            except OSError:
                status = 'unavailable'
            with self.lock:
                self.status = status
            self.stop_event.wait(self.interval_seconds)
