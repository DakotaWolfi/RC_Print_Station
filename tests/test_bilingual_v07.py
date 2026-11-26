"""v0.7 localisation, immutable snapshots and real native event regressions."""
from copy import deepcopy
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
import tempfile
import unittest

from benning_guide import Guide, STEPS
from benning_output import RESULTS, measurement_summary, report_language, result_kind
from benning_receiver import ReceiverStatus
from benning_store import Measurements, PHASES
from i18n import LANGUAGES, catalogue, error_text, tr
from native_ui import NativeUI
from operator_store import Operators
from panel_text import fit, printable
from report_web import render_pdf
from station import graphic_header, receipt, simulate
import station_config
from test_benning import EXAMPLES
from test_hmi_native import APP, PanelSerial, Simulation
from tools.printer_endpoint import resolve


class BilingualOutputs(unittest.TestCase):
    def test_complete_catalogue_and_guide_fit(self):
        invariant={"","Lo LOAD","PASS","FAIL","HIGH LOAD","FULL","StOP / hot","tAbLE / RPE"}
        for key,value in catalogue().items():
            placeholders=lambda text:{field for _,field,_,_ in Formatter().parse(text) if field}
            self.assertEqual(placeholders(key),placeholders(value),key)
        for step,screen in STEPS.items():
            for procedure in ("I","II","III","IEC","Verlängerung"):
                guide=Guide(step=step,procedure=procedure,observed="FAIL")
                for key in (screen.title,screen.instruction,screen.help,
                            *(label for label,_ in guide.choices())):
                    if key not in invariant:
                        self.assertIn(key,catalogue())
                for language in LANGUAGES:
                    items=[("gTitle",tr(language,screen.title)),
                           ("gBody",guide.instruction(language)),("gBody",tr(language,screen.help))]
                    choices=guide.choices()
                    items.extend((f"b{'Obs' if len(choices)>5 else 'Step'}{i}",tr(language,label))
                                 for i,(label,_) in enumerate(choices))
                    for field,value in items:
                        with self.subTest(language=language,step=step,field=field):
                            fitted=fit("guide",field,value,1000)
                            self.assertEqual(fitted.split(),printable(value).split())
        self.assertIn("Lo LOAD",tr("en",STEPS["low"].title))
        self.assertIn("I LEAK",tr("en",STEPS["leak"].title))
        self.assertIn("FAIL",Guide(step="save",observed="FAIL").instruction("en"))
        self.assertEqual(error_text("en","CSV-Zeile 3: Ungültige Prüfspannung."),
                         "CSV line 3: Invalid test voltage.")

    def test_reports_keep_language_raw_data_and_units(self):
        settings={"graphic":True,"density":"default","feed_mm":15}
        with tempfile.TemporaryDirectory() as tmp:
            store=Measurements(Path(tmp)/"reports.db")
            store.import_bytes(EXAMPLES,"usb")
            row=next(item for item in store.slots("usb") if item["slot"]=="005")
            people=Operators(store.db)
            examiner=people.rename("  Zoë  Muster ")
            exam={"examiner":people.active_name(examiner),"remarks":"  Mangel  am Griff  ",
                  "visual":"Ohne Befund","functional":"Ohne Befund"}
            for language in LANGUAGES:
                _,passed=store.create_report(" R-7 ","  Kaffeemaschine  Spezial  ",PHASES[0],
                                             row,examination=exam,examiner_id=examiner,language=language)
                self.assertEqual((passed["ticket"],passed["device"]),(" R-7 ","  Kaffeemaschine  Spezial  "))
                self.assertEqual(passed["examination"]["examiner"],"  Zoë  Muster ")
                self.assertEqual(passed["examination"]["remarks"],"  Mangel  am Griff  ")
                self.assertEqual(passed["record"]["voltage"],"500V")
                self.assertEqual(passed["record"]["tester_date"],"15/08/2026")
                self.assertEqual(passed["verdict"],"bestanden")
                self.assertIn("MOhm",[item["unit"] for item in passed["measurements"]])
                self.assertIn(("  Kaffeemaschine  Spezial  ",True),people.appliances(language))
                failed=deepcopy(passed)
                failed["record"]["verdict"]="nicht bestanden"
                unknown=deepcopy(passed)
                unknown["record"]["verdict"]=None
                _,incomplete=store.create_incomplete("R-8","Gerät",PHASES[0],exam,language=language)
                cases=(("PASS",passed),("FAIL",failed),("partial",incomplete),("unknown",unknown),
                       ("simulation",simulate("R-9","Muster",language=language)))
                for kind,report in cases:
                    with self.subTest(kind=kind,language=language):
                        self.assertEqual(report_language(report),language)
                        self.assertEqual(result_kind(report),kind)
                        artifact=receipt(report,settings)
                        suffix="-en" if language=="en" else ""
                        banner=(APP.parent/f"design/result-{kind}{suffix}.bin").read_bytes()
                        self.assertTrue(banner in artifact)
                        document=render_pdf(report)
                        self.assertIn(b"/Count 1",document)
                reading=receipt(passed,settings)
                self.assertTrue(graphic_header(language) in reading)
                self.assertNotEqual(graphic_header("de"),graphic_header("en"))
                self.assertTrue(b"0,17 \x1bt\x00\xea\x1bt\x02" in reading)
                self.assertTrue(b"500 V" in reading)
                self.assertTrue((b"15/08/2026" if language=="en" else b"15.08.2026") in reading)
                self.assertIn(("Coffee machine" if language=="en" else "Kaffeemaschine",False),
                              people.appliances(language))
        self.assertEqual(report_language({}),"de")
        value=measurement_summary({"name":"RISO","value":">2,1","unit":"MOhm",
                                   "limit":"0,5","limit_unit":"kOhm","result":"bestanden"},
                                  language="en")
        self.assertEqual(value,("RISO",">2,1 MΩ","0,5 kΩ","passed","PASS"))

    def test_printer_fallback_and_upgrade(self):
        with tempfile.TemporaryDirectory() as tmp:
            unit=Path(tmp)/"working.service"
            self.assertEqual(resolve(unit),("169.254.25.23",9100))
            unit.write_text("ExecStart=/usr/bin/python3 /opt/station/native_ui.py --host 169.254.223.252\n")
            self.assertEqual(resolve(unit),("169.254.25.23",9100))
            unit.write_text("ExecStart=/usr/bin/python3 /opt/station/native_ui.py --host=169.254.25.27 --printer-port 9200\n")
            self.assertEqual(resolve(unit),("169.254.25.27",9200))
            self.assertEqual(resolve(unit,"169.254.25.23",9100),("169.254.25.23",9100))


