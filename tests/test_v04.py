from pathlib import Path
import json
import tempfile
import threading
import time
import unittest

import station_config as config
from station_network import Network, NetworkError, NetworkManager, access_point
from native_ui import NativeUI, ENCODING, END
from station import receipt,simulate,graphic_header
try:
    from nxwright.testing.simulation import Simulation
except ImportError:
    Simulation=None

APP=Path(__file__).resolve().parents[1]/"hmi/native"


class SettingsTests(unittest.TestCase):
    def test_migrate_existing_receipt_settings_and_merge_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"receipt.json"
            p.write_text(json.dumps({"graphic":False,"feed_mm":47,"future":123}))
            self.assertEqual(config.load(p)["density"],"default")
            config.save({"printer_host":"169.254.223.252","printer_port":9101},p)
            config.save({"graphic":True,"feed_mm":50,"density":"light"},p)
            self.assertEqual(config.load(p)["printer_port"],9101)
            self.assertEqual(json.loads(p.read_text())["future"],123)
            for bad in ({"printer_port":0},{"printer_host":"255.255.255.255"},{"standby":5},
                        {"brightness":1},{"graphic":1},{"density":"arbitrary"}):
                before=p.read_bytes()
                with self.assertRaises(ValueError):
                    config.save(bad,p)
                self.assertEqual(p.read_bytes(),before)

    def test_receipt_bytes_and_opt_in_density(self):
        r=simulate("T1","Prüflampe")
        default=receipt(r,config.DEFAULTS)
        self.assertIn(graphic_header(),default)
        self.assertTrue(default.endswith(b"\x1bJ\xf0\x1bJ\x78\x1dV\x00"))
        s=dict(config.DEFAULTS,density="light",feed_mm=10,graphic=False)
        data=receipt(r,s)
        self.assertNotIn(graphic_header(),data)
        self.assertTrue(data.startswith(b"\x1b@\x1d(K\x02\x001\xff"))
        self.assertTrue(data.endswith(b"\x1bJP\x1dV\x00"))
        self.assertIn(b"SIMULATION ONLY",data)

    def test_ap_binary_ssid_classification_and_safe_password_rejection(self):
        attrs=dict(Ssid=b"Landauer:Test\\Net",Flags=1,WpaFlags=0,RsnFlags=0x500,Strength=73)
        self.assertEqual(access_point("/ap",attrs),Network("/ap",attrs["Ssid"],73,"WPA2/3","wpa-psk"))
        self.assertEqual(access_point("/ap",dict(attrs,RsnFlags=0x400)).key_mgmt,"sae")
        self.assertIsNone(access_point("/ap",dict(attrs,RsnFlags=0x200)).key_mgmt)
        self.assertEqual(access_point("/ap",dict(attrs,RsnFlags=0,Flags=0)).key_mgmt,"")
        try:
            NetworkManager().connect(access_point("/ap",attrs),"x\nSECRET")
        except NetworkError as exc:
            self.assertNotIn("SECRET",str(exc))
        else:
            self.fail("Invalid WLAN credential accepted")


class FakeNetwork:
    def __init__(self):
        self.started=threading.Event()
        self.release=threading.Event()
        self.current=("","")
        self.password=None

    def status(self):
        return self.current

    def scan(self):
        return [Network("/ap0",b"Werkstatt",82,"WPA2","wpa-psk"),
                Network("/ap1",b"Gast",68,"Offen",""),
                Network("/ap2",b"Enterprise",48,"802.1X",None),
                Network("/ap3",b"Vier",44,"Offen",""),
                Network("/ap4",b"Fuenf",42,"Offen","")]

    def connect(self,net,password):
        self.password=password
        self.started.set()
        if not self.release.wait(5):
            raise NetworkError("Test timeout")
        self.current=(net.name,"192.168.1.53")
        return self.current


class Serial:
    baudrate=115200

    def __init__(self,panel):
        self.panel=panel

    def write(self,data):
        for frame in data.split(END):
            if frame:
                self.panel.serial_input(frame.decode(ENCODING))
        return len(data)

    def flush(self):
        pass


