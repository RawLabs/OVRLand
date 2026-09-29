"""Alberta 511 winter-road reports for the nearest reported road segment."""
import json
import logging
import math
import ssl
import threading
import time
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


logger = logging.getLogger(__name__)


def _same_location(lat1, lon1, source1, lat2, lon2, source2):
    """Use the refresh threshold when deciding whether a result is still useful."""
    return (source1 == source2 and _valid_location(lat1, lon1)
            and _valid_location(lat2, lon2)
            and abs(lat1 - lat2) <= .03 and abs(lon1 - lon2) <= .03)


def _fetch_error(error):
    # Never expose exception messages or request URLs: they may contain the API key.
    if isinstance(error, HTTPError):
        return {'kind': 'http', 'http_status': error.code,
                'message': f'511 returned HTTP {error.code}'}
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, TimeoutError):
        return {'kind': 'timeout', 'message': '511 request timed out'}
    if isinstance(reason, ssl.SSLError):
        return {'kind': 'tls', 'message': '511 secure connection failed'}
    if isinstance(error, URLError):
        return {'kind': 'network', 'message': 'Could not connect to 511'}
    if isinstance(error, (ValueError, UnicodeError)):
        return {'kind': 'response', 'message': '511 response could not be read'}
    return {'kind': 'internal', 'message': 'Road feed processing failed'}


def _valid_location(latitude, longitude):
    return (isinstance(latitude, (int, float)) and math.isfinite(latitude)
            and -90 <= latitude <= 90
            and isinstance(longitude, (int, float)) and math.isfinite(longitude)
            and -180 <= longitude <= 180)


def _decode_polyline(encoded):
    points, lat, lon, index = [], 0, 0, 0
    while index < len(encoded):
        values = []
        for _ in range(2):
            result, shift = 0, 0
            while index < len(encoded):
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1f) << shift
                shift += 5
                if byte < 0x20:
                    break
            values.append(~(result >> 1) if result & 1 else result >> 1)
        lat += values[0]
        lon += values[1]
        points.append((lat / 1e5, lon / 1e5))
    return points


def _distance_km(lat1, lon1, lat2, lon2):
    radius = 6371
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da, db = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    value = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(db / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(max(0, 1 - value)))


def _field(record, *names):
    for name in names:
        if name in record:
            return record[name]
    return None


