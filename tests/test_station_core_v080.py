"""Single-core, headless and dual-client regressions."""
from pathlib import Path
import socket
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

from benning_receiver import ReceiverStatus
from display_presence import inspect, qt_environment, touchscreens
from nextion_adapter import NextionAdapter, SerialLink
from report_web import render_pdf
from slogan_store import SloganStore
from station_core import StationCore
from station_ipc import request, serving
from test_benning import EXAMPLES, EXAMPLE_ROWS, single_failure, wire
from test_hmi_native import APP, PanelSerial, Simulation


class CoreTests(unittest.TestCase):
    def setUp(self):
        scratch=tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.path=Path(scratch.name)
        self.sent=[]
        self.usb=SimpleNamespace(mode="usb",status=ReceiverStatus("waiting",source="usb"),
                                 start=lambda:None,close=lambda:None)
        self.core=StationCore(self.path/"reports.sqlite3",receiver=self.usb,
                              cache=SloganStore(self.path/"slogans.sqlite3"),config_path=self.path/"settings.json",
                              sender=lambda *job:self.sent.append(job),base_url="http://127.0.0.1:8081")
        self.addCleanup(self.core.close)

    def call(self,op,args=None,client="bench",ident=None,wanted=True):
        response=self.core.command({"op":op,"args":args or {},"id":ident},client)
        self.assertEqual(response["ok"],wanted,response)
        return response.get("data")

    def ref(self,**args):
        d=self.core.draft
        return dict(draft=d["id"],version=d["version"],**args)

    def fill(self,mode="direct"):
        self.call("draft.new",{"mode":mode})
        self.call("draft.edit",self.ref(changes={"ticket":"V080-1","device":"Demo bench"},
                                        previous={"ticket":"","device":""}))

    def imported(self, data):
        result=self.core.store.import_bytes(data,"usb")
        self.usb.status=ReceiverStatus("imported","usb",batch=result.batch)
        self.core.last_import_check=0
        self.core.tick()

    def test_headless_import_report_print_pdf_and_restart(self):
        self.imported(EXAMPLES)
        self.fill()
        self.call("language.report",self.ref(language="en"))
        self.call("exam.start",self.ref())
        self.imported(wire([EXAMPLE_ROWS[0],single_failure(),EXAMPLE_ROWS[2]]))
        self.assertEqual(self.core.phase,"review")
        selected=self.core.snapshot()["selected"]
        self.assertIsNotNone(selected)
        confirm=self.ref(record=selected["key"])
        self.call("review.confirm",confirm,ident="one")
        self.call("review.confirm",confirm,ident="one")  # same-client retry
        self.call("review.confirm",confirm,ident="other",client="second",wanted=False)
        rows=self.call("history")
        self.assertEqual(len(rows),1)
        ident=rows[0]["id"]
        saved=self.call("report.get",{"report":ident})
        self.assertEqual(saved["language"],"en")
        self.assertEqual(saved["verdict"],"nicht bestanden")
        self.assertIn(b"/Count 1",render_pdf(saved))
        self.assertIn("/r/",self.call("report.link",{"report":ident}))
        self.call("report.print",{"report":ident,"confirmed":True})
        self.core.jobs["printer"][1].result(timeout=2)
        self.core.tick()
        self.call("report.print",{"report":ident,"confirmed":True},client="second",wanted=False)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.sent[0][:2],("169.254.25.23",9100))
        self.assertIn(b"\x1bt\x00\xea",self.sent[0][2])
        reopened=StationCore(self.core.db,receiver=self.usb,cache=self.core.cache)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.command({"op":"report.get","args":{"report":ident}})["data"],saved)

    def test_novelty_receipts_are_distinct_and_never_enter_history(self):
        self.call("novelty.print",{"kind":"awoo"},wanted=False)
        self.call("novelty.print",{"kind":"awoo","confirmed":True})
        self.core.jobs["printer"][1].result(timeout=2)
        self.core.tick()
        self.assertTrue(self.sent[0][2].startswith(b"\x1b@\x1dv0\x00"))
        self.assertEqual(self.call("history"),[])
        self.call("settings.save",{"values":{"professional":True}})
        self.call("novelty.print",{"kind":"paw","confirmed":True},wanted=False)

    def test_two_clients_merge_different_fields_reject_same_stale_edit(self):
        self.call("draft.new",{"mode":"guided"})
        state=self.core.command({"op":"state"})["data"]
        d=state["draft"]
        barrier=threading.Barrier(2)
        results=[]
        def edit(key,value):
            barrier.wait()
            results.append(self.core.command({"op":"draft.edit","epoch":state["epoch"],
                "args":{"draft":d["id"],"previous":{key:""},"changes":{key:value}}},key))
        threads=[threading.Thread(target=edit,args=(key,value))
                 for key,value in (("ticket","R-2"),("device","Staubsauger"))]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(2)
        self.assertEqual(sum(row["ok"] for row in results),2)
        self.call("draft.edit",self.ref(changes={"ticket":"stale"},previous={"ticket":""}),wanted=False)
        self.call("settings.save",{"values":{"language":"en"}})
        self.call("language.report",self.ref(language="de"))
        new=self.core.command({"op":"state"},"reconnected")["data"]
        self.assertEqual((new["draft"]["ticket"],new["draft"]["device"]),("R-2","Staubsauger"))
        self.assertEqual((new["language"],new["report_language"]),("en","de"))

    def test_private_unix_socket_headless_and_reconnect(self):
        try:
            with socket.socket(socket.AF_UNIX):
                pass
        except PermissionError:
            self.skipTest("Unix sockets are restricted by the test environment")
        self.call("draft.new",{"mode":"direct"})
        with serving(self.path/"station.sock",self.core):
            first=request(self.path/"station.sock",{"op":"state","client":"display1"})["data"]
            again=request(self.path/"station.sock",{"op":"state","client":"display2"})["data"]
            self.assertEqual(first["draft"],again["draft"])
            self.assertEqual((self.path/"station.sock").stat().st_mode&0o777,0o700)

    def test_connected_editor_holds_transition_but_accepts_other_fields(self):
        self.fill()
        self.call("draft.editor",self.ref(active=True),client="nextion")
        self.call("draft.edit",self.ref(changes={"device":"update"},previous={"device":"Demo bench"}),client="hdmi")
        self.call("exam.start",self.ref(),client="hdmi",wanted=False)
        self.call("draft.editor",self.ref(active=False),client="nextion")
        self.call("exam.start",self.ref(),client="hdmi")
        self.assertEqual(self.core.phase,"waiting")

    def test_manual_rules_professional_and_stale_guide_action(self):
        self.fill("guided")
        self.call("exam.start",self.ref())
        guard=self.ref(step="visual",choice=1)
        self.call("guide.choose",guard)
        self.assertEqual(self.core.guide.step,"stop")
        self.call("guide.choose",guard,wanted=False)
        self.call("guide.choose",self.ref(step="stop",choice=0))
        self.call("exam.submit",self.ref())
        self.assertEqual(self.core.report["source"],"EXAMINATION")
        self.call("settings.save",{"values":{"professional":True}})
        self.call("personality.pet",wanted=False)
        self.assertIsNone(self.core.snapshot()["personality"]["slogan"])

    def test_firmware_adapter_and_hdmi_touch_same_draft(self):
        if Simulation is None:
            self.skipTest("nxwright unavailable")
        incoming=bytearray()
        panel=Simulation(APP,sending=incoming.extend)
        adapter=NextionAdapter(self.core,PanelSerial(panel))
        self.addCleanup(adapter.close)

        def pump():
            for _ in range(16):
                data=bytes(incoming)
                incoming.clear()
                if data:
                    adapter.feed(data)
                adapter.next_sync=0
                adapter.sync()
                if not incoming:
                    return
            self.fail("Nextion did not settle")

        def tap(name):
            obj=next(item for item in panel.components() if item.name==name)
            v=obj.values
            x,y=v["x"]+v["w"]//2,v["y"]+v["h"]//2
            self.assertEqual(panel.component_at(x,y),name)
            panel.press(name,x,y)
            panel.release()
            pump()

        adapter.connect_panel()
        pump()
        tap("bNew")
        self.assertEqual(self.core.draft["mode"],"guided")
        tap("hEdit0")
        panel.serial_input('input.txt="NEXTION-1"')
        self.call("draft.edit",self.ref(changes={"device":"HDMI device"},previous={"device":""}),client="hdmi")
        tap("bOK")
        self.assertEqual(self.core.draft["ticket"],"NEXTION-1")
        self.assertEqual(self.core.draft["device"],"HDMI device")
        self.assertEqual(panel.values()["tDevice.txt"],"HDMI device")
        tap("bReportLang")
        self.assertEqual(self.core.report_language(),"en")
        self.call("settings.save",{"values":{"language":"en"}},client="hdmi")
        pump()
        self.assertEqual(panel.values()["bReportLang.txt"],"Report: EN")
        tap("bCreate")
        self.assertEqual((self.core.phase,panel.page),("guide","guide"))
        old_step=self.ref(step="visual",choice=0)
        tap("bStep0")
        self.assertEqual(self.core.guide.step,"kind")
        self.call("guide.choose",old_step,client="hdmi",wanted=False)
        adapter.connect_panel()
        pump()
        self.assertEqual((panel.page,self.core.guide.step),("guide","kind"))


