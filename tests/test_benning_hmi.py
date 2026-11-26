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

    def draft(self):
        self.tap("bNew")
        self.panel.serial_input('tTicket.txt="R-15"')
        self.panel.serial_input('tDevice.txt="Kaffeemühle"')

    def test_requires_confirmation_for_first_import_and_pass_survives(self):
        self.draft()
        self.assertEqual(self.value("cLast.val"),1)
        self.tap("bCreate")
        self.assertEqual(self.panel.page,"tester")
        self.assertEqual(self.value("mReady.val"),0)
        first=self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.receiver.status=ReceiverStatus("imported","usb",len(EXAMPLES),batch=first.batch)
        self.ui.tester.poll()
        self.pump()
        self.assertEqual(self.value("mReady.val"),1)
        self.tap("bBack")
        self.assertEqual(self.value("tSlot.txt"),"033")
        self.tap("bCreate")
        self.assertIn("Reihenfolge unklar",self.value("mNote.txt"))
        self.assertIn("033",self.value("mSelected.txt"))
        self.assertIsNone(self.ui.report)
        self.tap("bUse")
        self.panel.advance(200)
        self.pump()
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.value("tResult.txt"),"Tester: bestanden")
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
        change=self.ui.measurements.import_bytes(wire([EXAMPLE_ROWS[0],single_failure(),EXAMPLE_ROWS[2]]),"usb")
        self.receiver.status=ReceiverStatus("imported","usb",batch=change.batch)
        self.tap("bCreate")
        self.assertIn("Ein Slot seit",self.value("mNote.txt"))
        self.tap("bUse")
        self.panel.advance(200)
        self.pump()
        self.assertEqual(self.ui.report["phase"],"Zwischenprüfung")
        self.assertEqual(self.ui.report["verdict"],"nicht bestanden")

    def test_new_import_invalidates_displayed_selected_version(self):
        self.ui.measurements.import_bytes(EXAMPLES,"usb")
        self.draft()
        self.tap("bCreate")
        self.assertEqual(self.value("mReady.val"),1)
        update=self.ui.measurements.import_bytes(wire([EXAMPLE_ROWS[0],EXAMPLE_ROWS[1],single_failure("033")]),"usb")
        self.receiver.status=ReceiverStatus("imported","usb",batch=update.batch)
        self.tap("bUse")
        self.assertIsNone(self.ui.report)
        self.assertEqual(self.value("mReady.val"),0)
