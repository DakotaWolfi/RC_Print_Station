"""Exercise the native frontend through real Qt events and station commands."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, skipIf

try:
    from PyQt5.QtCore import Qt, QPoint, QPointF
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QPushButton
except ImportError:
    QApplication=None

from benning_receiver import ReceiverStatus
from slogan_store import SloganStore
from station_core import StationCore


@skipIf(QApplication is None,"Install PyQt5 with system Python")
class HDMIFlow(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from hdmi_frontend import Surface, RotatedSurface
        from display_rotation import Rotation
        self.temp=TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name)
        self.rx=SimpleNamespace(mode="usb",status=ReceiverStatus("waiting","usb"),close=lambda:None)
        self.prints=[]
        self.core=StationCore(root/"bench.db",receiver=self.rx,config_path=root/"settings.json",
                              cache=SloganStore(root/"pets.db"),sender=lambda *args:self.prints.append(args),
                              base_url="http://192.168.9.221:8080")
        self.addCleanup(self.core.close)
        self.core.operators.rename("Bench Operator")
        self.commands=[]
        def transport(_,packet):
            self.commands.append(packet.copy())
            packet=packet.copy()
            source=packet.pop("client")
            return self.core.command(packet,source)
        self.surface=Surface(transport=transport)
        self.window=RotatedSurface(self.surface,0)
        self.surface.rotation=Rotation("HDMI-A-1",self.window.change_rotation,path=root/"rotation.json")
        self.window.resize(480,800)
        self.window.show()
        self.addCleanup(self.window.close)
        self.wait(lambda:bool(self.surface.state))

    def wait(self,check):
        for _ in range(120):
            self.core.tick()
            QTest.qWait(25)
            if check():
                return
        self.fail(f"Timeout. Page={self.surface.view}, stage={self.core.phase}, "
                  f"guide={getattr(self.core.guide,'step',None)} error={self.surface.notice}")

    def button(self,prefix):
        return next((b for b in self.surface.findChildren(QPushButton)
                     if b.isVisible() and b.isEnabled() and b.text().startswith(prefix)),None)

    def click(self,prefix):
        self.wait(lambda:self.button(prefix) is not None)
        item=self.button(prefix)
        if not self.surface.overlay and self.surface.scroll.isAncestorOf(item):
            self.surface.scroll.ensureWidgetVisible(item)
        self.app.processEvents()
        point=self.window.mapFromScene(self.window.proxy.mapToScene(item.mapTo(self.surface,item.rect().center())))
        QTest.mouseClick(self.window.viewport(),Qt.LeftButton,pos=point)
        return item

    def enter(self,prefix,value):
        self.click(prefix)
        self.wait(lambda:self.surface.overlay is not None)
        editor=self.surface.overlay
        self.assertFalse(editor.isWindow())
        QTest.keyClicks(editor.edit,value)
        self.click("Übernehmen")
        self.wait(lambda:self.surface.overlay is None)

    def test_complete_examination_with_real_clicks_and_print(self):
        self.click("Geführte Prüfung")
        self.wait(lambda:self.core.phase=="entry")
        self.enter("Prüfnummer","V082-01")
        self.enter("Gerätebeschreibung","Bench kettle")
        self.click("Prüfart")
        self.wait(lambda:self.surface.overlay is not None)
        self.assertFalse(self.button("Prüfung beginnen"))
        self.click("Ausgangsprüfung")
        self.wait(lambda:self.core.draft["phase"]==2)
        self.click("Prüfung beginnen")
        self.click("Ohne Befund")
        self.wait(lambda:self.core.guide.step=="kind")
        choice=next(x for x in self.commands if x["op"]=="guide.choose")
        self.assertIs(type(choice["args"]["choice"]),int)
        self.click("Schutzklasse I")
        self.click("Netz + 500 V geprüft")
        self.click("Hilfe")
        self.wait(lambda:self.surface.overlay is not None)
        self.assertFalse(self.button("PASS"))
        self.click("Schliessen")
        self.click("Lo LOAD")
        self.click("Geringe Last bestätigt")
        self.click("I LEAK blinkt")
        self.click("Sicherheit bestätigt")
        self.click("PASS")
        self.click("STORE + Slot gesehen")
        self.click("Prüfperson")
        self.click("Bench Operator")
        self.click("Funktion")
        self.click("Ohne Befund")
        self.click("Zum Import")
        self.wait(lambda:self.core.phase=="waiting")
        from test_benning import RS232
        self.rx.mode="rs232"
        self.rx.status=ReceiverStatus("waiting","rs232")
        self.core.refresh_import()
        result=self.core.store.import_bytes(RS232,"rs232")
        self.rx.status=ReceiverStatus("imported","rs232",batch=result.batch)
        self.wait(lambda:self.surface.state.get("draft",{}).get("stage") in ("waiting","review"))
        if self.core.phase=="waiting":
            self.click("Vorhandene Messung")
        if not self.core.selected:
            self.click("012")
        self.click("Messung bestätigen")
        self.wait(lambda:self.core.phase=="report")
        self.click("PDF / QR-Code")
        self.wait(lambda:self.surface.url.startswith("http"))
        self.assertEqual(self.surface.view,"download")
        self.assertIsNone(self.button("PDF öffnen"))
        self.click("Zurück")
        self.click("Beleg drucken")
        self.click("Bestätigen")
        self.wait(lambda:len(self.prints)==1)
        self.assertEqual(self.core.report["source"],"BENNING")

    def test_home_wolf_double_tap_counts_once_and_opens(self):
        from hdmi_personality import Wolf
        self.wait(lambda:self.surface.findChild(Wolf) is not None)
        mascot=self.surface.findChild(Wolf)
        self.surface.scroll.ensureWidgetVisible(mascot)
        self.app.processEvents()
        point=self.window.mapFromScene(self.window.proxy.mapToScene(
            mascot.mapTo(self.surface,mascot.rect().center())))
        QTest.mouseClick(self.window.viewport(),Qt.LeftButton,pos=point)
        self.assertEqual(mascot.sprite,"happy")
        QTest.mouseClick(self.window.viewport(),Qt.LeftButton,pos=point)
        self.assertEqual(self.surface.view,"pet")
        self.wait(lambda:self.core.pet_count==1)
        self.assertEqual(self.core.achievement_stats["pets"],1)

    def test_rotated_overlay_resizes_scrolls_and_rolls_back(self):
        self.click("☰")
        self.click("Anzeige")
        self.click("90°")
        self.wait(lambda:self.surface.overlay is not None and self.window.angle==90)
        self.window.resize(1024,600)
        self.wait(lambda:self.surface.width()==600)
        self.click("Bestätigen")
        self.assertEqual(self.surface.rotation.saved,90)
        self.click("270°")
        self.assertEqual(self.window.angle,270)
        from PyQt5.QtCore import QTimer
        self.surface.overlay.findChild(QTimer).start(80)
        self.wait(lambda:self.window.angle==90 and self.surface.overlay is None)
        self.click("0°")
        self.click("Bestätigen")
        self.core.operators.rename("Another Bench Examiner")
        for i in range(13):
            self.core.operators.rename(f"Bench {i:02}")
        self.surface.route("settings")
        self.click("Prüfpersonen")
        self.wait(lambda:self.surface.scroll.verticalScrollBar().maximum()>0)
        target=self.surface.scroll.viewport()
        p=QPointF(target.rect().center())
        wheel=QWheelEvent(p,p,QPoint(),QPoint(0,-240),Qt.NoButton,Qt.NoModifier,Qt.NoScrollPhase,False)
        QApplication.sendEvent(target,wheel)
        self.wait(lambda:self.surface.scroll.verticalScrollBar().value()>0)
