"""Run separately with /usr/bin/python3 and QT_QPA_PLATFORM=offscreen."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QPushButton
except ImportError:
    QApplication=None

from benning_receiver import ReceiverStatus
from slogan_store import SloganStore
from station_core import StationCore


@unittest.skipIf(QApplication is None,"Install python3-pyqt5 to test the HDMI frontend")
class QtSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication([])

    def setUp(self):
        from hdmi_frontend import Surface
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        path=Path(temp.name)
        receiver=SimpleNamespace(mode="file",status=ReceiverStatus("file"),
                                 start=lambda:None,close=lambda:None)
        self.core=StationCore(path/"r.sqlite3",receiver=receiver,config_path=path/"settings.json",
                              cache=SloganStore(path/"slogans.sqlite3"))
        self.addCleanup(self.core.close)
        self.surface=Surface(preview=True)
        self.surface.preview=False
        self.surface.show()
        self.addCleanup(self.surface.close)
        self.sync()

    def sync(self):
        self.surface.show_state(self.core.snapshot())
        self.app.processEvents()

    def queued(self):
        packet,callback=self.surface.outgoing.popleft()
        source=packet.pop("client")
        result=self.core.command(packet,source)
        self.assertTrue(result["ok"],result)
        if callback:
            callback(result["data"])
        self.sync()

    def click(self,text):
        b=next(item for item in self.surface.findChildren(QPushButton)
               if item.text()==text and item.isVisible())
        QTest.mouseClick(b,Qt.LeftButton)

    def test_submit_semantics_and_shared_language(self):
        self.click("Geführte Prüfung")
        self.queued()
        d=self.core.draft
        self.surface.edit("ticket","","QT-42")
        self.queued()
        owner=d["id"]
        self.core.command({"op":"draft.edit","args":{"draft":owner,"previous":{"device":""},
                           "changes":{"device":"HDMI + Nextion"}}},"nextion")
        self.sync()
        self.click("Bericht: DE")
        self.queued()
        self.click("DE / EN")
        self.queued()
        self.assertEqual(self.core.report_language(),"en")
        self.click("Report: EN")
        self.queued()
        self.assertEqual((self.core.language,self.core.report_language()),("en","de"))
        self.assertEqual((self.core.draft["ticket"],self.core.draft["device"]),("QT-42","HDMI + Nextion"))

    def test_reflow_at_four_sizes_and_wraps_long_input(self):
        self.core.command({"op":"draft.new","args":{"mode":"direct"}})
        self.sync()
        d=self.core.draft
        self.surface.edit("device","","Gerätebeschreibung mit vielen Worten für das schmale Display")
        self.queued()
        for width,height in ((800,480),(480,800),(1024,600),(600,1024)):
            self.surface.resize(width,height)
            self.app.processEvents()
            self.surface.render()
            self.app.processEvents()
            btn=next(item for item in self.surface.scroll.widget().findChildren(QPushButton)
                     if item.text().startswith("Gerätebeschreibung"))
            self.assertGreaterEqual(btn.height(),48)
            self.assertEqual(self.surface.scroll.horizontalScrollBar().maximum(),0)
            self.assertGreaterEqual(btn.height(),btn.heightForWidth(btn.width()))

    def test_professional_mode_hides_pet(self):
        self.core.command({"op":"settings.save","args":{"values":{"professional":True}}})
        self.sync()
        for _ in range(5):
            self.surface.pet_gate()
        self.assertEqual(self.surface.view,"work")
        self.assertIsNone(self.surface.state["personality"]["slogan"])
