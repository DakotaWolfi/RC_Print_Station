from pathlib import Path
import struct
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase,skipIf
from unittest.mock import patch
from urllib.request import urlopen

from benning_receiver import Capture,Receiver,ReceiverStatus
from benning_store import Measurements,StorageReset
from novelty import ITEMS, preview_path, render
from pdf_export import pdf_filename,save_pdf
from report_web import publish,start_server
from slogan_store import SloganStore
from station import receipt,simulate
from station_core import StationCore

from test_benning import EXAMPLES,EXAMPLE_ROWS,RS232,wire

try:
    from PIL import Image
except ImportError:
    Image=None


class PhysicalRegressions(TestCase):
    def setUp(self):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path=Path(directory.name)
        self.store=Measurements(self.path/"station.db")

    def core(self,receiver):
        prints=[]
        c=StationCore(self.store.path,receiver=receiver,config_path=self.path/"config.json",
                      cache=SloganStore(self.path/"pets.db"),sender=lambda *args:prints.append(args))
        self.addCleanup(c.close)
        return c,prints

    @staticmethod
    def ref(core,**fields):
        return dict(draft=core.draft["id"],version=core.draft["version"],**fields)

    def send(self,core,op,args=None,*,client="local",ok=True):
        result=core.command({"op":op,"args":args or {},"epoch":core.epoch},client)
        self.assertEqual(result["ok"],ok,result)
        return result["data"] if ok else result["error"]

    def begin(self,core,kind="direct",client="local"):
        self.send(core,"draft.new",{"mode":kind},client=client)
        self.send(core,"draft.edit",self.ref(core,changes={"ticket":"A-0001","device":"Bench kettle"},
                    previous={"ticket":"","device":""}),client=client)
        self.send(core,"exam.start",self.ref(core),client=client)

    def test_owner_recovery_requires_conscious_handoff_and_bumps_revision(self):
        rx=SimpleNamespace(mode="file",status=ReceiverStatus("file"),close=lambda:None)
        core,_=self.core(rx)
        first,second="a"*32,"web-fixture-b"
        with patch("station_core.monotonic",return_value=100):
            self.begin(core,"guided",first)
            ref=self.ref(core,step="visual",choice=0)
            self.assertEqual(self.send(core,"state",client=second)["control"],"other")
            self.send(core,"guide.choose",ref,client=second,ok=False)
            self.send(core,"draft.control",self.ref(core,action="resume",confirmed=True),client=second,ok=False)
        with patch("station_core.monotonic",return_value=121):
            self.assertEqual(self.send(core,"state",client=second)["control"],"available")
            self.send(core,"guide.choose",ref,client=second,ok=False)
            self.send(core,"draft.control",self.ref(core,action="resume",confirmed=False),client=second,ok=False)
            self.send(core,"draft.control",self.ref(core,action="resume",confirmed=True),client=second)
            self.assertEqual(core.guide.step,"visual")
            self.send(core,"guide.choose",ref,client=second,ok=False)
            self.send(core,"guide.choose",self.ref(core,step="visual",choice=0),client=first,ok=False)
            self.send(core,"guide.choose",self.ref(core,step="visual",choice=0),client=second)
            self.assertEqual(core.guide.step,"kind")
            self.send(core,"draft.control",self.ref(core,action="release",confirmed=True),client=second)
            self.assertEqual(self.send(core,"state",client=first)["control"],"available")

    def frame(self,rx,data,source="usb"):
        cap=Capture()
        cap.feed(data,1)
        rx._finish(cap,source)

    def test_reset_reused_slot_and_identical_upload_keep_original_and_require_confirmation(self):
        rx=Receiver(self.store,"usb")
        self.frame(rx,EXAMPLES)
        oldrow=next(row for row in self.store.slots("usb") if row["slot"]=="005")
        oldid,oldreport=self.store.create_report("OLDER","Bench lamp","Eingangsprüfung",oldrow)
        core,prints=self.core(rx)
        self.begin(core)
        header_only=wire([])
        self.frame(rx,header_only[:-2])
        self.assertEqual(rx.status.state,"error")
        self.assertEqual(len(self.store.slots("usb")),3)
        with self.assertRaises(StorageReset):
            self.store.import_bytes(header_only,"usb")
        self.frame(rx,header_only)
        self.assertEqual(rx.status.state,"reset-pending")
        reset=rx.status.reset
        self.send(core,"import.reset",self.ref(core,reset="not-the-frame",confirmed=True),ok=False)
        self.send(core,"import.reset",self.ref(core,reset=reset,confirmed=True))
        self.assertEqual(self.store.slots("usb"),[])
        self.frame(rx,wire([EXAMPLE_ROWS[1]]))
        core.refresh_import()
        self.assertIsNone(core.selected)
        self.send(core,"review.manual",self.ref(core))
        row=core.snapshot()["slots"][0]
        self.assertEqual(row["origin"],"identical")
        self.send(core,"review.select",self.ref(core,record=row["key"]))
        self.send(core,"review.confirm",self.ref(core,record=row["key"]),ok=False)
        self.send(core,"review.confirm",self.ref(core,record=row["key"],same_reading_confirmed=True))
        new=core.report
        self.assertEqual(new["record_id"],oldreport["record_id"])
        self.assertNotEqual(new["import_batch"],oldreport["import_batch"])
        self.assertEqual(new["measurement_confirmation"],"identical")
        self.assertNotEqual(core.report_id,oldid)
        self.send(core,"report.print",{"report":oldid,"confirmed":True})
        core.jobs["printer"][1].result(2)
        core.tick()
        self.assertEqual(prints[0][2],receipt(oldreport,core.config))
        self.send(core,"report.print",{"report":oldid,"confirmed":True},ok=False)

    def test_rs232_reused_slot_same_day_retransmission_then_changed_measurement(self):
        rx=Receiver(self.store,"rs232")
        self.frame(rx,RS232,"rs232")
        old=self.store.slots("rs232")[0]
        core,_=self.core(rx)
        self.begin(core)
        self.frame(rx,RS232,"rs232")
        core.refresh_import()
        self.assertIsNone(core.selected)
        self.frame(rx,RS232.replace(b"0,18",b"0,21"),"rs232")
        core.refresh_import()
        self.assertEqual(core.phase,"review")
        self.assertEqual(core.selected["slot"],old["slot"])
        self.assertNotEqual(core.selected["record_id"],old["record_id"])

    def test_pdf_download_headers_real_pdf_and_non_overwriting_local_save(self):
        report=simulate("../P-00 Ä 1","Bench test")
        report["created"]="2026-11-28T10:00:00+01:00"
        name="FMI-2026-11-28-P-00-A-1-R41.pdf"
        self.assertEqual(pdf_filename(report,41),name)
        first=save_pdf(self.path/"Downloads",report,41)
        old=first.read_bytes()
        second=save_pdf(self.path/"Downloads",report,41)
        self.assertNotEqual(first,second)
        self.assertEqual(first.read_bytes(),old)
        self.assertTrue(second.read_bytes().startswith(b"%PDF-"))
        server=start_server(self.store.path,0)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        url=publish(self.store.path,dict(report,_download_id=41),f"http://127.0.0.1:{server.server_port}")
        with urlopen(url+"?download=1",timeout=2) as result:
            self.assertEqual(result.headers["Content-Disposition"],f'attachment; filename="{name}"')
            self.assertEqual(result.headers["Cache-Control"],"no-store")
            self.assertTrue(result.read().startswith(b"%PDF-"))
        with urlopen(url,timeout=2) as result:
            self.assertEqual(result.headers["Content-Disposition"],f'inline; filename="{name}"')

    @skipIf(Image is None,"Pillow verifies raster pixels against previews")
    def test_novelty_raster_matches_preview_and_final_feed_cut_at_all_lengths(self):
        for kind in ITEMS:
            for language in ("en","de"):
                for feed in (0,45,77,100):
                    with self.subTest(kind=kind,language=language,feed=feed):
                        data=render(kind,language,feed)
                        self.assertEqual(data[:6],b"\x1b@\x1dv0\x00")
                        width,lines=struct.unpack("<HH",data[6:10])
                        self.assertEqual(width,63)
                        end=10+width*lines
                        preview=Image.open(preview_path(kind,language))
                        self.assertEqual(preview.size,(504,lines))
                        self.assertEqual(bytes(v^255 for v in preview.tobytes()),data[10:end])
                        self.assertGreater(sum(data[10:end]),80000)
                        tail=data[end:]
                        self.assertEqual(tail[:1],b"\n")
                        self.assertEqual(tail[-3:],b"\x1dV\x00")
                        chunks=tail[1:-3]
                        self.assertEqual(len(chunks)%3,0)
                        self.assertTrue(all(chunks[n:n+2]==b"\x1bJ" and 0<chunks[n+2]<=240 for n in range(0,len(chunks),3)))
                        self.assertEqual(sum(chunks[2::3]),8*max(45,feed))
