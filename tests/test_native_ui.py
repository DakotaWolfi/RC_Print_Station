import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from native_ui import END, ENCODING, FrameDecoder, NativeUI, report_base, verify_panel
from station import database, receipt, simulate


class MemorySerial:
    baudrate = 115200

    def __init__(self):
        self.written = []

    def write(self, data):
        self.written.append(data)
        return len(data)

    def flush(self):
        pass


class NativeBackendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.serial = MemorySerial()
        self.printed = []
        self.ui = NativeUI(self.serial,"printer",Path(self.tmp.name)/"reports.db",
                           sender=lambda *args:self.printed.append(args),tester_mode="simulation")

    def tearDown(self):
        self.ui.close()
        self.tmp.cleanup()

    def create(self, ticket="RC-42", device="Prüflampe"):
        self.ui.feed(b"RC3:CREATE\x00"+ticket.encode(ENCODING)+b"\x00"+device.encode(ENCODING)+END)

    def commands(self):
        return b"".join(self.serial.written).decode(ENCODING)

    def test_uart_fragmentation_and_coalescing(self):
        decoder = FrameDecoder()
        self.assertEqual(decoder.feed(b"RC3:LAST\xff"),[])
        self.assertEqual(decoder.feed(b"\xff\xff\x01"+END),[b"RC3:LAST",b"\x01"])
        with self.assertLogs("native_ui",level="WARNING"):
            decoder.feed(b"x"*2100)
        self.assertEqual(decoder.feed(b"RC3:LAST"+END),[b"RC3:LAST"])

    def test_store_then_print_existing_receipt_and_cut_sequence(self):
        self.create(device='Mühle "gross" \\ 12 €')
        self.ui.handle(b"RC3:PRINT")
        self.ui.close()
        self.ui.finish_print()
        self.assertEqual(len(self.printed),1)
        self.assertEqual(self.printed[0],("printer",9100,receipt(self.ui.report)))
        self.assertTrue(self.printed[0][2].endswith(b"\x1bJ\xf0\x1bJ\x78\x1dV\x00"))
        with database(self.ui.db) as db:
            stored = json.loads(db.execute("SELECT data FROM reports").fetchone()[0])
        self.assertEqual(stored["device"],'Mühle "gross" \\ 12 €')
        self.assertEqual(stored["source"],"SIMULATOR")
        self.assertIn(b"SIMULATION ONLY",self.printed[0][2])
        self.assertIn(b"12 EUR",self.printed[0][2])

    def test_duplicate_print_during_submission_is_not_queued(self):
        release = threading.Event()
        self.ui.sender = lambda *args: release.wait(2)
        self.create()
        try:
            self.ui.handle(b"RC3:PRINT")
            first = self.ui.print_job[0]
            self.ui.handle(b"RC3:PRINT")
            self.assertIs(self.ui.print_job[0],first)
            self.assertIn("bereits",self.commands())
        finally:
            release.set()

    def test_printer_failure_releases_latch_without_retry(self):
        calls = []
        def fail(*args):
            calls.append(args)
            raise OSError("timeout")
        self.ui.sender = fail
        self.create()
        self.ui.print_report()
        self.ui.close()
        with self.assertLogs("native_ui",level="ERROR"):
            self.ui.finish_print()
        self.assertEqual(len(calls),1)
        self.assertIsNone(self.ui.print_job)
        self.assertIn("Druckfehler",self.commands())
        self.assertIn("report.printing.val=0",self.commands())

    def test_reject_invalid_create_and_non_simulated_history(self):
        for payload in (b"RC3:CREATE\x00 \x00lamp", b"RC3:CREATE\x00"+b"a"*33+b"\x00lamp"):
            with self.assertLogs("native_ui",level="ERROR"):
                self.ui.handle(payload)
        with database(self.ui.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM reports").fetchone()[0],0)
        with self.assertRaises(ValueError):
            self.ui.load_report(1,dict(simulate("T","Lamp"),source="REAL",verdict="PASS"))

    def test_history_and_last_use_saved_report(self):
        for i in range(7):
            self.create(ticket=f"RC-{i}")
        self.ui.refresh_history()
        self.ui.handle(b"RC3:OPEN:4")
        self.assertEqual(self.ui.report["ticket"],"RC-2")
        self.ui.handle(b"RC3:LAST")
        self.assertEqual(self.ui.report["ticket"],"RC-6")
        self.assertEqual(len(self.ui.history),5)

    def test_qr_disabled_and_cached_token(self):
        self.create()
        self.ui.show_qr()
        self.assertIn("qrpage.qReady.val=2",self.commands())
        self.ui.base_url = report_base("http://192.168.1.42:8080")
        self.ui.show_qr()
        first = self.ui.urls[self.ui.report_id]
        self.ui.show_qr()
        self.assertEqual(first,self.ui.urls[self.ui.report_id])
        self.assertLessEqual(len(first),78)
        with database(self.ui.db) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM downloads").fetchone()[0],1)

    def test_bad_download_origin_is_rejected(self):
        for url in ("javascript:alert(1)","http://u:p@host","http://host?x=1",
                    "http://host/"+"x"*60,'http://host/"',"http://host:abc","http://host/path"):
            with self.subTest(url=url),self.assertRaises(ValueError):
                report_base(url)


class HandshakeSerial(MemorySerial):
    def __init__(self,model=b"NX8048T070_011R",protocol=71):
        super().__init__()
        self.buffer = bytearray()
        self.model,self.protocol=model,protocol

    @property
    def in_waiting(self):
        return len(self.buffer)

    def reset_input_buffer(self):
        self.buffer.clear()

    def write(self,data):
        super().write(data)
        if data==b"connect"+END:
            self.buffer.extend(b"comok 1,1,"+self.model+b",1,1,SERIAL,16777216"+END)
        elif data==b"get home.proto.val"+END:
            self.buffer.extend(b"\x71"+self.protocol.to_bytes(4,"little")+END)
        return len(data)

    def read(self,size):
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result


class PanelHandshakeTests(unittest.TestCase):
    def test_matching_panel_does_not_change_its_pages_or_baud(self):
        ser = HandshakeSerial()
        verify_panel(ser)
        self.assertEqual(ser.written,[END,b"connect"+END,b"get home.proto.val"+END])

    def test_reject_wrong_model_or_protocol(self):
        for ser in (HandshakeSerial(b"NX8048K070_011R"),HandshakeSerial(protocol=2)):
            with self.assertRaises(RuntimeError):
                verify_panel(ser)


if __name__=="__main__":
    unittest.main()
