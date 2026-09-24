"""Small cached lookups for current track metadata from curated radio providers."""
import json
import threading
import time
from urllib.request import Request, urlopen


class RadioMetadata:
    CACHE_SECONDS = 12
    FAILURE_CACHE_SECONDS = 5
    TIMEOUT_SECONDS = 4

    def __init__(self, presets):
        self._presets = {preset['id']: dict(preset) for preset in presets}
        self._cache = {}
        self._lock = threading.Lock()

    def current(self, stream_id):
        preset = self._presets.get(stream_id)
        if preset is None:
            return {'ok': False, 'status': 'unknown_station'}

        provider = preset.get('provider')
        if provider == 'Radio Paradise':
            result = self._cached(('radio_paradise', stream_id), self._radio_paradise)
        elif provider == 'KEXP':
            result = self._cached(('kexp', stream_id), self._kexp)
        elif provider == 'SomaFM' and preset.get('metadata_id'):
            channels = self._cached(('somafm', 'channels'), self._somafm_channels)
            result = channels.get(preset['metadata_id']) if channels else None
        else:
            return {'ok': False, 'status': 'metadata_unavailable'}

        if not result:
            return {'ok': False, 'status': 'metadata_unavailable'}
        return {'ok': True, 'title': result.get('title'),
                'artist': result.get('artist'), 'album': result.get('album')}

    def _cached(self, key, fetch):
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached[0] > now:
                return cached[1]

        try:
            value = fetch()
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            value = None

        lifetime = self.CACHE_SECONDS if value else self.FAILURE_CACHE_SECONDS
        with self._lock:
            self._cache[key] = (time.monotonic() + lifetime, value)
        return value

    def _get_json(self, url):
        request = Request(url, headers={'User-Agent': 'OVRLand/1.0'})
        with urlopen(request, timeout=self.TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode('utf-8'))

    def _radio_paradise(self):
        data = self._get_json('https://api.radioparadise.com/api/now_playing?chan=0')
        if not data.get('title'):
            return None
        return {'title': data['title'], 'artist': data.get('artist'),
                'album': data.get('album')}

    def _kexp(self):
        data = self._get_json('https://api.kexp.org/v2/plays/?limit=1')
        results = data.get('results') or []
        if not results:
            return None
        track = results[0]
        if not track.get('song'):
            return None
        return {'title': track['song'], 'artist': track.get('artist'),
                'album': track.get('album')}

    def _somafm_channels(self):
        data = self._get_json('https://api.somafm.com/channels.json')
        return {
            channel['id']: {'title': channel['lastPlaying'], 'artist': None}
            for channel in data.get('channels', [])
            if channel.get('id') and channel.get('lastPlaying')
        }
