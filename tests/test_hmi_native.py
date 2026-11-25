"""Execute the real generated native events, joined to the Python backend.

Needs the pinned development toolchain, not the panel or a printer.
"""
from pathlib import Path
import tempfile
import unittest

try:
    from nxwright.testing.simulation import Simulation
except ImportError:
    Simulation = None
from native_ui import END, ENCODING, NativeUI
from station import receipt

APP = Path(__file__).resolve().parents[1]/"hmi/native"


class PanelSerial:
    baudrate = 115200

    def __init__(self,panel):
        self.panel=panel

    def write(self,data):
        for command in data.split(END):
            if command:
                self.panel.serial_input(command.decode(ENCODING))
        return len(data)

    def flush(self):
        pass


@unittest.skipIf(Simulation is None,"Install requirements-build.txt for native event tests")
class NativeFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = bytearray()
        self.panel = Simulation(APP,sending=self.out.extend)
        self.printed = []
        self.ui = NativeUI(PanelSerial(self.panel),"epson",Path(self.tmp.name)/"reports.db",
            base_url="http://192.168.1.42:8080",sender=lambda *a:self.printed.append(a))
        self.pump()

    def tearDown(self):
        self.ui.close()
        self.tmp.cleanup()

    def pump(self):
        for _ in range(10):
            data=bytes(self.out)
            self.out.clear()
            if not data:
                break
            self.ui.feed(data)
        else:
            self.fail("Serial exchange did not settle")

    def tap(self,name):
        component=next(c for c in self.panel.components() if c.name==name)
        x=component.values["x"]+component.values["w"]//2
        y=component.values["y"]+component.values["h"]//2
        target=self.panel.component_at(x,y)
        self.assertEqual(target,name)
        self.panel.press(target,x,y)
        self.panel.release()

    def value(self,name):
        return self.panel.values()[name]

    def open_keyboard(self,field="device"):
        self.tap("bNew")
        self.tap("hEdit1" if field=="device" else "hEdit0")
        self.assertEqual(self.panel.page,"keybdA")

    def key(self,char):
        match=next(c for c in self.panel.components()
                   if c.name.startswith("k") and c.type=="button" and c.values["txt"]==char)
        self.tap(match.name)

    def test_typing_shift_caps_umlauts_symbols_cancel_and_backspace(self):
        self.open_keyboard()
        self.key("q")
        self.key("z")
        self.key("y")
        self.tap("bShift")
        self.key("Ä")
        self.assertEqual(self.value("shift.val"),0)
        self.key("ö")
        self.tap("bCaps")
        self.key("Ü")
        self.key("1")
        self.tap("bCaps")
        self.tap("bMode")
        for char in ("@","€",'"',"\\"):
            self.key(char)
        self.tap("bDel")
        self.assertEqual(self.value("input.txt"),'qzyÄöÜ1@€"')
        self.tap("bOK")
        self.assertEqual(self.panel.page,"entry")
        self.assertEqual(self.value("tDevice.txt"),'qzyÄöÜ1@€"')
        self.tap("hEdit1")
        self.tap("bClear")
        self.tap("bCancel")
        self.assertEqual(self.value("tDevice.txt"),'qzyÄöÜ1@€"')

    def test_native_field_limits_and_empty_backspace(self):
        self.open_keyboard("ticket")
        self.tap("bDel")
        for _ in range(36):
            self.key("x")
        self.assertEqual(self.value("input.txt"),"x"*32)
        self.tap("bOK")
        self.assertEqual(self.value("tTicket.txt"),"x"*32)
        self.tap("hEdit1")
        for _ in range(68):
            self.key("w")
        self.assertEqual(self.value("input.txt"),"w"*64)

    def test_full_native_create_print_download_history_flow(self):
        self.tap("bNew")
        self.panel.serial_input('tTicket.txt="RC-17"')
        self.ui.text("entry.tDevice",'Mühle "Spezial" \\ 12 €',64)
        self.tap("bCreate")
        self.assertEqual(self.panel.page,"entry")
        self.pump()
        self.panel.advance(200)
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.value("tDevice.txt"),'Mühle "Spezial" \\ 12 €')
        self.tap("bPrint")
        self.tap("bPrint")
        self.pump()
        self.ui.close()
        self.ui.finish_print()
        self.pump()
        self.assertEqual(len(self.printed),1)
        self.assertEqual(self.printed[0][2],receipt(self.ui.report))
        self.tap("bQR")
        self.assertEqual(self.panel.page,"qrpage")
        self.assertIn("qrReport",self.panel.hidden())
        self.pump()
        self.panel.advance(200)
        self.assertNotIn("qrReport",self.panel.hidden())
        self.assertTrue(self.value("qrReport.txt").startswith("http://192.168.1.42:8080/r/"))
        self.tap("bBack")
        self.tap("bHome")
        self.tap("bHistory")
        self.pump()
        self.assertIn("RC-17",self.value("bRow0.txt"))
        self.tap("bRow0")
        self.pump()
        self.panel.advance(200)
        self.assertEqual(self.panel.page,"report")
        self.assertEqual(self.value("tTicket.txt"),"RC-17")
        errors=[line for _,line in self.panel.log if "refused" in line.lower() or "error" in line.lower()]
        self.assertEqual(errors,[])

    def test_host_disconnect_keeps_native_editing_and_blocks_submission(self):
        self.open_keyboard()
        self.key("ä")
        self.panel.advance(8000)
        self.assertEqual(self.value("home.online.val"),0)
        self.key("ü")
        self.tap("bOK")
        self.assertEqual(self.value("tDevice.txt"),"äü")
        self.panel.serial_input('tTicket.txt="RC-1"')
        self.tap("bCreate")
        self.pump()
        self.assertIsNone(self.ui.report)
        self.assertIn("nicht verbunden",self.value("tStatus.txt"))


if __name__=="__main__":
    unittest.main()
