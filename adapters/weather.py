"""Open-Meteo current conditions, refreshed off the telemetry request path."""
import json
import math
import threading
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen


WEATHER_CODES = {
    0: 'CLEAR', 1: 'MOSTLY CLEAR', 2: 'PARTLY CLOUDY', 3: 'CLOUDY',
    45: 'FOG', 48: 'RIME FOG', 51: 'LIGHT DRIZZLE', 53: 'DRIZZLE',
    55: 'HEAVY DRIZZLE', 56: 'FREEZING DRIZZLE', 57: 'FREEZING DRIZZLE',
    61: 'LIGHT RAIN', 63: 'RAIN', 65: 'HEAVY RAIN', 66: 'FREEZING RAIN',
    67: 'FREEZING RAIN', 71: 'LIGHT SNOW', 73: 'SNOW', 75: 'HEAVY SNOW',
    77: 'SNOW GRAINS', 80: 'RAIN SHOWERS', 81: 'RAIN SHOWERS',
    82: 'HEAVY RAIN SHOWERS', 85: 'SNOW SHOWERS', 86: 'HEAVY SNOW SHOWERS',
    95: 'THUNDERSTORM', 96: 'THUNDERSTORM / HAIL', 99: 'THUNDERSTORM / HAIL',
}


def _valid_location(latitude, longitude):
    return (isinstance(latitude, (int, float)) and math.isfinite(latitude)
            and -90 <= latitude <= 90
            and isinstance(longitude, (int, float)) and math.isfinite(longitude)
            and -180 <= longitude <= 180)


