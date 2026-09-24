"""Alberta 511 winter-road reports for the nearest reported road segment."""
import json
import math
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


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
        self.state = {'status': 'not_configured' if not api_key else 'waiting',
                      'provider': '511 Alberta', 'location_source': 'default'}

    def set_location(self, latitude, longitude, source):
        if not _valid_location(latitude, longitude):
            return
        with self.lock:
            moved = (source != self.location_source or self._refresh_latitude is None
                     or self._refresh_longitude is None
                     or abs(self._refresh_latitude - latitude) > .03
                     or abs(self._refresh_longitude - longitude) > .03)
            self.latitude, self.longitude = latitude, longitude
            self.location_source = source
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
            return dict(self.state)

    def _fetch(self, latitude, longitude, source):
        query = urlencode({'key': self.api_key, 'format': 'json', 'lang': 'en'})
        request = Request('https://511.alberta.ca/api/v3/get/winterroads?' + query,
                          headers={'User-Agent': 'OVRLand/1.0'})
        with urlopen(request, timeout=10) as response:
            payload = json.load(response)
        if isinstance(payload, dict):
            records = payload.get('WinterRoads') or payload.get('winterroads') or payload.get('data') or []
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
                try:
                    result = self._fetch(latitude, longitude, source)
                    with self.lock:
                        if (latitude, longitude, source) == (self.latitude, self.longitude, self.location_source):
                            self.state = result
                except Exception:
                    with self.lock:
                        previous = self.state
                        self.state = {**previous, 'status': 'stale' if previous.get('updated_at') else 'unavailable',
                                      'provider': '511 Alberta'}
                    delay = 60
            self.refresh_event.wait(delay)
            if self.stop_event.is_set():
                break
