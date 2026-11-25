import unittest
import tempfile
from pathlib import Path
from station import simulate, receipt, database

class StationTests(unittest.TestCase):
    def test_simulation(self):
        r = simulate("T1", "Lamp")
        self.assertEqual(r["verdict"], "NOT TESTED")
        self.assertEqual(r["source"], "SIMULATOR")
    def test_receipt(self):
        data = receipt(simulate("T1", "Lamp"))
        self.assertIn(b"SIMULATION ONLY", data)
        self.assertIn(b"NOT TESTED", data)
    def test_control_characters(self):
        self.assertNotIn(b"\x1bX", receipt(simulate("T1", "\x1bX")))
    def test_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            with database(Path(tmp) / "test.db") as db:
                db.execute("INSERT INTO reports(data) VALUES (?)", ("demo",))
                self.assertEqual(db.execute("SELECT data FROM reports").fetchone()[0], "demo")
