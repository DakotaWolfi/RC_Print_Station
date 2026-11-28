from base64 import b64decode
from contextlib import closing
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
import json

from benning_csv import ImportErrorDetail, parse_csv
from benning_output import electrical_check, measurement_summary, report_checks, result_kind
from benning_receiver import Capture, Receiver, ReceiverStatus
from benning_rs232 import parse_printout
from benning_store import Measurements, PHASES
from examination_rules import class_review, validate_selection
from slogan_store import SloganStore
from station import measurement_lines, receipt
from station_core import StationCore

from benning_hardware import RAW, USB_41, USB_COMPLETE, USB_DUMP


def table_lines(report):
    job=receipt(report,{"graphic":True,"feed_mm":30})
    # Epson selects CP437 only around the omega, and switches back immediately.
    heading=b"\x1bE\x01Measurement" if report["language"]=="en" else b"\x1bE\x01Messung"
    block=heading[3:]+job.split(heading,1)[1].split(b"-"*42+b"\n",1)[0].replace(b"\x1bE\x00",b"")
    return ["Ω".join(part.decode("cp850") for part in row.split(b"\x1bt\x00\xea\x1bt\x02"))
            for row in block.split(b"\n") if row]


class MeasurementTests(TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)
        self.store=Measurements(self.path/"bench.db")

    @staticmethod
    def row(test):
        return next(row for row in test.measurements if row.name=="Kabel")

    def report(self,slot,source="usb",language="de"):
        row=next(row for row in self.store.slots(source) if row["slot"]==slot)
        return self.store.create_report("BENCH-084","Fixture",PHASES[0],row,language=language)[1]

    def test_real_csv_complete_frames_and_exact_interruption_through_receiver(self):
        self.assertEqual(len(USB_DUMP),5088)
        self.assertIn(b"Pr\xfcfdatum",USB_COMPLETE)
        _,records=parse_csv(USB_COMPLETE,wire=True)
        self.assertEqual(len(records),44)
        for record in records[:41]:
            self.assertEqual(b64decode(record.raw_b64),RAW["usb",record.slot])
        self.assertEqual(len(parse_csv(USB_41,wire=True)[1]),41)
        cable=records[-1]
        self.assertEqual((cable.slot,cable.designation),("044","Kabel"))
        self.assertEqual((self.row(cable).value,self.row(cable).unit,self.row(cable).result),("Gut",None,"bestanden"))
        rx=Receiver(self.store,"usb")
        def send(frame):
            capture=Capture()
            for i in range(0,len(frame),137):
                capture.feed(frame[i:i+137],i/1000+1)
            rx._finish(capture,"usb")
        send(USB_COMPLETE)
        batch=self.store.latest(("usb",))["id"]
        self.assertEqual((rx.status.state,len(self.store.slots("usb"))),("imported",44))
        send(USB_DUMP)
        self.assertEqual(rx.status.state,"error")
        self.assertEqual(self.store.latest(("usb",))["id"],batch)
        send(USB_41)
        self.assertEqual(rx.status.state,"reset-pending")
        self.assertEqual(len(self.store.slots("usb")),44)

    def test_all_real_rs232_reports_and_paired_signatures(self):
        self.store.import_bytes(USB_COMPLETE,"usb")
        for (source,slot),blob in RAW.items():
            if source!="rs232":
                continue
            with self.subTest(slot=slot):
                _,(record,)=parse_printout(blob,wire=True)
                self.assertEqual(record.slot,slot)
                self.assertIsNone(record.protection_class)
                self.assertEqual(b64decode(record.raw_b64),blob)
                self.assertTrue(blob.startswith(b"\x18\x1bc5\x01\x1b!\x04"))
                self.store.import_bytes(blob,"rs232")
                per_port=self.report(slot,"rs232")
                match=class_review({},per_port["record"],"rs232")
                if slot in ("044","045"):
                    self.assertEqual((match["measured"],match["evidence"]),("Kabel","explicit"))
                    self.assertEqual((self.row(record).value,self.row(record).limit),("Gut",None))
                else:
                    expected="II" if int(slot)<=4 else "I"
                    self.assertEqual((match["measured"],match["evidence"]),(expected,"inferred"))
                self.assertEqual(electrical_check(per_port),("Messdaten vollständig",()))
                if slot!="045":
                    from_usb=self.report(slot)
                    def values(report):
                        from benning_output import show_value
                        return {("IB" if row["name"]=="IBer" else row["name"]):
                            show_value(row["value"],row["unit"]) for row in report["measurements"] if row["value"]}
                    self.assertEqual(per_port["record"]["iso_date"],from_usb["record"]["iso_date"])
                    self.assertEqual(values(per_port),values(from_usb))

    def test_csv_validation_stays_strict_and_categorical_unknown_is_visible(self):
        bad=USB_COMPLETE.replace(b"0,06;Ohm",b"Gut;Ohm")
        with self.assertRaisesRegex(ImportErrorDetail,"RPE"):
            parse_csv(bad,wire=True)
        with self.assertRaisesRegex(ImportErrorDetail,"Kabel"):
            parse_csv(USB_COMPLETE.replace(b";Gut;;bestanden",b";Gut;mA;bestanden"),wire=True)
        for status,overall,individual,expected in (
                (b"OPEN",b"nicht bestanden",b"nicht bestanden","FAIL"),
                (b"Shor",b"nicht bestanden",b"nicht bestanden","FAIL"),
                (b"CrOSS",b"nicht bestanden",b"nicht bestanden","FAIL"),
                (b"Unbekannt",b"bestanden",b"bestanden","partial"),
                (b"",b"bestanden",b"bestanden","partial")):
            with self.subTest(status=status):
                # Synthetic negative derived from the captured positive.
                wire=USB_COMPLETE.replace(b"044;Kabel;28/11/2026;bestanden",b"044;Kabel;28/11/2026;"+overall)
                self.store.import_bytes(wire.replace(b";Gut;;bestanden",b";"+status+b";;"+individual),"usb")
                report=self.report("044")
                row=next(row for row in report["measurements"] if row["name"]=="Kabel")
                self.assertEqual(measurement_summary(row,csv_source=True)[-1],expected)
                self.assertEqual(bool(electrical_check(report)[1]),expected=="partial")

    def test_cable_rs232_negative_unknown_and_missing_are_independent_of_overall_pass(self):
        original=RAW["rs232","044"]
        for token,kind in ((b"OPEN","FAIL"),(b"Shor","FAIL"),(b"CrOSS","FAIL"),(b"Unbekannt","partial")):
            with self.subTest(kind=kind,token=token):
                self.store.import_bytes(original.replace(b"Kabelpr\x81fung  Gut",b"Kabelpr\x81fung  "+token),"rs232")
                report=self.report("044","rs232")
                self.assertEqual(result_kind(report),"PASS")
                self.assertTrue(electrical_check(report)[1])
                self.assertEqual(measurement_summary(report["measurements"][-1])[-1],kind)
        self.store.import_bytes(original.replace(b"Kabelpr\x81fung  Gut\r\n",b""),"rs232")
        report=self.report("044","rs232")
        report["examination"]={"procedure":"IEC"}
        self.assertIn("Kabel fehlt",electrical_check(report)[1])
        with self.assertRaisesRegex(ImportErrorDetail,"Kabelstatus"):
            parse_printout(original.replace(b"  Gut",b":"))
        with self.assertRaisesRegex(ImportErrorDetail,"Doppelte"):
            parse_printout(original.replace(b"  Gut\r\n",b"  Gut\r\nKabelpr\x81fung:  Gut\r\n"))

    def test_applicable_methods_early_failure_and_genuine_missing_readings(self):
        self.store.import_bytes(USB_COMPLETE,"usb")
        self.assertEqual(electrical_check(self.report("020")),("Messdaten vollständig",()))
        first=self.report("040")
        self.assertEqual(result_kind(first),"FAIL")
        self.assertEqual(electrical_check(first),("Abbruch nach Fehler · Folgeprüfungen nicht erfasst",()))
        second=self.report("041")
        self.assertEqual(result_kind(second),"FAIL")
        self.assertEqual(electrical_check(second),("Messdaten vollständig",()))
        report=self.report("005")
        report["measurements"]=[row for row in report["measurements"] if row["name"]!="IPE"]
        self.assertEqual(electrical_check(report)[1],("Ableitstrom fehlt",))
        report=self.report("040")
        report["measurements"][0]["unit"]=None
        self.assertIn("RPE: Messwert oder Einheit fehlt",electrical_check(report)[1])

    def test_class_evidence_unknown_and_both_mismatch_directions(self):
        _,records=parse_csv(USB_41,wire=True)
        by_slot={r.slot:asdict(r) for r in records}
        for chosen,slot,expected in (("I","001","II"),("II","005","I")):
            exam={"procedure":chosen,"observed":"PASS","functional":"Ohne Befund","voltage_confirmed":500}
            record=by_slot[slot]
            self.assertEqual(class_review(exam,record,"usb"),
                             dict(selected=chosen,measured=expected,evidence="explicit",mismatch=True))
            with self.assertRaisesRegex(ValueError,"Schutzklasse"):
                validate_selection(exam,record,"usb")
            adopted=validate_selection(exam,record,"usb",resolution="adopt")
            self.assertEqual(adopted["procedure"],expected)
            self.assertNotIn("voltage_confirmed",adopted)
            self.assertEqual(adopted["class_reconciliation"]["prior_examination"],exam)
            self.assertIsNone(validate_selection(exam,record,"usb",resolution="document")["procedure"])
        self.assertFalse(class_review({"procedure":"III"},by_slot["001"],"usb")["mismatch"])
        _,(rs,)=parse_printout(RAW["rs232","001"])
        self.assertEqual(class_review({"procedure":"I"},asdict(rs),"rs232")["evidence"],"inferred")
        with self.assertRaisesRegex(ValueError,"Abgeleitete"):
            validate_selection({"procedure":"I","observed":"PASS"},asdict(rs),"rs232",resolution="adopt")
        unknown=dict(asdict(rs),measurements=[dict(name="RISO",value="1")])
        self.assertEqual(class_review({"procedure":"I"},unknown,"rs232")["evidence"],"unknown")
        self.assertFalse(class_review({"procedure":"I"},unknown,"rs232")["mismatch"])

    def test_compact_receipts_for_three_procedures_in_both_languages(self):
        self.store.import_bytes(USB_COMPLETE,"usb")
        for slot in ("011","001","044"):
            self.store.import_bytes(RAW["rs232",slot],"rs232")
        # Real passed on both links, two real appliance failures, one synthetic cable failure.
        bad=USB_COMPLETE.replace(b"044;Kabel;28/11/2026;bestanden",b"044;Kabel;28/11/2026;nicht bestanden")
        bad=bad.replace(b";Gut;;bestanden",b";OPEN;;nicht bestanden")
        for lang in ("de","en"):
            for source,slot,result in (("rs232","011","PASS"),("rs232","001","PASS"),
                                        ("rs232","044","PASS"),("usb","040","FAIL"),
                                        ("usb","041","FAIL"),("usb","044","FAIL")):
                if slot=="044" and source=="usb":
                    self.store.import_bytes(bad,"usb")
                report=self.report(slot,source,lang)
                lines=table_lines(report)
                self.assertEqual(result_kind(report),result)
                self.assertTrue(all(len(line)<=42 for line in lines))
                self.assertIn("Limit" if lang=="en" else "Grenzwert",lines[0])
                if source=="rs232":
                    self.assertTrue(any(">19,99 MΩ" in line[12:30] and "MΩ" in line[31:] for line in lines))
                    self.assertEqual(len(lines),4 if slot!="001" else 3)
                else:
                    self.assertTrue(all(not line[31:].strip() for line in lines[1:]))
                    self.assertIn("failed" if lang=="en" else "nicht bestanden","".join(lines))
        name,value,limit=("RCD-SonderbezeichnungMitLaenge",">12345678901234567890,6789 MΩ","123456789012345678,99 MΩ")
        lines=list(measurement_lines(name,value,limit))
        for start,end,expected in ((0,11,name),(12,30,value),(31,42,limit)):
            self.assertEqual("".join(line[start:end].strip().replace(" ","") for line in lines),expected.replace(" ",""))

    def test_reparsed_rs232_payload_remains_an_identical_physical_reading(self):
        raw=RAW["rs232","044"]
        self.store.import_bytes(raw,"rs232")
        slot=self.store.slots("rs232")[0]
        # Model a v0.8.3 cache that retained the raw bytes but omitted cable data.
        old=dict(slot["original"],measurements=slot["original"]["measurements"][:-1])
        with closing(self.store.db()) as db,db:
            db.execute("INSERT INTO benning_records VALUES(?,?,?,?,?)",
                       ("legacy",slot["slot"],json.dumps(old),"rs232",slot["imported"]))
            db.execute("UPDATE benning_slots SET record_id='legacy'")
        receiver=SimpleNamespace(mode="rs232",status=ReceiverStatus("waiting","rs232"),close=lambda:None)
        core=StationCore(self.store.path,receiver=receiver,config_path=self.path/"config.json",
                         cache=SloganStore(self.path/"pets.db"))
        self.addCleanup(core.close)
        core.begin({"mode":"direct"})
        core.draft.update(ticket="084",device="Cable fixture")
        core.await_import()
        self.store.import_bytes(raw,"rs232")
        core.refresh_import()
        self.assertEqual(core.phase,"waiting")
        self.assertIsNone(core.selected)
        core.selected=self.store.slots("rs232")[0]
        self.assertEqual(core.snapshot()["selected"]["origin"],"identical")

    def test_reconciliation_confirmation_is_bound_to_current_slot_and_report(self):
        self.store.import_bytes(USB_COMPLETE,"usb")
        rx=SimpleNamespace(mode="usb",status=ReceiverStatus("imported","usb"),close=lambda:None)
        jobs=[]
        core=StationCore(self.store.path,receiver=rx,config_path=self.path/"config.json",
                         cache=SloganStore(self.path/"pets.db"),sender=lambda *args:jobs.append(args))
        self.addCleanup(core.close)
        core.begin({"mode":"guided"})
        core.draft.update(ticket="084",device="Fixture")
        core.examination={"procedure":"II","observed":"PASS","voltage_confirmed":500,
                          "visual":"Ohne Befund","functional":"Ohne Befund"}
        core.refresh_import()
        core.selected=next(row for row in core.slots if row["slot"]=="039")
        core.advance("review")
        ref={"draft":core.draft["id"],"version":core.draft["version"],"record":list(core.identity(core.selected))}
        def command(op,args,client="local"):
            return core.command({"op":op,"args":args,"epoch":core.epoch},client)
        self.assertFalse(command("review.confirm",ref)["ok"])
        self.assertFalse(command("review.confirm",dict(ref,class_resolution="document"))["ok"])
        confirmed=dict(ref,class_resolution="document",class_confirmed=True)
        self.assertFalse(command("review.confirm",dict(confirmed,record=[-1,"wrong"]))["ok"])
        self.assertFalse(command("review.confirm",dict(confirmed,version=-1))["ok"])
        self.assertTrue(command("review.confirm",confirmed)["ok"])
        self.assertFalse(command("review.confirm",confirmed,client="other")["ok"])
        ident=core.report_id
        historical=core.get_report(ident)
        self.assertEqual(historical,core.report)
        self.assertEqual(historical["verdict"],"bestanden")
        self.assertEqual(dict(report_checks(historical))["Freigabe"],"Keine Freigabe · Prüfung wiederholen")
        options={"report":ident,"confirmed":True}
        self.assertTrue(command("report.print",options)["ok"])
        core.jobs["printer"][1].result(2)
        core.tick()
        self.assertFalse(command("report.print",options,client="other")["ok"])
        self.assertEqual(len(jobs),1)
        self.store.import_bytes(USB_COMPLETE.replace(b"0,16;mA;bestanden",b"0,17;mA;bestanden"),"usb")
        self.assertEqual(core.get_report(ident),historical)
