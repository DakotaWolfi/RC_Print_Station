import unittest
import tempfile
from unittest.mock import patch
from pathlib import Path
from station import simulate, receipt, database

class StationTests(unittest.TestCase):
    def test_simulation(self):
        r = simulate("T1", "Lamp")
        self.assertEqual(r["verdict"], "NOT TESTED")
        self.assertEqual(r["source"], "SIMULATOR")
    @patch('station.receipt_settings', return_value={'graphic': True, 'feed_mm':45})
    def test_receipt(self, settings):
        data = receipt(simulate("T1", "Lamp"))
        self.assertIn(b"SIMULATION ONLY", data)
        self.assertIn(b"NOT TESTED", data)
        self.assertIn(b"\x1b\x4a\xf0\x1bJ\x78\x1dV\x00", data)
        self.assertIn("Gerät".encode("cp850"), data)
        self.assertIn(b"\x1dv0\x00\x3f\x00\xa8\x00", data)
    @patch('station.receipt_settings', return_value={'graphic': False, 'feed_mm':45})
    def test_control_characters(self, settings):
        self.assertNotIn(b"\x1bX", receipt(simulate("T1", "\x1bX")))
    def test_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            with database(Path(tmp) / "test.db") as db:
                db.execute("INSERT INTO reports(data) VALUES (?)", ("demo",))
                self.assertEqual(db.execute("SELECT data FROM reports").fetchone()[0], "demo")
