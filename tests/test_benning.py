import base64
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import pty
import select
import tempfile
from threading import Thread
import time
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from benning_admin import ImportPage
from benning_csv import HEADER, ImportErrorDetail, parse_csv, outcome
from benning_receiver import Receiver, choose_port
from benning_rs232 import PREAMBLE, parse_printout
from benning_store import Measurements, PHASES
from report_web import publish, render_pdf, start_server
from station import receipt, graphic_header

CAPTURE_TEXT=(Path(__file__).parent/"fixtures"/"benning_usbcsv_examples.txt").read_text(encoding="utf-8")
EXAMPLE_ROWS=CAPTURE_TEXT.splitlines()[1:]
EXAMPLES=CAPTURE_TEXT.replace("\n","\r\n").encode("cp437")


def wire(rows,encoding="cp437"):
    return ("\r\n".join([";".join(HEADER),*rows])+"\r\n").encode(encoding)


def single_failure(slot="005"):
    row=EXAMPLE_ROWS[1].split(";")
    row[0]=slot
    row[3]="nicht bestanden"
    row[4]=">2,34"
    row[6]="nicht bestanden"
    # A value without a result must stay incomplete.
    row[9]=""
    return ";".join(row)


# Synthetic transcript, following the documented forum layout and control prefix.
RS232=PREAMBLE+(
    "\r\n--------------------------------Prüfung gemäss DIN VDE 0701-0702\r\n"
    "Ident-Nr.  _______________\r\nPrüfobjekt  _______________\r\n"
    "Speicherplatz-Nr.   012\r\nDatum     13.11.2026\r\n"
    "Prüfung   Messwert Grenzwert\r\n"
    "RPE:      0,18Ω   0,30Ω\r\nRISO:     >19,99MΩ    1,00MΩ\r\n"
    "VISO:      500V\r\nIPE:      <0,13mA    3,50mA\r\n"
    "Prüfergebnis   Bestanden\r\nPrüffirma  _____________________\r\n"
    "Prüfer     _____________________\r\n").encode("cp437")


