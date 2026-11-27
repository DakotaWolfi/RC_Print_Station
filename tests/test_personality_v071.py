"""Personality stays out of the report path and runs without a provider."""
from contextlib import closing
import json
from pathlib import Path
import tempfile
from unittest import TestCase, skipIf
from unittest.mock import Mock

from benning_guide import Guide
from native_ui import NativeUI
from personality import report_counts
from slogan_store import SloganStore
from station import database, receipt, simulate
from test_hmi_native import APP, PanelSerial, Simulation
from test_native_ui import MemorySerial


class CacheTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"slogans.sqlite3"
        self.store=SloganStore(self.path)

    def test_real_milestones_and_distinct_passed_tests(self):
        reports=Path(self.temp.name)/"reports.sqlite3"
        docs=[
            {"source":"BENNING","record_id":12,"record":{"verdict":"bestanden"}},
            {"source":"BENNING","record_id":12,"record":{"verdict":"bestanden"}},
            {"source":"BENNING","record_id":13,"record":{"verdict":"nicht bestanden"}},
            {"source":"EXAMINATION"},
            simulate("DEV-1","Demo"),
        ]
        with closing(database(reports)) as conn, conn:
            conn.executemany("INSERT INTO reports(data) VALUES(?)",((json.dumps(doc),) for doc in docs))
            conn.execute("INSERT INTO reports(data) VALUES(?)",("malformed",))
        self.assertEqual(report_counts(reports),(4,1))
        self.assertEqual(self.store.milestones(4),0)
        for n in (10,50,100,500):
            self.assertEqual(self.store.milestones(n),n)
            self.assertEqual(SloganStore(self.path).milestones(n),0)
        self.assertEqual(SloganStore(self.path).pet(),1)
        self.assertEqual(self.store.pet(),2)
        self.assertNotIn(b"Streicheleinheiten",receipt(docs[-1]))


class BackendLanguageTests(TestCase):
    def test_resync_success_and_response_1a_logging(self):
        with tempfile.TemporaryDirectory() as scratch:
            temp=Path(scratch)
            ui=NativeUI(MemorySerial(),"printer",temp/"reports.sqlite3",
                        config_path=temp/"settings.json",tester_mode="simulation")
            self.addCleanup(ui.close)
            with self.assertLogs("native_ui",level="INFO") as logs:
                ui.handle(b"RC70:LANG")
                ui.handle(b"\x66\x00")
                ui.handle(b"\x1a")
                ui.handle(b"RC71:LOCALE:EN")
            self.assertEqual(ui.language,"en")
            self.assertEqual(json.loads((temp/"settings.json").read_text())["language"],"en")
            self.assertTrue(any("page resync" in line for line in logs.output))
            self.assertTrue(any("0x1a during station" in line for line in logs.output))
            self.assertTrue(any("confirmed station language" in line for line in logs.output))


@skipIf(Simulation is None,"Install requirements-build.txt")
class NativePersonalityTests(TestCase):
    def setUp(self):
        scratch=tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.rx=bytearray()
        self.sim=Simulation(APP,sending=self.rx.extend)
        self.ui=NativeUI(PanelSerial(self.sim),"printer",Path(scratch.name)/"reports.sqlite3",
                         config_path=Path(scratch.name)/"settings.json",tester_mode="simulation")
        self.addCleanup(self.ui.close)
        self.now=1000
        self.ui.personality.clock=lambda: self.now
        self.pump()

    def pump(self):
        for _ in range(16):
            frames=bytes(self.rx)
            self.rx.clear()
            if not frames:
                return
            self.ui.feed(frames)
        self.fail("UART did not settle")

    def press(self,name):
        obj=next(c for c in self.sim.components() if c.name==name)
        v=obj.values
        x,y=v["x"]+v["w"]//2,v["y"]+v["h"]//2
        self.assertEqual(self.sim.component_at(x,y),name)
        self.sim.press(name,x,y)

    def tap(self,name):
        self.press(name)
        self.sim.release()
        self.pump()

    def done(self):
        self.ui.personality.job[1].result(timeout=2)
        self.ui.personality.finish()

    def test_gesture_and_persistent_pet_then_long_press_read_only(self):
        for _ in range(4):
            self.tap("hLogo")
        self.assertEqual(self.sim.page,"home")
        self.tap("hLogo")
        self.assertEqual(self.sim.page,"pet")
        self.tap("bPet")
        self.done()
        self.assertEqual(self.ui.personality.store.counts()[0],1)
        self.assertEqual(self.sim.values()["tPets.txt"],"Streicheleinheiten: 1")
        self.tap("bBack")
        self.tap("hVersion")
        self.sim.advance(1100)
        self.pump()
        self.assertEqual(self.sim.page,"home")
        self.press("hVersion")
        self.sim.advance(1100)
        self.pump()
        self.assertEqual(self.sim.page,"engineering")
        self.assertNotIn("bChange",[obj.name for obj in self.sim.components()])
        self.sim.release()

    def test_frozen_home_clears_old_slogan_and_does_not_interrupt_guide(self):
        personality=self.ui.personality
        personality.tick()
        self.assertEqual(self.sim.values()["tSlogan.txt"],"")
        self.ui.workflow.guide=Guide()
        for _ in range(5):
            self.tap("hLogo")
        self.assertEqual(self.sim.page,"home")
