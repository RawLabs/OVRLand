"""Read-only raster MBTiles for maps served locally by the Pi."""
import math
import sqlite3
from contextlib import closing
from pathlib import Path


class OfflineMap:
    MIME = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'webp': 'image/webp'}

    def __init__(self, path):
        self.path = Path(path).resolve()

    def connect(self):
        return sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=2)

    def info(self):
        if not self.path.is_file():
            return {'available': False, 'message': 'No offline map installed on this Pi.'}
        try:
            with closing(self.connect()) as db:
                meta = dict(db.execute('SELECT name, value FROM metadata'))
                if meta.get('format') not in self.MIME:
                    return {'available': False, 'message': 'This map needs a raster MBTiles export (PNG, JPEG, or WebP).'}
                zooms = db.execute('SELECT MIN(zoom_level), MAX(zoom_level) FROM tiles').fetchone()
                if zooms[0] is None or not (0 <= zooms[0] <= zooms[1] <= 22):
                    raise ValueError('Invalid zoom range')
                bounds = [float(v) for v in meta.get('bounds', '-180,-85,180,85').split(',')]
                if len(bounds) != 4 or not all(math.isfinite(v) for v in bounds):
                    raise ValueError('Invalid bounds')
                west, south, east, north = bounds
                if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
                    raise ValueError('Invalid bounds')
                return {'available': True, 'name': meta.get('name', 'Offline map'),
                        'format': meta['format'], 'bounds': bounds,
                        'minzoom': zooms[0], 'maxzoom': zooms[1],
                        'attribution': meta.get('attribution', 'Map attribution not supplied in package')}
        except (sqlite3.Error, ValueError, TypeError):
            return {'available': False, 'message': 'Offline map could not be read. Check the map package.'}

    def tile(self, z, x, y):
        if not (0 <= z <= 22 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
            return None
        try:
            with closing(self.connect()) as db:
                fmt = db.execute("SELECT value FROM metadata WHERE name='format'").fetchone()
                if not fmt or fmt[0] not in self.MIME:
                    return None
                # Web maps request XYZ rows; MBTiles stores south-to-north TMS rows.
                row = db.execute('SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?',
                                 (z, x, 2 ** z - 1 - y)).fetchone()
                return (bytes(row[0]), self.MIME[fmt[0]]) if row else None
        except (sqlite3.Error, TypeError):
            return None
