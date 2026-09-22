from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.maps import OfflineMap


class OfflineMapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'area.mbtiles'
        self.reader = OfflineMap(self.path)

    def make_map(self, fmt='png'):
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE metadata (name TEXT, value TEXT)')
            db.executemany('INSERT INTO metadata VALUES (?, ?)', [
                ('name', 'Test region'), ('format', fmt),
                ('bounds', '-120,40,-110,50'), ('attribution', 'Test map credit')])
            db.execute('CREATE TABLE tiles (zoom_level INTEGER, tile_column INTEGER, tile_row INTEGER, tile_data BLOB)')
            db.execute('INSERT INTO tiles VALUES (2, 1, 3, ?)', (b'northern tile',))

    def test_missing_file_is_not_created(self):
        self.assertFalse(self.reader.info()['available'])
        self.assertIsNone(self.reader.tile(0, 0, 0))
        self.assertFalse(self.path.exists())

    def test_metadata_and_xyz_to_tms(self):
        self.make_map()
        info = self.reader.info()
        self.assertTrue(info['available'])
        self.assertEqual(info['bounds'], [-120, 40, -110, 50])
        self.assertEqual(info['minzoom'], 2)
        self.assertEqual(self.reader.tile(2, 1, 0), (b'northern tile', 'image/png'))
        self.assertIsNone(self.reader.tile(2, 1, 3))
        for coords in [(-1, 0, 0), (23, 0, 0), (2, -1, 0), (2, 4, 0), (2, 0, 4)]:
            self.assertIsNone(self.reader.tile(*coords))

    def test_vector_and_corrupt_packages_are_unavailable(self):
        self.make_map('pbf')
        self.assertFalse(self.reader.info()['available'])
        self.assertIsNone(self.reader.tile(2, 1, 0))
        self.path.write_bytes(b'not a database')
        self.assertFalse(self.reader.info()['available'])
        self.assertIsNone(self.reader.tile(2, 1, 0))

    def test_invalid_bounds_are_unavailable(self):
        self.make_map()
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute("UPDATE metadata SET value='nan,0,1,1' WHERE name='bounds'")
        self.assertFalse(self.reader.info()['available'])

    def test_tile_response_and_missing_tile(self):
        self.make_map()
        import app
        with patch.object(app, 'offline_map', self.reader):
            self.assertTrue(app.offline_map_info()['available'])
            response = app.offline_map_tile(2, 1, 0)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.body, b'northern tile')
            self.assertEqual(response.media_type, 'image/png')
            self.assertEqual(app.offline_map_tile(2, 1, 3).status_code, 404)
