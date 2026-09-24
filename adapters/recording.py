"""Service-owned JSONL telemetry recordings and GPS-only GPX export."""
import json
import math
import os
import tempfile
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


RECORDING_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class Recording:
    """Write complete telemetry snapshots until stopped or the service exits."""

    def __init__(self, directory):
        self.directory = Path(directory).expanduser()
        self._lock = threading.RLock()
        self._file = None
        self._recording_id = None
        self._started_at = None
        self._error = None

    def is_recording(self):
        with self._lock:
            return self._file is not None

    def start(self):
        with self._lock:
            if self._file is not None:
                return self._status_locked()
            self.directory.mkdir(parents=True, exist_ok=True)
            self._recording_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            self._recording_id += f'-{uuid.uuid4().hex[:8]}'
            path = self.directory / f'{self._recording_id}.jsonl'
            self._file = path.open('x', encoding='utf-8')
            self._started_at = _now()
            self._error = None
            try:
                self._write_locked({'type': 'recording_started', 'recording_id': self._recording_id,
                                    'started_at': self._started_at, 'schema_version': 1})
            except Exception:
                self._file.close()
                self._file = None
                self._started_at = None
                raise
            return self._status_locked()

    def append(self, snapshot):
        with self._lock:
            if self._file is None:
                return False
            self._write_locked({'type': 'telemetry', 'snapshot': snapshot})
            return True

    def _write_locked(self, value):
        self._file.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
        self._file.flush()

    def stop(self, reason='user'):
        with self._lock:
            if self._file is None:
                return self._status_locked()
            try:
                self._write_locked({'type': 'recording_stopped', 'recording_id': self._recording_id,
                                    'stopped_at': _now(), 'reason': reason})
            except Exception as error:
                self._error = str(error)
            finally:
                self._file.close()
                self._file = None
                self._started_at = None
            return self._status_locked()

    def fail(self, error):
        with self._lock:
            self._error = str(error)
            try:
                self.stop('write_error')
            except Exception:
                if self._file is not None:
                    self._file.close()
                    self._file = None
                    self._started_at = None

    def _latest_id_locked(self):
        if self._recording_id:
            return self._recording_id
        try:
            files = sorted(self.directory.glob('*.jsonl'), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return None
        for path in files:
            candidate = path.stem
            if RECORDING_ID.fullmatch(candidate) and not path.is_symlink():
                return candidate
        return None

    def _status_locked(self):
        latest = self._latest_id_locked()
        return {
            'recording': self._file is not None,
            'recording_id': self._recording_id if self._file is not None else None,
            'started_at': self._started_at if self._file is not None else None,
            'latest_recording_id': latest,
            'error': self._error,
        }

    def status(self):
        with self._lock:
            return self._status_locked()

    def log_path(self, recording_id):
        if not isinstance(recording_id, str) or not RECORDING_ID.fullmatch(recording_id):
            return None
        path = self.directory / f'{recording_id}.jsonl'
        if path.is_symlink() or not path.is_file():
            return None
        try:
            if path.resolve().parent != self.directory.resolve():
                return None
        except OSError:
            return None
        return path

    def gps_track(self, recording_id):
        """Return a temporary GPX file; the caller owns and must close it."""
        path = self.log_path(recording_id)
        if path is None:
            return None
        # Capture a complete, flushed prefix while append/stop are excluded.
        # All disk operations here run in the endpoint's worker thread.
        with self._lock:
            if self._file is not None and recording_id == self._recording_id:
                self._file.flush()
            stream = path.open('rb')
            try:
                boundary = os.fstat(stream.fileno()).st_size
            except BaseException:
                stream.close()
                raise
        output = None
        last_fix_key = None
        try:
            with stream:
                output = tempfile.TemporaryFile(mode='w+b', dir=self.directory)
                output.write((f'<?xml version="1.0" encoding="utf-8"?>\n'
                              f'<gpx xmlns="{GPX_NAMESPACE}" version="1.1" creator="OVRLand">'
                              f'<trk><name>{recording_id}</name><trkseg>').encode())
                remaining = boundary
                while remaining:
                    line = stream.readline(remaining)
                    if not line:
                        break
                    remaining -= len(line)
                    if not line.endswith(b'\n'):
                        continue
                    try:
                        row = json.loads(line)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
                    snapshot = row.get('snapshot') if isinstance(row, dict) else None
                    if not isinstance(snapshot, dict) or snapshot.get('source') != 'live':
                        continue
                    sources = snapshot.get('sources')
                    if not isinstance(sources, dict) or sources.get('gps') != 'live':
                        continue
                    gps_data = snapshot.get('gps')
                    gps_data = gps_data if isinstance(gps_data, dict) else {}
                    fix_key = gps_data.get('received_at') or gps_data.get('gps_time')
                    if fix_key and fix_key == last_fix_key:
                        continue
                    location = snapshot.get('location')
                    if not isinstance(location, dict):
                        continue
                    latitude, longitude = location.get('latitude'), location.get('longitude')
                    if (not _number(latitude) or not _number(longitude)
                            or not -90 <= latitude <= 90 or not -180 <= longitude <= 180):
                        continue
                    last_fix_key = fix_key
                    point = ElementTree.Element('trkpt', {
                        'lat': str(latitude), 'lon': str(longitude),
                    })
                    if location.get('altitude_source') == 'gps' and _number(location.get('altitude_m')):
                        ElementTree.SubElement(point, 'ele').text = str(location['altitude_m'])
                    point_time = gps_data.get('gps_time') or snapshot.get('timestamp')
                    if isinstance(point_time, str):
                        ElementTree.SubElement(point, 'time').text = point_time
                    output.write(ElementTree.tostring(point, encoding='utf-8'))
                output.write(b'</trkseg></trk></gpx>')
                output.seek(0)
            return output
        except BaseException:
            if output is not None:
                output.close()
            raise
