"""Native slot confirmation, measured report and existing keyboard actions."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from native_ui import NativeUI
from benning_receiver import ReceiverStatus
from test_benning import EXAMPLES, EXAMPLE_ROWS, single_failure, wire
from test_hmi_native import APP, PanelSerial, Simulation


@unittest.skipIf(Simulation is None,"Install requirements-build.txt")
class BenningTouchTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.out=bytearray()
        self.panel=Simulation(APP,sending=self.out.extend)
        self.receiver=SimpleNamespace(mode="usb",status=ReceiverStatus("waiting",source="usb"),
                                      close=lambda:None)
        self.ui=NativeUI(PanelSerial(self.panel),"printer",Path(tmp.name)/"reports.db",
                         tester_receiver=self.receiver)
        self.addCleanup(self.ui.close)
        self.pump()

    def pump(self):
        for _ in range(12):
            data=bytes(self.out)
            self.out.clear()
            if not data:
                return
            self.ui.feed(data)
        self.fail("UART did not settle")

    def tap(self,name):
        comp=next(c for c in self.panel.components() if c.name==name)
        v=comp.values
        x,y=v["x"]+v["w"]//2,v["y"]+v["h"]//2
        self.assertEqual(self.panel.component_at(x,y),name)
        self.panel.press(name,x,y)
        self.panel.release()
        self.pump()

    def value(self,name):
        return self.panel.values()[name]

    def draft(self,guided=False):
        self.tap("bNew" if guided else "bDirect")
        self.panel.serial_input('tTicket.txt="R-15"')
        self.panel.serial_input('tDevice.txt="Kaffeemühle"')

    def settle(self):
        self.panel.advance(200)
        self.pump()

    def imported(self,data):
        result=self.ui.measurements.import_bytes(data,"usb")
        self.receiver.status=ReceiverStatus("imported","usb",len(data),batch=result.batch)
        self.ui.tick()
        self.pump()
        return result

    def test_first_export_requires_manually_confirming_a_slot(self):
        self.draft()
        self.assertEqual(self.value("cLast.val"),1)
        self.tap("bCreate")
        self.settle()
        self.assertEqual(self.panel.page,"importer")
        self.assertIn("Alle Leitungen",self.value("iBody.txt"))
        self.imported(EXAMPLES)
        self.settle()
        self.assertEqual(self.panel.page,"importer")
        self.assertIn("Erster Import",self.value("iMessage.txt"))
        self.tap("bManual")
        self.settle()
        self.assertEqual(self.panel.page,"tester")
        self.assertEqual(self.value("mReady.val"),0)
        self.tap("mRow0")
        self.assertIn("033",self.value("mSelected.txt"))
        self.tap("bUse")
        self.settle()
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.value("tResult.txt"),"BESTANDEN")
        self.assertEqual(self.ui.report["record"]["tester_date"],"14/11/2026")

    def test_manual_slot_entry_and_explicit_phase_after_overwrite(self):
        self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.draft()
        self.tap("cLast")
        self.assertEqual(self.value("cLast.val"),0)
        self.tap("hEdit2")
        self.assertEqual(self.panel.page,"keyboard")
        self.panel.serial_input('input.txt="005"')
        self.tap("bOK")
        self.assertEqual(self.value("tSlot.txt"),"005")
        self.tap("bPhase")
        self.imported(wire([EXAMPLE_ROWS[0],single_failure(),EXAMPLE_ROWS[2]]))
        self.tap("bTester")
        self.settle()
        self.assertIn("Vorhandenes Testergebnis",self.value("mNote.txt"))
        self.tap("bUse")
        self.settle()
        self.assertEqual(self.ui.report["phase"],"Zwischenprüfung")
        self.assertEqual(self.ui.report["verdict"],"nicht bestanden")
        self.assertEqual(self.value("tResult.txt"),"NICHT BESTANDEN")

    def test_fresh_import_advances_but_an_overwrite_invalidates_selection(self):
        self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.draft()
        self.tap("bCreate")
        self.settle()
        self.assertEqual(self.panel.page,"importer")
        self.imported(wire([EXAMPLE_ROWS[0],EXAMPLE_ROWS[1],single_failure("033")]))
        # The heartbeat can run before the native transition timer.
        self.ui.tick()
        self.settle()
        self.assertEqual(self.panel.page,"tester")
        self.assertIn("Neuer Datensatz",self.value("mNote.txt"))
        self.assertEqual(self.value("mReady.val"),1)
        self.imported(EXAMPLES)
        self.tap("bUse")
        self.assertIsNone(self.ui.report)
        self.assertEqual(self.value("mReady.val"),0)

    def test_ambiguous_import_and_error_remain_on_wait_page(self):
        self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.draft()
        self.tap("bCreate")
        self.settle()
        self.receiver.status=ReceiverStatus("error","usb",detail="CSV ungültig")
        self.ui.tick()
        self.assertIn("ungültig",self.value("iStatus.txt"))
        self.imported(wire([single_failure("001"),single_failure(),EXAMPLE_ROWS[2]]))
        self.settle()
        self.assertEqual(self.panel.page,"importer")
        self.assertIn("Mehrere Änderungen",self.value("iMessage.txt"))
        self.tap("bBack")
        self.settle()
        self.assertEqual(self.panel.page,"entry")
        self.assertEqual(self.value("tTicket.txt"),"R-15")

    def test_guided_visual_failure_persists_a_separate_incomplete_examination(self):
        self.draft(guided=True)
        self.tap("bCreate")
        self.settle()
        self.assertEqual(self.panel.page,"guide")
        self.tap("bHelp")
        self.assertIn("Aufsicht",self.value("gBody.txt"))
        self.tap("bStep1")
        self.tap("bBack")
        self.assertEqual(self.ui.workflow.guide.step,"stop")
        self.tap("bStep0")
        self.assertEqual(self.ui.workflow.guide.step,"exam")
        self.tap("bName")
        self.assertEqual(self.panel.page,"keyboard")
        self.panel.serial_input('input.txt="Prüfperson Test"')
        self.tap("bOK")
        self.assertEqual(self.panel.page,"guide")
        self.tap("gProceed")
        self.settle()
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.value("tResult.txt"),"UNVOLLSTÄNDIG")
        self.assertEqual(self.ui.report["examination"]["visual"],"Mangel oder ungeklärt")
        self.assertEqual(self.ui.report["examination"]["examiner"],"Prüfperson Test")
        self.assertIsNone(self.ui.report["verdict"])

    def test_guided_cancel_retains_repair_draft(self):
        self.draft(guided=True)
        self.tap("bCreate")
        self.settle()
        self.tap("bCancel")
        self.settle()
        self.assertEqual(self.panel.page,"entry")
        self.assertEqual(self.value("tTicket.txt"),"R-15")
        self.assertIsNone(self.ui.workflow.guide)
        self.assertIsNone(self.ui.report)
        self.tap("bCreate")
        self.settle()
        self.assertEqual(self.ui.workflow.guide.step,"visual")

    def test_guided_new_fail_must_match_the_observed_result_and_class(self):
        self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.draft(guided=True)
        self.tap("bCreate")
        self.settle()
        # Class I, battery, connection, voltage, start, FAIL, save and STORE.
        for option in (0,0,0,0,0,0,1,0,0):
            self.tap(f"bStep{option}")
        self.panel.serial_input('eName.txt="Prüfperson Test"')
        self.tap("gFunction")
        self.tap("gProceed")
        self.settle()
        self.assertEqual(self.panel.page,"importer")
        self.imported(wire([EXAMPLE_ROWS[0],single_failure(),EXAMPLE_ROWS[2]]))
        self.settle()
        self.tap("mRow0")  # PASS from Class II must not attach to this FAIL.
        self.tap("bUse")
        self.assertIsNone(self.ui.report)
        self.assertIn("weicht",self.value("mNote.txt"))
        self.tap("mRow1")
        self.tap("bUse")
        self.settle()
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.ui.report["verdict"],"nicht bestanden")
        self.assertEqual(self.ui.report["examination"]["observed"],"FAIL")
        self.assertEqual(self.ui.report["examination"]["functional"],"Ohne Befund")