class Alberta511:
    def __init__(self, api_key, latitude, longitude, refresh_seconds=300, radius_km=35):
        self.api_key = api_key
        self.latitude, self.longitude = latitude, longitude
        self._refresh_latitude, self._refresh_longitude = latitude, longitude
        self.location_source = 'default'
        self.refresh_seconds = refresh_seconds
        self.radius_km = radius_km
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.thread = None
        self.diagnostics = {'phase': 'not_configured' if not api_key else 'not_started',
                            'attempts': 0, 'failures': 0, 'discarded_results': 0,
                            'last_attempt_at': None, 'last_fetch_succeeded_at': None,
                            'last_fetch_seconds': None, 'last_error': None,
                            'next_attempt_at': None}
        self.state = {'status': 'not_configured' if not api_key else 'waiting',
                      'provider': '511 Alberta', 'location_source': 'default'}

    def set_location(self, latitude, longitude, source):
        if not _valid_location(latitude, longitude):
            return
        with self.lock:
            moved = not _same_location(
                latitude, longitude, source,
                self._refresh_latitude, self._refresh_longitude, self.location_source)
            self.latitude, self.longitude = latitude, longitude
            self.location_source = source
            if moved and self.state.get('status') == 'live':
                # Keep the old report and its provenance, but never present it
                # as current while a materially different location is pending.
                self.state = {**self.state, 'status': 'stale'}
        if moved:
            self.refresh_event.set()

    def start(self):
        if not self.api_key:
            return
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='alberta-511-feed')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.refresh_event.set()
        if self.thread:
            self.thread.join(timeout=11)

    def snapshot(self):
        with self.lock:
            diagnostics = dict(self.diagnostics)
            if diagnostics['last_error'] is not None:
                diagnostics['last_error'] = dict(diagnostics['last_error'])
            diagnostics['worker_alive'] = bool(self.thread and self.thread.is_alive())
            return {**self.state, 'diagnostics': diagnostics}

    def _fetch(self, latitude, longitude, source):
        query = urlencode({'key': self.api_key, 'format': 'json', 'lang': 'en'})
        request = Request('https://511.alberta.ca/api/v3/get/winterroads?' + query,
                          headers={'User-Agent': 'OVRLand/1.0'})
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        if isinstance(payload, dict):
            records = _field(payload, 'WinterRoads', 'winterroads', 'data')
        else:
            records = payload
        if not isinstance(records, list):
            raise ValueError('511 response has no road condition list')
        nearest, nearest_distance = None, None
        for item in records:
            if not isinstance(item, dict):
                continue
            encoded = _field(item, 'EncodedPolyline', 'encodedPolyline', 'encoded_polyline')
            lines = encoded if isinstance(encoded, list) else [encoded]
            distance = None
            for line in lines:
                if not isinstance(line, str) or not line:
                    continue
                try:
                    for point_lat, point_lon in _decode_polyline(line):
                        point_distance = _distance_km(latitude, longitude, point_lat, point_lon)
                        distance = point_distance if distance is None else min(distance, point_distance)
                except (IndexError, ValueError):
                    continue
            if distance is not None and (nearest_distance is None or distance < nearest_distance):
                nearest, nearest_distance = item, distance
        result = {'status': 'live', 'provider': '511 Alberta', 'location_source': source,
                  'latitude': latitude, 'longitude': longitude,
                  'updated_at': datetime.now(timezone.utc).isoformat(),
                  'radius_km': self.radius_km}
        if nearest is None or nearest_distance > self.radius_km:
            result.update({'condition': None, 'roadway': None, 'area': None,
                           'distance_km': round(nearest_distance, 1) if nearest_distance is not None else None,
                           'report_status': 'no_report_nearby'})
            return result
        primary = _field(nearest, 'Primary Condition', 'PrimaryCondition', 'primaryCondition')
        secondary = _field(nearest, 'Secondary Conditions', 'SecondaryConditions', 'secondaryConditions')
        result.update({
            'condition': primary,
            'secondary_conditions': secondary if isinstance(secondary, (str, list)) else None,
            'visibility': _field(nearest, 'Visibility', 'visibility'),
            'roadway': _field(nearest, 'RoadwayName', 'roadwayName'),
            'location_description': _field(nearest, 'LocationDescription', 'locationDescription'),
            'area': _field(nearest, 'AreaName', 'areaName'),
            'distance_km': round(nearest_distance, 1),
            'last_updated': _field(nearest, 'LastUpdated', 'lastUpdated'),
            'report_status': 'reported',
        })
        return result

    def _run(self):
        while not self.stop_event.is_set():
            self.refresh_event.clear()
            delay = self.refresh_seconds
            with self.lock:
                latitude, longitude = self.latitude, self.longitude
                source = self.location_source
                self._refresh_latitude, self._refresh_longitude = latitude, longitude
            if self.stop_event.is_set():
                break
            if _valid_location(latitude, longitude):
                started = time.monotonic()
                with self.lock:
                    self.diagnostics.update(phase='fetching',
                                            last_attempt_at=datetime.now(timezone.utc).isoformat(),
                                            next_attempt_at=None)
                    self.diagnostics['attempts'] += 1
                try:
                    result = self._fetch(latitude, longitude, source)
                    with self.lock:
                        self.diagnostics.update(
                            last_fetch_succeeded_at=datetime.now(timezone.utc).isoformat(),
                            last_error=None, phase='idle')
                        if _same_location(latitude, longitude, source,
                                          self.latitude, self.longitude, self.location_source):
                            self.state = result
                        else:
                            self.diagnostics['discarded_results'] += 1
                            self.diagnostics['phase'] = 'location_changed'
                            # A material move during the fetch needs a fresh result now.
                            self.refresh_event.set()
                            delay = 0
                    if delay == 0:
                        logger.warning('511 response discarded after location changed; fetching again')
                except Exception as error:
                    detail = _fetch_error(error)
                    with self.lock:
                        previous = self.state
                        self.state = {**previous, 'status': 'stale' if previous.get('updated_at') else 'unavailable',
                                      'provider': '511 Alberta'}
                        self.diagnostics.update(phase='retry_wait', last_error=detail)
                        self.diagnostics['failures'] += 1
                    logger.warning('511 fetch failed: %s; retrying in 60 seconds', detail['message'])
                    delay = 60
                finally:
                    with self.lock:
                        self.diagnostics['last_fetch_seconds'] = round(time.monotonic() - started, 3)
            else:
                with self.lock:
                    self.state = {**self.state, 'status': 'waiting_location'}
                    self.diagnostics['phase'] = 'waiting_location'
            with self.lock:
                self.diagnostics['next_attempt_at'] = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            self.refresh_event.wait(delay)
            if self.stop_event.is_set():
                break
        with self.lock:
            self.diagnostics.update(phase='stopped', next_attempt_at=None)
