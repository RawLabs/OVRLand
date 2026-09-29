"""Service-owned JSONL telemetry recordings and GPS-only GPX export."""
import json
import errno
import math
import os
import shutil
import tempfile
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


RECORDING_ID = re.compile(r"^\d{8}T\d{6}Z-[0-9a-f]{8}$")
GPX_NAMESPACE = "http://www.topografix.com/GPX/1/1"
MAX_LOG_ROW_BYTES = 4 * 1024 * 1024


def _now():
    return datetime.now(timezone.utc).isoformat()


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _seconds(stamp):
    if not isinstance(stamp, str):
        return None
    try:
        return datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
    except ValueError:
        return None


def _distance_km(first, second):
    lat1, lon1 = first
    lat2, lon2 = second
    a = (math.sin(math.radians(lat2 - lat1) / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 12742 * math.atan2(math.sqrt(a), math.sqrt(max(0, 1 - a)))


def _new_summary():
    return {'distance_km': 0.0, 'moving_seconds': 0.0, 'fix_count': 0,
            'last_fix_at': None, 'started_at': None, 'stopped_at': None,
            '_last_point': None, '_last_time': None, '_last_fix_key': None}


def _add_fix(summary, snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('source') != 'live':
        return
    if not isinstance(snapshot.get('sources'), dict) or snapshot['sources'].get('gps') != 'live':
        return
    gps = snapshot.get('gps') if isinstance(snapshot.get('gps'), dict) else {}
    location = snapshot.get('location') if isinstance(snapshot.get('location'), dict) else {}
    lat, lon = location.get('latitude'), location.get('longitude')
    if not (_number(lat) and _number(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return
    fix_key = gps.get('received_at') or gps.get('gps_time')
    if fix_key is not None and fix_key == summary['_last_fix_key']:
        return
    stamp = gps.get('gps_time') or snapshot.get('timestamp')
    seconds = _seconds(stamp)
    point = (lat, lon)
    previous, previous_time = summary['_last_point'], summary['_last_time']
    use_as_baseline = True
    if previous is not None and seconds is not None and previous_time is not None:
        elapsed = seconds - previous_time
        if 0 < elapsed <= 60:
            distance = _distance_km(previous, point)
            # Reject GPS jumps; a truck cannot travel at this speed.
            speed_kmh = distance / elapsed * 3600
            if speed_kmh <= 180:
                if speed_kmh > 1.8:
                    summary['distance_km'] += distance
                    summary['moving_seconds'] += elapsed
            else:
                use_as_baseline = False
    summary['fix_count'] += 1
    summary['last_fix_at'] = stamp if isinstance(stamp, str) else None
    if use_as_baseline:
        summary['_last_point'], summary['_last_time'] = point, seconds
    summary['_last_fix_key'] = fix_key


def _public_summary(summary):
    return {key: value for key, value in summary.items() if not key.startswith('_')}


class _ExportStream:
    """Keep the single-export permit until the client closes its response."""
    def __init__(self, stream, permit):
        self.stream = stream
        self.permit = permit
        self.closed = False

    def read(self, size=-1):
        return self.stream.read(size)

    def seek(self, offset, whence=0):
        return self.stream.seek(offset, whence)

    def tell(self):
        return self.stream.tell()

    def seekable(self):
        return self.stream.seekable()

    def readable(self):
        return self.stream.readable()

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.stream.close()
        finally:
            self.permit.release()


class Recording:
    """Write complete telemetry snapshots until stopped or the service exits."""

    def __init__(self, directory, min_free_bytes=256 * 1024 * 1024,
                 sync_interval_seconds=5, space_check_seconds=30):
        self.directory = Path(directory).expanduser()
        self.min_free_bytes = max(0, int(min_free_bytes))
        self.sync_interval_seconds = max(1, float(sync_interval_seconds))
        self.space_check_seconds = max(1, float(space_check_seconds))
        self._lock = threading.RLock()
        self._export_lock = threading.Lock()
        self._file = None
        self._recording_id = None
        self._started_at = None
        self._error = None
        self._summary = None
        self._summary_id = None
        self._last_sync = 0.0
        self._last_space_check = 0.0

    def is_recording(self):
        with self._lock:
            return self._file is not None

    def start(self):
        with self._lock:
            if self._file is not None:
                return self._status_locked()
            self.directory.mkdir(parents=True, exist_ok=True)
            self._check_free_space_locked(0)
            self._recording_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
            self._recording_id += f'-{uuid.uuid4().hex[:8]}'
            path = self.directory / f'{self._recording_id}.jsonl'
            self._file = path.open('x', encoding='utf-8')
            self._started_at = _now()
            self._error = None
            self._summary = _new_summary()
            self._summary['started_at'] = self._started_at
            self._summary_id = self._recording_id
            try:
                self._write_locked({'type': 'recording_started', 'recording_id': self._recording_id,
                                    'started_at': self._started_at, 'schema_version': 1})
                self._sync_locked()
            except Exception as error:
                file = self._file
                self._file = None
                self._started_at = None
                self._error = str(error)
                if file is not None:
                    try:
                        file.close()
                    except Exception as close_error:
                        self._error += f'; close failed: {close_error}'
                raise
            return self._status_locked()

    def append(self, snapshot):
        with self._lock:
            if self._file is None:
                return False
            self._write_locked({'type': 'telemetry', 'snapshot': snapshot})
            _add_fix(self._summary, snapshot)
            now = time.monotonic()
            if now - self._last_space_check >= self.space_check_seconds:
                self._last_space_check = now
                self._check_free_space_locked(0)
            if now - self._last_sync >= self.sync_interval_seconds:
                self._sync_locked()
            return True

    def _write_locked(self, value):
        self._file.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
        self._file.flush()

    def _sync_locked(self):
        if self._file is None:
            return
        os.fsync(self._file.fileno())
        self._last_sync = time.monotonic()

    def _check_free_space_locked(self, additional_bytes=0):
        free = shutil.disk_usage(self.directory).free
        if free < self.min_free_bytes + additional_bytes:
            raise OSError(errno.ENOSPC, 'recording storage reserve would be exceeded')

    def stop(self, reason='user'):
        with self._lock:
            if self._file is None:
                return self._status_locked()
            try:
                if self._summary is not None:
                    self._summary['stopped_at'] = _now()
                self._write_locked({'type': 'recording_stopped', 'recording_id': self._recording_id,
                                    'stopped_at': self._summary['stopped_at'], 'reason': reason})
                self._sync_locked()
            except Exception as error:
                self._error = f'{self._error}; {error}' if self._error else str(error)
            finally:
                file = self._file
                self._file = None
                self._started_at = None
                if file is not None:
                    try:
                        file.close()
                    except Exception as error:
                        self._error = f'{self._error}; close failed: {error}' if self._error else f'close failed: {error}'
            return self._status_locked()

    def fail(self, error):
        with self._lock:
            original = str(error)
            self._error = f'{self._error}; {original}' if self._error else original
            self.stop('write_error')

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
            'summary': _public_summary(self._summary) if self._summary is not None else None,
        }

    def _load_summary_locked(self, recording_id):
        summary = _new_summary()
        summary['recovery_warning'] = None
        saw_start = saw_stop = False
        path = self.log_path(recording_id)
        if path is None:
            return summary
        try:
            with path.open('rb') as stream:
                while raw_line := stream.readline(MAX_LOG_ROW_BYTES + 1):
                    if len(raw_line) > MAX_LOG_ROW_BYTES:
                        summary['recovery_warning'] = 'A log row exceeded the recovery size limit.'
                        while raw_line and not raw_line.endswith(b'\n'):
                            raw_line = stream.readline(MAX_LOG_ROW_BYTES + 1)
                        continue
                    try:
                        row = json.loads(raw_line.decode('utf-8'))
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        summary['recovery_warning'] = 'Some log rows were corrupt or incomplete.'
                        continue
                    if not isinstance(row, dict):
                        summary['recovery_warning'] = 'Some log rows were not valid objects.'
                        continue
                    if row.get('type') == 'recording_started':
                        saw_start = True
                        summary['started_at'] = row.get('started_at')
                    elif row.get('type') == 'recording_stopped':
                        saw_stop = True
                        summary['stopped_at'] = row.get('stopped_at')
                    elif row.get('type') == 'telemetry':
                        _add_fix(summary, row.get('snapshot'))
        except OSError:
            summary['recovery_warning'] = 'The latest log could not be read.'
        if saw_start and not saw_stop and summary['recovery_warning'] is None:
            summary['recovery_warning'] = 'Recording ended without a clean stop marker.'
        return summary

    def status(self):
        with self._lock:
            latest = self._latest_id_locked()
            cached = latest == self._summary_id
            if cached:
                return self._status_locked()
        recovered = self._load_summary_locked(latest) if latest else None
        with self._lock:
            if latest == self._latest_id_locked() and latest != self._summary_id:
                self._summary = recovered
                self._summary_id = latest
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

    def log_snapshot(self, recording_id):
        """Open one stable prefix for download; caller owns the binary stream."""
        path = self.log_path(recording_id)
        if path is None:
            return None
        with self._lock:
            if self._file is not None and recording_id == self._recording_id:
                self._file.flush()
            stream = path.open('rb')
            try:
                return stream, os.fstat(stream.fileno()).st_size
            except BaseException:
                stream.close()
                raise

    def export_all(self):
        """Build a ZIP snapshot of every saved log, including the active log prefix."""
        if not self._export_lock.acquire(blocking=False):
            raise BlockingIOError(errno.EBUSY, 'another recording export is in progress')
        output = None
        transfer_permit = False
        try:
            with self._lock:
                if self._file is not None:
                    self._file.flush()
                sources = []
                for path in sorted(self.directory.glob('*.jsonl')):
                    recording_id = path.stem
                    if (not RECORDING_ID.fullmatch(recording_id) or path.is_symlink()
                            or not path.is_file()):
                        continue
                    sources.append((recording_id, path, path.stat().st_size))
            if not sources:
                return None
            required = sum(boundary for _, _, boundary in sources)
            # ZIP directory/header overhead plus a margin for the end record.
            required += 65536 + 1024 * len(sources)
            with self._lock:
                self._check_free_space_locked(required)
            output = tempfile.TemporaryFile(mode='w+b', dir=self.directory)
            with zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_STORED,
                                 allowZip64=True) as archive:
                for recording_id, path, boundary in sources:
                    with path.open('rb') as source:
                        with archive.open(f'ovrland-{recording_id}.jsonl', mode='w') as target:
                            remaining = boundary
                            while remaining:
                                chunk = source.read(min(64 * 1024, remaining))
                                if not chunk:
                                    break
                                target.write(chunk)
                                remaining -= len(chunk)
            output.seek(0)
            result = _ExportStream(output, self._export_lock)
            output = None
            transfer_permit = True
            return result
        finally:
            if output is not None:
                output.close()
            if not transfer_permit:
                self._export_lock.release()

    def check_export(self):
        """Check whether a ZIP export can begin without retaining descriptors."""
        if not self._export_lock.acquire(blocking=False):
            raise BlockingIOError(errno.EBUSY, 'another recording export is in progress')
        try:
            with self._lock:
                sources = [(path, path.stat().st_size) for path in self.directory.glob('*.jsonl')
                           if RECORDING_ID.fullmatch(path.stem) and not path.is_symlink()
                           and path.is_file()]
                if not sources:
                    return False
                required = sum(size for _, size in sources) + 65536 + 1024 * len(sources)
                self._check_free_space_locked(required)
                return True
        finally:
            self._export_lock.release()

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
                    line = stream.readline(min(remaining, MAX_LOG_ROW_BYTES + 1))
                    if not line:
                        break
                    remaining -= len(line)
                    if len(line) > MAX_LOG_ROW_BYTES:
                        # Drain an oversized row in bounded chunks without
                        # parsing or retaining it.
                        while not line.endswith(b'\n') and remaining:
                            line = stream.readline(min(remaining, MAX_LOG_ROW_BYTES + 1))
                            remaining -= len(line)
                        continue
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