@unittest.skipIf(Simulation is None,"Install requirements-build.txt")
class NativeLanguages(unittest.TestCase):
    def test_ohm_slot_contains_the_actual_omega_bitmap(self):
        from nxwright.project.font_drawing import draw_font
        from nxwright.project.truetype import TrueTypeFont
        from nxwright.project.zi_font import decode_font

        original=APP.parent/"design/typeface/NotoSans-Regular.ttf"
        typeface=TrueTypeFont(original.read_bytes())
        expected=next(glyph for glyph in draw_font(typeface,20,"utf-8",characters=[ord("Ω")])
                      if glyph.code==ord("Ω"))
        font=decode_font((APP/"fonts/UI20.zi").read_bytes())
        actual=font.characters[0xad]
        self.assertEqual(printable("Ω kΩ MΩ").encode("iso-8859-15"),b"\xad k\xad M\xad")
        self.assertEqual((actual.advance,tuple(actual.coverages())),(expected.advance,expected.coverages))

    def test_language_switch_preserves_active_draft_and_report_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            out=bytearray()
            panel=Simulation(APP,sending=out.extend)
            receiver=SimpleNamespace(mode="simulation",status=ReceiverStatus("simulation"),close=lambda:None)
            with self.subTest("draft"):
                ui=NativeUI(PanelSerial(panel),"printer",root/"reports.db",
                            config_path=root/"settings.json",tester_receiver=receiver)
                self.addCleanup(ui.close)

                def pump():
                    for _ in range(12):
                        chunk=bytes(out)
                        out.clear()
                        if not chunk:
                            return
                        ui.feed(chunk)
                    self.fail("UART did not settle")

                def tap(name):
                    comp=next(item for item in panel.components() if item.name==name)
                    values=comp.values
                    panel.press(name,values["x"]+values["w"]//2,values["y"]+values["h"]//2)
                    panel.release()
                    pump()

                pump()
                self.assertEqual(ui.language,"de")
                tap("bDirect")
                panel.serial_input('tTicket.txt="R-7"')
                panel.serial_input('tDevice.txt="  Kaffeemaschine  Spezial "')
                tap("bBack")
                tap("bLang")
                self.assertEqual(station_config.load(root/"settings.json")["language"],"en")
                self.assertEqual(panel.values()["lang.val"],1)
                tap("bResume")
                self.assertEqual(panel.values()["tDevice.txt"],"  Kaffeemaschine  Spezial ")
                self.assertEqual(panel.values()["bReportLang.txt"],"Report: EN")
                tap("bReportLang")
                self.assertEqual(panel.values()["bReportLang.txt"],"Report: DE")
                tap("bCreate")
                self.assertEqual(ui.report["language"],"de")
                self.assertEqual(ui.report["device"],"  Kaffeemaschine  Spezial ")
                self.assertEqual(ui.language,"en")
                self.assertEqual(panel.values()["inProgress.val"],0)
                new=NativeUI(PanelSerial(panel),"printer",root/"reports.db",
                             config_path=root/"settings.json",tester_receiver=receiver)
                self.addCleanup(new.close)
                self.assertEqual(new.language,"en")