class CsvTests(unittest.TestCase):
    def test_header_selects_codec_and_passed_german_values_survive(self):
        for encoding in ("cp437","cp850","cp1252","utf-8-sig"):
            with self.subTest(encoding=encoding):
                raw=wire(EXAMPLE_ROWS,encoding)
                code,items=parse_csv(raw,wire=True)
                self.assertIn(encoding,code)
                slot1,slot5,slot33=items
                self.assertEqual(slot1.protection_class,"Klasse II")
                self.assertEqual((slot5.slot,slot5.tester_date,slot5.voltage),("005","15/08/2026","500V"))
                self.assertEqual(outcome(slot33.verdict),"PASS")
                items={m.name:m for m in slot1.measurements}
                self.assertEqual(items["IBer"].value,"<0,10")
                self.assertEqual(items["RISO"].value,">19,99")
                self.assertIsNone(items["RPE"].value)
                self.assertIsNone(items["RPE"].result)
                self.assertEqual(base64.b64decode(slot1.raw_b64),raw.split(b"\r\n")[1]+b"\r\n")

    def test_failure_and_fi_fields(self):
        row=single_failure().split(";")
        row[23:]=["bestanden","synthetisch","<10,5","ms","nicht bestanden"]
        _,[record]=parse_csv(wire([";".join(row)]))
        tests={m.name:m for m in record.measurements}
        self.assertEqual(outcome(record.verdict),"FAIL")
        self.assertEqual(tests["RPE"].value,">2,34")
        self.assertEqual(tests["RPE"].result,"nicht bestanden")
        self.assertIsNone(tests["IPE"].result)
        self.assertEqual(tests["Sichtprüfung"].result,"bestanden")
        self.assertEqual((tests["FI/RCD"].value,tests["FI/RCD"].test),("<10,5","synthetisch"))

    def test_invalid_transfers_rejected(self):
        for data in (EXAMPLES[:-4],EXAMPLES.replace(b"\r\n",b"\n"),wire([EXAMPLE_ROWS[0][:-1]]),
                     wire([EXAMPLE_ROWS[0]]*2),wire([EXAMPLE_ROWS[0].replace("15/08","31/09")]),
                     wire([EXAMPLE_ROWS[0].replace("<0,10","nonsense")]),
                     wire([EXAMPLE_ROWS[0].replace("bestanden","unbekannt",1)]),
                     wire([EXAMPLE_ROWS[0].replace("Klasse II","Klasse II\x1b")]),wire([])):
            with self.subTest(data=data[-80:]),self.assertRaises(ImportErrorDetail):
                parse_csv(data,wire=True)

    def test_ambiguous_unicode_requires_explicit_override(self):
        row=EXAMPLE_ROWS[0].replace("Klasse II","Klasse II Ø")
        data=wire([row],"cp850")
        with self.assertRaisesRegex(ImportErrorDetail,"mehrdeutig"):
            parse_csv(data)
        _,[item]=parse_csv(data,"cp850")
        self.assertEqual(item.designation,"Klasse II Ø")

    def test_rs232_preserves_measured_limits_and_original_result(self):
        codec,[record]=parse_printout(RS232,wire=True)
        self.assertEqual((codec,record.slot,record.voltage),("cp437","012","500V"))
        self.assertEqual(record.measurements[1].unit,"MΩ")
        self.assertEqual(record.measurements[1].limit,"1,00")
        self.assertIsNone(record.measurements[1].result)
        self.assertIsNone(record.protection_class)
        self.assertEqual(base64.b64decode(record.raw_b64),RS232)
        with self.assertRaises(ImportErrorDetail):
            parse_printout(RS232.split(b"Pr\x81fer ")[0])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"station.db"
        self.db=Measurements(self.path)

    def test_duplicates_changes_and_overwrites_keep_history(self):
        first=self.db.import_bytes(EXAMPLES,"usb")
        self.assertEqual((first.suggested,first.reason),("033","baseline"))
        copy=self.db.import_bytes(EXAMPLES,"usb")
        self.assertEqual(copy.reason,"unchanged")
        self.db.import_bytes(EXAMPLES,"file-csv")
        with closing(self.db.db()) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM benning_records").fetchone()[0],3)
        row=next(r for r in self.db.slots("usb") if r["slot"]=="005")
        ident,old=self.db.create_report("R1","Lampe",PHASES[0],row)
        changed=self.db.import_bytes(wire([EXAMPLE_ROWS[0],single_failure(),EXAMPLE_ROWS[2]]),"usb")
        self.assertEqual((changed.modified,changed.suggested,changed.reason),(("005",),"005","single-change"))
        after=next(r for r in self.db.slots("usb") if r["slot"]=="005")
        self.assertNotEqual(row["record_id"],after["record_id"])
        _,new=self.db.create_report("R1","Lampe",PHASES[1],after)
        self.assertEqual((old["verdict"],new["verdict"]),("bestanden","nicht bestanden"))
        with closing(self.db.db()) as conn:
            original=json.loads(conn.execute("SELECT data FROM reports WHERE id=?",(ident,)).fetchone()[0])
        self.assertEqual(original,old)

    def test_missing_slots_quarantined_and_multiple_changes_uncertain(self):
        first=self.db.import_bytes(EXAMPLES,"usb")
        with self.assertRaisesRegex(ImportErrorDetail,"weniger Slots"):
            self.db.import_bytes(wire(EXAMPLE_ROWS[:-1]),"usb")
        self.assertEqual(self.db.latest(("usb",))["id"],first.batch)
        modified=self.db.import_bytes(wire([single_failure("001"),single_failure(),EXAMPLE_ROWS[2]]),"usb")
        self.assertEqual(modified.reason,"ambiguous")
        self.assertEqual(modified.modified,("001","005"))
        reset=self.db.import_bytes(wire(EXAMPLE_ROWS[:1]),"usb",accept_reset=True)
        self.assertEqual(reset.reason,"baseline")
        self.assertEqual(len(self.db.slots("usb")),1)

    def test_receipt_pdf_and_download_only_hotspot_listener(self):
        self.db.import_bytes(wire([single_failure()]),"file-csv")
        _,report=self.db.create_report("R2","Heizlüfter",PHASES[2],self.db.slots("file-csv")[0])
        data=receipt(report)
        self.assertIn(graphic_header(),data)
        self.assertIn(b"nicht bestanden",data)
        self.assertIn(b">2,34 \x1bt\x00\xea\x1bt\x02",data)
        self.assertNotIn(b"SIMULATION",data)
        self.assertTrue(render_pdf(report).startswith(b"%PDF-"))
        server=start_server(self.path,0)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base=f"http://127.0.0.1:{server.server_port}"
        url=publish(self.path,report,base)
        with urlopen(url,timeout=3) as result:
            self.assertIn("benning-report.pdf",result.headers["Content-Disposition"])
        for path,method in (("/benning","GET"),("/history","GET"),("/print","POST"),("/benning","POST")):
            with self.subTest(path=path,method=method),self.assertRaises(HTTPError):
                urlopen(Request(base+path,method=method),timeout=3)

    def test_receive_only_pty_fragmentation_and_interrupted_reconnect(self):
        try:
            import serial
        except ImportError:
            self.skipTest("pyserial is required for PTY integration")
        master,slave=pty.openpty()
        path=os.ttyname(slave)
        rx=Receiver(self.db,"usb",resolver=lambda:("usb",path) if os.path.exists(path) else None,idle=.5)
        self.addCleanup(os.close,slave)
        self.addCleanup(rx.close)
        rx.start()

        def wait_for(predicate):
            end=time.monotonic()+3
            while time.monotonic()<end and not predicate():
                time.sleep(.01)
            self.assertTrue(predicate(),rx.status)

        try:
            wait_for(lambda:rx.status.state=="waiting")
            for i in range(0,len(EXAMPLES),19):
                os.write(master,EXAMPLES[i:i+19])
            wait_for(lambda:rx.status.state=="imported")
            batch=self.db.latest(("usb",))["id"]
            self.assertFalse(select.select([master],[],[],.05)[0],"Tester port unexpectedly transmitted")
            os.write(master,EXAMPLES[:280])
            wait_for(lambda:rx.status.state=="receiving")
        finally:
            os.close(master)
        wait_for(lambda:rx.status.state in ("interrupted","searching","disconnected"))
        self.assertEqual(self.db.latest(("usb",))["id"],batch)

    def test_loopback_upload_requires_auth_and_csrf(self):
        token="synthetic-test-token-long-enough"
        page=ImportPage(self.path,token)

        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass

            def do_GET(self):
                page.serve(self)

            def do_POST(self):
                page.serve(self,submit=True)

        with ThreadingHTTPServer(("127.0.0.1",0),Handler) as server:
            worker=Thread(target=server.serve_forever,daemon=True)
            worker.start()
            try:
                url=f"http://127.0.0.1:{server.server_port}/benning"
                with self.assertRaises(HTTPError) as error:
                    urlopen(url,timeout=3)
                self.assertEqual(error.exception.code,401)
                auth=base64.b64encode(f"benning:{token}".encode()).decode()
                headers={"Authorization":f"Basic {auth}"}
                with urlopen(Request(url,headers=headers),timeout=3) as reply:
                    self.assertIn(page.csrf.encode(),reply.read())
                headers["Content-Type"]="multipart/form-data; boundary=bench"

                def upload(csrf):
                    data=(b'--bench\r\nContent-Disposition: form-data; name="format"\r\n\r\ncsv\r\n'
                          b'--bench\r\nContent-Disposition: form-data; name="csrf"\r\n\r\n'+csrf.encode()+b'\r\n'
                          b'--bench\r\nContent-Disposition: form-data; name="data"; filename="bench.csv"\r\n'
                          b'Content-Type: application/octet-stream\r\n\r\n'+EXAMPLES+b'\r\n--bench--\r\n')
                    return urlopen(Request(url,data=data,headers=headers),timeout=3)

                with self.assertRaises(HTTPError) as error:
                    upload("wrong")
                self.assertEqual(error.exception.code,403)
                self.assertEqual(self.db.slots("file-csv"),[])
                with upload(page.csrf) as reply:
                    self.assertIn(b"3 Messungen importiert",reply.read())
                self.assertEqual(len(self.db.slots("file-csv")),3)
            finally:
                server.shutdown()
                worker.join()

    def test_detect_prefers_persistent_path_and_rejects_hmi_or_ambiguity(self):
        from benning_receiver import USB_PATH
        self.assertEqual(choose_port("auto",exists=lambda p:p==USB_PATH,list_ports=lambda:[]),("usb",USB_PATH))
        p=SimpleNamespace(vid=0x10c4,pid=0xea60,serial_number="0001",device="/dev/ttyUSB9")
        self.assertEqual(choose_port("auto",exists=lambda x:x==p.device,list_ports=lambda:[p]),("usb",p.device))
        with self.assertRaises(ImportErrorDetail):
            choose_port("auto",usb="/dev/ttyUSB0",rs232="/dev/ttyUSB1",exists=lambda p:True)
        with self.assertRaises(ImportErrorDetail):
            choose_port("rs232",rs232="/dev/serial0",exists=lambda p:True,hmi="/dev/serial0")
