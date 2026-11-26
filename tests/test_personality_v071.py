"""Personality stays out of the report path and runs without a provider."""
from contextlib import closing
from io import BytesIO
import json
from pathlib import Path
import tempfile
from unittest import TestCase, skipIf
from unittest.mock import Mock
from urllib.error import URLError

from benning_guide import Guide
from native_ui import NativeUI
from panel_text import fit
from personality import ROTATE_SECONDS, report_counts
from slogan_store import LIMIT, OFFLINE, SloganStore, utc_day
from slogan_worker import BATCH, SAFE_PAIRS, local, openai, replenish, validate
from station import database, receipt, simulate
from test_hmi_native import APP, PanelSerial, Simulation
from test_native_ui import MemorySerial


def reply_payload(keys):
    return {"pairs":[{"first":a,"last":b} for a,b in keys]}


class CacheTests(TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/"slogans.sqlite3"
        self.store=SloganStore(self.path)

    def test_curated_and_safe_model_text_fit_whole_words(self):
        self.assertGreaterEqual(len(OFFLINE),100)
        self.assertEqual(len({pair[0] for pair in OFFLINE}),len(OFFLINE))
        self.assertEqual(len({pair[1] for pair in OFFLINE}),len(OFFLINE))
        for pair in (*OFFLINE,*SAFE_PAIRS.values()):
            for text in pair:
                self.assertLessEqual(len(text),LIMIT)
                self.assertEqual(fit("home","tSlogan",text,LIMIT).split(),text.split(),text)
        values=[SloganStore(self.path).next() for _ in range(len(OFFLINE))]
        self.assertEqual(set(values),set(OFFLINE))
        self.assertEqual(SloganStore(self.path).next(),values[0])

    def test_reject_duplicates_foreign_text_and_non_integer_indices(self):
        rows=[{"first":0,"last":0},{"first":0,"last":0},{"first":"bad","last":1},
              {"first":-1,"last":0},{"first":1,"last":True},
              {"first":1,"last":1,"de":"Unreviewed content"}]
        self.assertEqual(validate(json.dumps({"pairs":rows}),len(rows)),[SAFE_PAIRS[(0,0)]])
        self.store.add([SAFE_PAIRS[(0,0)]]*2,"openai")
        self.assertEqual(self.store.remaining(),1)
        self.assertEqual(SloganStore(self.path).next(),SAFE_PAIRS[(0,0)])
        self.store.add([SAFE_PAIRS[(0,0)]],"openai")
        self.assertEqual(self.store.remaining(),0)
        self.assertIn(self.store.next(),OFFLINE)

    def test_openai_static_only_is_bounded_and_accounts_for_failure(self):
        batch=reply_payload(list(SAFE_PAIRS)[:BATCH])
        calls=[]
        def request(req,timeout):
            calls.append(req)
            self.assertEqual(req.full_url,"https://api.openai.com/v1/responses")
            self.assertEqual(timeout,15)
            payload=json.loads(req.data)
            self.assertIs(payload["store"],False)
            self.assertIn("exactly 50",payload["input"])
            self.assertEqual(payload["model"],"unit-test-model")
            self.assertNotIn("example-secret",req.data.decode())
            data={"status":"completed","usage":{"total_tokens":1450},
                  "output":[{"type":"message","content":[{"type":"output_text","text":json.dumps(batch)}]}]}
            return BytesIO(json.dumps(data).encode())
        self.assertEqual(len(openai(self.store,"example-secret","unit-test-model",2,40000,request=request)),50)
        self.assertEqual(self.store.counts()[1],(1,1450,0))
        self.assertEqual(openai(self.store,"key","model",2,1000,request=request),[])
        fail=Mock(side_effect=URLError("offline"))
        with self.assertRaises(URLError):
            openai(self.store,"key","unit-test-model",2,40000,request=fail)
        requests,tokens,reserve=self.store.counts()[1]
        self.assertEqual((requests,tokens),(2,1450))
        self.assertGreater(reserve,0)
        self.assertEqual(openai(self.store,"key","model",2,40000,request=request),[])
        self.assertEqual(len(calls),1)
        self.assertIn(self.store.next(),OFFLINE)
        self.assertEqual(utc_day().count("-"),2)

    def test_disabled_and_no_key_do_not_touch_cache(self):
        replenish(self.store,{})
        replenish(self.store,{"FMI_SLOGAN_PROVIDER":"openai"})
        self.assertFalse(self.path.exists())

    def test_local_runtime_is_isolated_and_timeboxed(self):
        good=reply_payload(list(SAFE_PAIRS)[:8])
        def run(args,**opts):
            self.assertEqual(args[:3],["nice","-n","15"])
            self.assertIn("--grammar",args)
            self.assertEqual(args[args.index("--threads")+1],"1")
            self.assertEqual(opts["timeout"],11)
            self.assertNotIn("OPENAI_API_KEY",opts["env"])
            opts["stdout"].write(json.dumps(good).encode())
        self.assertEqual(len(local("/fixtures/llama-cli","/fixtures/model.gguf",11,runner=run)),8)

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

    def test_five_minute_rotation_and_active_guide_suppression(self):
        personality=self.ui.personality
        personality.tick()
        self.done()
        self.assertEqual(personality.next_rotation,self.now+ROTATE_SECONDS)
        first=personality.slogan
        self.now+=ROTATE_SECONDS
        self.ui.workflow.guide=Guide()
        shown=self.sim.values()["tSlogan.txt"]
        for _ in range(5):
            self.tap("hLogo")
        self.assertEqual(self.sim.page,"home")
        personality.tick()
        if personality.job:
            self.done()
        self.assertEqual(personality.slogan,first)
        self.assertEqual(self.sim.values()["tSlogan.txt"],shown)
        self.ui.workflow.guide=None
        personality.tick()
        self.done()
        self.assertNotEqual(personality.slogan,first)
