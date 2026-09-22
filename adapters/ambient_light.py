"""Durable, user-labelled reference readings for the APDS9960 light sensor."""
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


CONDITIONS = frozenset(('day', 'dusk', 'night'))


def brightness(rgb):
    """Return a relative luminance from raw RGB counts, or None when incomplete."""
    if (not isinstance(rgb, (tuple, list)) or len(rgb) != 3
            or not all(isinstance(value, (int, float)) and not isinstance(value, bool)
                       for value in rgb)):
        return None
    return round(.2126 * rgb[0] + .7152 * rgb[1] + .0722 * rgb[2], 1)


class AmbientLightCalibration:
    """Append and retrieve manually labelled sensor readings.

    The APDS9960 values are deliberately retained as raw counts.  Thresholds are
    chosen from these vehicle-specific references later; this class does not
    classify the light level or alter display brightness.
    """
    def __init__(self, path, max_entries=180):
        self.path = Path(path)
        self.max_entries = max_entries
        self._lock = threading.Lock()

    def entries(self):
        with self._lock:
            return self._read()

    def capture(self, condition, rgb, timestamp=None):
        if condition not in CONDITIONS:
            raise ValueError('Unknown ambient-light condition')
        brightness_raw = brightness(rgb)
        if brightness_raw is None:
            raise ValueError('A complete RGB reading is required')
        entry = {
            'condition': condition,
            'timestamp': (timestamp or datetime.now(timezone.utc)).isoformat(),
            'rgb': [round(value, 3) for value in rgb],
            'brightness_raw': brightness_raw,
        }
        with self._lock:
            entries = self._read()
            entries.append(entry)
            self._write(entries[-self.max_entries:])
        return entry

    def _read(self):
        try:
            document = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError):
            return []
        entries = document.get('entries') if isinstance(document, dict) else None
        return entries if isinstance(entries, list) else []

    def _write(self, entries):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        temporary.write_text(json.dumps({'schema_version': 1, 'entries': entries}, indent=2) + '\n')
        os.replace(temporary, self.path)