@unittest.skipIf(Simulation is None,"Install requirements-build.txt")
class TouchSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.out=bytearray()
        self.panel=Simulation(APP,sending=self.out.extend)
        self.network=FakeNetwork()
        self.printed=[]
        self.probes=[]
        self.actions=[]
        self.ui=NativeUI(Serial(self.panel),"169.254.223.252",Path(self.tmp.name)/"reports.db",
            network=self.network,config_path=Path(self.tmp.name)/"receipt.json",enable_power=True,
            sender=lambda *args:self.printed.append(args), probe_fn=lambda *args:self.probes.append(args),
            power_fn=self.actions.append)
        self.ui.auto_port=8080
        self.pump()

    def tearDown(self):
        self.network.release.set()
        self.ui.close()
        self.tmp.cleanup()

    def pump(self):
        for _ in range(12):
            data=bytes(self.out)
            self.out.clear()
            if not data:
                return
            self.ui.feed(data)
        self.fail("UART did not settle")

    def tap(self,name,pump=True):
        cmp=next(c for c in self.panel.components() if c.name==name)
        v=cmp.values
        x,y=v["x"]+v["w"]//2,v["y"]+v["h"]//2
        self.assertEqual(self.panel.component_at(x,y),name)
        self.panel.press(name,x,y)
        self.panel.release()
        if pump:
            self.pump()

    def page(self,p):
        self.panel.serial_input("page "+p)
        self.pump()

    def val(self,name):
        return self.panel.values()[name]

    def key(self,char):
        cmp=next(c for c in self.panel.components()
                 if c.name.startswith("k") and c.type=="button" and c.values["txt"]==char)
        self.tap(cmp.name)

    def wait_jobs(self):
        for _ in range(100):
            self.ui.tick()
            self.pump()
            jobs=(self.ui.settings.job,self.ui.settings.printer_probe,self.ui.print_job,self.ui.settings.power_job)
            if not any(jobs):
                return
            time.sleep(.01)
        self.fail("Jobs did not finish")

    def test_scan_pages_mask_clear_connect_and_qr_refresh_while_printing(self):
        self.tap("bSettings")
        self.tap("bwifi")
        self.tap("bScan")
        self.wait_jobs()
        self.assertEqual(self.val("wCount.val"),4)
        self.assertIn("82% WPA2 | Werkstatt",self.val("wRow0.txt"))
        self.tap("bNext")
        self.assertIn("Fuenf",self.val("wRow0.txt"))
        self.tap("bPrev")
        self.tap("wRow0")
        self.tap("bJoin")
        for c in "secret42":
            self.key(c)
        self.assertEqual(self.val("input.txt"),"********")
        self.tap("bCancel")
        self.tap("bJoin")
        self.assertEqual(self.val("secret.txt"),"")
        self.assertEqual(self.val("input.txt"),"")
        for c in "secret42":
            self.key(c)
        self.tap("bOK")
        self.assertTrue(self.network.started.wait(1))
        self.assertIn("warte auf IP",self.val("jStatus.txt"))
        self.assertEqual(self.network.password,"secret42")
        self.ui.last_heartbeat=float("-inf")
        self.ui.tick()
        self.assertGreater(self.ui.last_heartbeat,0)
        self.page("printer")
        self.tap("bTest")
        self.assertIsNotNone(self.ui.print_job)
        self.network.release.set()
        self.wait_jobs()
        self.assertEqual(self.ui.base_url,"http://192.168.1.53:8080")
        self.assertIn(b"KEINE ELEKTRISCHE",self.printed[0][2])
        self.tap("bBack")
        self.tap("bwifi")
        self.assertIn("Werkstatt / 192.168.1.53",self.val("wCurrent.txt"))
        self.ui.load_report(1,simulate("T","Prüflampe"))
        self.page("qrpage")
        self.assertIn("192.168.1.53",self.val("qrReport.txt"))
        self.ui.settings.set_status("Other","192.168.0.19")
        self.pump()
        self.assertIn("192.168.0.19",self.val("qrReport.txt"))
        self.ui.settings.set_status("","")
        self.pump()
        self.assertEqual(self.val("qReady.val"),2)

    def test_printer_edit_probe_receipt_and_display_persistence(self):
        self.page("printer")
        self.tap("bPort")
        self.tap("bClear")
        for c in "9201":
            self.key(c)
        self.tap("bOK")
        self.assertEqual(self.val("pPort.txt"),"9201")
        self.tap("bHost")
        self.tap("bClear")
        for c in "10.88.77.30":
            self.key(c)
        self.tap("bOK")
        self.tap("bProbe")
        self.wait_jobs()
        self.assertEqual(self.probes,[("10.88.77.30",9201)])
        self.assertIn("erfolgreich",self.val("pStatus.txt"))
        self.page("receipt")
        self.tap("rGraphic")
        self.tap("bFeedUp")
        self.tap("rDensity")
        self.page("printer")
        self.tap("bTest")
        self.wait_jobs()
        host,port,data=self.printed[0]
        self.assertEqual((host,port),("10.88.77.30",9201))
        self.assertNotIn(graphic_header(),data)
        self.assertTrue(data.endswith(b"\x1bJ\xf0\x1bJ\xa0\x1dV\x00"))
        self.page("system")
        self.tap("bBrightDown")
        self.tap("bStand")
        self.assertEqual((self.val("dim"),self.val("thsp")),(90,30))
        self.assertEqual(self.ui.settings.cfg()["brightness"],90)

    def test_power_requires_confirmation_page_opt_in_and_time_limit(self):
        self.page("system")
        self.ui.handle(b"RC4:HALT")
        self.assertEqual(self.actions,[])
        self.tap("bPower")
        self.tap("bCancel")
        self.assertEqual(self.actions,[])
        self.tap("bPower")
        self.ui.settings.armed_until=time.monotonic()-1
        self.tap("bREBOOT")
        self.assertEqual(self.actions,[])
        self.page("system")
        self.ui.settings.enable_power=False
        self.tap("bPower")
        self.tap("bHALT")
        self.assertEqual(self.actions,[])
        self.page("system")
        self.ui.settings.enable_power=True
        self.tap("bPower")
        self.tap("bREBOOT")
        self.wait_jobs()
        self.assertEqual(self.actions,["REBOOT"])
