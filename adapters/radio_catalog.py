"""Curated browser-playable internet radio station catalog."""


class RadioCatalog:
    """Expose only station metadata and a direct URL supported by browser audio."""

    PRIVATE_URL_FIELDS = {'primary_url', 'fallback_url', 'low_bandwidth_url', 'browser_url'}

    def __init__(self, presets):
        if not isinstance(presets, list):
            raise ValueError('Radio presets must be a list')
        self._presets = []
        seen = set()
        for preset in presets:
            if not isinstance(preset, dict):
                raise ValueError('Each radio preset must be an object')
            station = dict(preset)
            station_id = station.get('id')
            if not isinstance(station_id, str) or not station_id or station_id in seen:
                raise ValueError('Radio preset ids must be unique non-empty strings')
            if not all(isinstance(station.get(key), str) and station[key]
                       for key in ('display_name', 'primary_url')):
                raise ValueError(f'Radio preset {station_id!r} is missing playback metadata')
            seen.add(station_id)
            self._presets.append(station)

    def streams(self):
        """Return the public station list with a direct browser-compatible URL."""
        stations = []
        for preset in self._presets:
            public = {key: value for key, value in preset.items()
                      if key not in self.PRIVATE_URL_FIELDS}
            public['playback_url'] = (preset.get('browser_url') or preset.get('fallback_url')
                                      or preset['primary_url'])
            public['name'] = preset['display_name']
            public['favorite'] = False
            stations.append(public)
        return {'ok': True, 'streams': stations}