class Weather:
    def __init__(self, latitude, longitude, refresh_seconds=900):
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.refresh_event = threading.Event()
        self.thread = None
        self.latitude = latitude
        self.longitude = longitude
        self._refresh_latitude = latitude
        self._refresh_longitude = longitude
        self.location_source = 'default'
        self.refresh_seconds = refresh_seconds
        self.state = {'status': 'waiting', 'provider': 'Open-Meteo', 'location_source': 'default'}

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
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, daemon=True, name='weather-feed')
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.refresh_event.set()
        if self.thread:
            self.thread.join(timeout=9)

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def _fetch(self, latitude, longitude, location_source):
        query = urlencode({
            'latitude': latitude, 'longitude': longitude,
            'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,precipitation,rain,showers,snowfall,cloud_cover,pressure_msl',
            'hourly': 'temperature_2m,apparent_temperature,precipitation_probability,precipitation,rain,showers,snowfall,weather_code,wind_speed_10m,wind_direction_10m,wind_gusts_10m,cloud_cover,visibility,uv_index',
            'daily': 'weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_probability_max,precipitation_sum,rain_sum,snowfall_sum,sunrise,sunset,uv_index_max,wind_speed_10m_max,wind_gusts_10m_max,wind_direction_10m_dominant',
            'temperature_unit': 'celsius', 'wind_speed_unit': 'kmh',
            'timezone': 'auto', 'forecast_days': 2,
        })
        request = Request('https://api.open-meteo.com/v1/forecast?' + query,
                          headers={'User-Agent': 'OVRLand/1.0'})
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
        current = payload.get('current')
        if not isinstance(current, dict) or not isinstance(current.get('temperature_2m'), (int, float)):
            raise ValueError('Weather response has no current conditions')
        code = current.get('weather_code')
        hourly = payload.get('hourly') if isinstance(payload.get('hourly'), dict) else {}
        hourly_times = hourly.get('time') if isinstance(hourly.get('time'), list) else []
        hourly_fields = {
            'temperature_c': 'temperature_2m', 'feels_like_c': 'apparent_temperature',
            'precipitation_probability_pct': 'precipitation_probability',
            'precipitation_mm': 'precipitation', 'rain_mm': 'rain', 'showers_mm': 'showers',
            'snowfall_cm': 'snowfall', 'weather_code': 'weather_code',
            'wind_speed_kmh': 'wind_speed_10m', 'wind_direction_deg': 'wind_direction_10m',
            'wind_gust_kmh': 'wind_gusts_10m', 'cloud_cover_pct': 'cloud_cover',
            'visibility_m': 'visibility', 'uv_index': 'uv_index',
        }
        try:
            start_index = next((i for i, stamp in enumerate(hourly_times) if stamp >= current.get('time', '')), 0)
        except TypeError:
            start_index = 0
        current_hour = {}
        for field in ('visibility', 'uv_index'):
            values = hourly.get(field)
            if isinstance(values, list) and start_index < len(values):
                current_hour[field] = values[start_index]
        hourly_forecast = []
        for index in range(start_index, min(len(hourly_times), start_index + 12)):
            item = {'time': hourly_times[index]}
            for output, field in hourly_fields.items():
                values = hourly.get(field)
                item[output] = values[index] if isinstance(values, list) and index < len(values) else None
            hourly_forecast.append(item)

        daily = payload.get('daily') if isinstance(payload.get('daily'), dict) else {}
        daily_fields = {
            'weather_code': 'weather_code', 'high_c': 'temperature_2m_max',
            'low_c': 'temperature_2m_min', 'feels_like_high_c': 'apparent_temperature_max',
            'feels_like_low_c': 'apparent_temperature_min',
            'precipitation_probability_pct': 'precipitation_probability_max',
            'precipitation_mm': 'precipitation_sum', 'rain_mm': 'rain_sum',
            'snowfall_cm': 'snowfall_sum', 'sunrise': 'sunrise', 'sunset': 'sunset',
            'uv_index_max': 'uv_index_max', 'wind_speed_max_kmh': 'wind_speed_10m_max',
            'wind_gust_max_kmh': 'wind_gusts_10m_max',
            'wind_direction_deg': 'wind_direction_10m_dominant',
        }
        daily_times = daily.get('time') if isinstance(daily.get('time'), list) else []
        daily_forecast = []
        for index, stamp in enumerate(daily_times[:2]):
            item = {'date': stamp}
            for output, field in daily_fields.items():
                values = daily.get(field)
                item[output] = values[index] if isinstance(values, list) and index < len(values) else None
            daily_forecast.append(item)
        return {
            'status': 'live', 'provider': 'Open-Meteo',
            'location_source': location_source, 'latitude': latitude, 'longitude': longitude,
            'observed_at': current.get('time'),
            'temperature_c': current.get('temperature_2m'),
            'apparent_temperature_c': current.get('apparent_temperature'),
            'humidity_pct': current.get('relative_humidity_2m'),
            'cloud_cover_pct': current.get('cloud_cover'),
            'pressure_hpa': current.get('pressure_msl'),
            'visibility_m': current_hour.get('visibility'),
            'uv_index': current_hour.get('uv_index'),
            'weather_code': code,
            'summary': WEATHER_CODES.get(code, 'CONDITIONS'),
            'wind_speed_kmh': current.get('wind_speed_10m'),
            'wind_direction_deg': current.get('wind_direction_10m'),
            'wind_gust_kmh': current.get('wind_gusts_10m'),
            'precipitation_mm': current.get('precipitation'),
            'rain_mm': current.get('rain'), 'showers_mm': current.get('showers'),
            'snowfall_cm': current.get('snowfall'),
            'hourly_forecast': hourly_forecast,
            'daily_forecast': daily_forecast,
            'timezone': payload.get('timezone'),
            'timezone_abbreviation': payload.get('timezone_abbreviation'),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }

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
                                      'provider': 'Open-Meteo'}
                    delay = 60
            else:
                with self.lock:
                    self.state = {'status': 'waiting_location', 'provider': 'Open-Meteo',
                                  'location_source': source}
            self.refresh_event.wait(delay)
            if self.stop_event.is_set():
                break
