from contextlib import closing
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from benning_guide import Guide, STEPS
from benning_output import electrical_check, report_checks, result_kind
from benning_store import Measurements, PHASES
from operator_store import APPLIANCES, Operators, name_key
from panel_text import bounds, fit, paginate, quote, word_lines
from station import receipt
from test_benning import EXAMPLES


class OperatorStoreTests(unittest.TestCase):
    def setUp(self):
        tmp=TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path=Path(tmp.name)/"station.db"
        self.store=Measurements(self.path)
        self.people=Operators(self.store.db)

    def test_names_order_persist_and_old_reports_preserve_name(self):
        old=self.people.rename("Muster Person A")
        new=self.people.rename("Muster Person B")
        self.assertEqual(self.people.rename("muster   person B"),new)
        ident,_=self.store.create_incomplete("123","Leuchte",PHASES[0],
                                           {"examiner":"Muster Person B"},examiner_id=new)
        self.people.rename("Muster Person Neu",new)
        restarted=Operators(Measurements(self.path).db)
        self.assertEqual(restarted.examiners()[0]["id"],new)
        self.assertEqual(restarted.active_name(new),"Muster Person Neu")
        restarted.set_active(new,False)
        self.assertEqual([row["id"] for row in restarted.examiners()],[old])
        self.assertFalse(restarted.examiners(include_inactive=True)[1]["active"])
        with closing(self.store.db()) as conn:
            snapshot=json.loads(conn.execute("SELECT data FROM reports WHERE id=?",(ident,)).fetchone()[0])
        self.assertEqual(snapshot["examination"]["examiner"],"Muster Person B")
        restarted.set_active(new,True)
        self.assertEqual(restarted.examiners()[0]["id"],new)

    def test_device_history_keeps_eight_recent_unique_values_and_all_templates(self):
        for idx in range(10):
            self.store.create_incomplete(str(idx),f"Gerät {idx}",PHASES[0],{})
        self.store.create_incomplete("water","Wasserkocher",PHASES[0],{})
        self.store.create_incomplete("again","wasserkocher",PHASES[0],{})
        recent=Operators(Measurements(self.path).db).appliances()
        self.assertEqual([label for label,old in recent if old][:3],["wasserkocher","Gerät 9","Gerät 8"])
        self.assertEqual(sum(is_recent for _,is_recent in recent),8)
        self.assertEqual(len({name_key(label) for label,_ in recent}),len(recent))
        self.assertTrue({name_key(label) for label in APPLIANCES}.issubset(
            {name_key(label) for label,_ in recent}))

    def test_blank_optional_csv_fields_do_not_invalidate_pass(self):
        self.store.import_bytes(EXAMPLES,"usb")
        for row in self.store.slots("usb"):
            with self.subTest(slot=row["slot"]):
                _,report=self.store.create_report("1","Prüfgerät",PHASES[0],row,
                    examination={"visual":"Ohne Befund","functional":"Offen","examiner":""})
                self.assertEqual(result_kind(report),"PASS")
                self.assertEqual(electrical_check(report),("Messdaten vollständig",()))
                checks=dict(report_checks(report))
                self.assertIn("Funktionsbefund fehlt",checks["Protokoll"])
                self.assertIn("Prüfperson fehlt",checks["Protokoll"])
                self.assertNotIn("Grenzwert",checks["Protokoll"])
                self.assertIn("Nicht erfasst",checks["Freigabe"])
                self.assertIn(b"Funktionsbefund fehlt",receipt(report))
                self.assertEqual(report["record"]["verdict"],"bestanden")
                report["examination"].update(functional="Mangel",examiner="Muster",release="Nicht freigegeben")
                self.assertEqual(dict(report_checks(report))["Protokoll"],"Dokumentiert")
                self.assertEqual(dict(report_checks(report))["Funktion"],"Mangel")
                self.assertEqual(dict(report_checks(report))["Freigabe"],"Nicht freigegeben")

    def test_missing_required_measurement_and_voltage_mismatch_are_explained(self):
        self.store.import_bytes(EXAMPLES,"usb")
        _,report=self.store.create_report("1","Prüfgerät",PHASES[0],self.store.slots("usb")[0],
                                      examination={"voltage_confirmed":250})
        report["measurements"]=[row for row in report["measurements"] if row["name"]!="RISO"]
        checks=dict(report_checks(report))
        self.assertEqual(result_kind(report),"PASS")
        self.assertIn("RISO fehlt",checks["Elektrische Messung"])
        self.assertIn("Prüfspannung abweichend",checks["Protokoll"])


class WrappingTests(unittest.TestCase):
    def test_wraps_between_whole_words_with_nextion_breaks(self):
        source="Kaffeemaschine mit separatem Milchaufschäumer"
        result=word_lines(source,len,23,3,1,99)
        self.assertEqual(result.split("\r\n"),["Kaffeemaschine mit","separatem","Milchaufschäumer"])
        self.assertEqual(quote(result).count("\\r"),2)
        long="BeschreibungOhneTrennstelle"
        self.assertEqual(word_lines(long,len,8,5,1,99),"...")

    def test_every_guide_message_fits_at_actual_panel_width(self):
        for key,step in STEPS.items():
            for procedure,mode in (("I","Netz"),("II","Netz"),("III","Batterie"),("IEC","Batterie")):
                guide=Guide(step=key,procedure=procedure,mode=mode,observed="PASS")
                for text in (guide.instruction(),step.help):
                    with self.subTest(key=key,procedure=procedure,text=text):
                        result=fit("guide","gBody",text,230)
                        self.assertEqual(result.split(),text.split())

    def test_protocol_text_keeps_every_reason_when_paginated(self):
        paragraphs=["Protokoll offen: Messumfang nicht beurteilbar, Prüfergebnis widersprüchlich."]*6
        pages=paginate("report.tDetails",paragraphs)
        measure,width,height,font,limit,sy=bounds("report.tDetails")
        for page in pages:
            self.assertLessEqual(len(page),limit)
            self.assertLessEqual(len(page.split("\r\n"))*(font+sy)-sy,height)
            self.assertTrue(all(measure(line)<=width for line in page.split("\r\n")))
        self.assertEqual(" ".join(pages).split()," ".join(paragraphs).split())