class DisplayPresenceTests(unittest.TestCase):
    def test_drm_hotplug_and_touch_classification(self):
        with tempfile.TemporaryDirectory() as scratch:
            root=Path(scratch)
            port=root/"card0-HDMI-A-1"
            port.mkdir()
            (port/"status").write_text("disconnected\n")
            (port/"modes").write_text("1024x600\n800x480\n")
            udev=root/"udev"
            udev.mkdir()
            touch=root/"event8"
            touch.mkdir()
            mouse=root/"event9"
            mouse.mkdir()
            (touch/"dev").write_text("13:72")
            (mouse/"dev").write_text("13:73")
            (udev/"c13:72").write_text("E:ID_INPUT_TOUCHSCREEN=1\n")
            (udev/"c13:73").write_text("E:ID_INPUT_MOUSE=1\n")
            options=dict(drm=root,input_root=root,udev=udev,env={})
            self.assertFalse(inspect(**options)["available"])
            self.assertTrue(inspect(**options,force=True)["available"])
            (port/"status").write_text("connected")
            state=inspect(**options)
            self.assertTrue(state["available"])
            self.assertEqual((state["modes"],state["touch"]),(("1024x600","800x480"),("/dev/input/event8",)))
            (udev/"c13:72").unlink()
            self.assertEqual(touchscreens(root,udev),())

    def test_display_absent_does_not_hold_startup(self):
        calls=[]
        def missing(*args,**kw):
            calls.append(args)
            raise OSError("missing")
        link=SerialLink("/dev/test",opener=missing)
        link.start()
        limit=time.monotonic()+1
        while not calls and time.monotonic()<limit:
            time.sleep(.01)
        self.assertTrue(calls)
        self.assertFalse(link.ready.is_set())
        link.close()
        self.assertEqual(qt_environment("linuxfb",90,"/dev/input/event4",{})[
            "QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS"],"/dev/input/event4")

    def test_supervisor_relaunches_without_owning_station(self):
        from display_presence import supervise
        states=[(False,()),(True,("800x480",)),(False,()),(True,("1024x600",))]
        actions=[]
        class Stop:
            i=0
            def is_set(self):
                return self.i>=len(states)
            def wait(self,_):
                self.i+=1
        class Child:
            dead=False
            def poll(self):
                return 0 if self.dead else None
            def terminate(self):
                self.dead=True
                actions.append("stop")
            def wait(self,timeout):
                return 0
        stop=Stop()
        def detect(**unused):
            available,modes=states[stop.i]
            return {"available":available,"connector":"HDMI-A-1" if available else "",
                    "modes":modes,"touch":()}
        def launch(args,env):
            self.assertIn("hdmi_frontend.py",args[1])
            actions.append("start")
            return Child()
        settings=SimpleNamespace(connector="",force=False,mode="auto",backend="offscreen",
                                 touch="",socket="/not-used.sock",window=False,rotation=0)
        supervise(settings,stop,detect,launch)
        self.assertEqual(actions,["start","stop","start","stop"])
