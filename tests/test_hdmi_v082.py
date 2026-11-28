"""Exercise the native frontend through real Qt events and station commands."""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase, skipIf
from unittest.mock import patch

try:
    from PyQt5.QtCore import QEvent, Qt, QPoint, QPointF
    from PyQt5.QtGui import QMouseEvent, QWheelEvent
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QLabel, QPushButton
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
        self.transport=transport
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
        self.click("Meldung oder Unsicherheit")
        self.click("Lo LOAD")
        self.click("Geringe Last bestätigt")
        self.click("Meldung oder Unsicherheit")
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
        with patch.dict("os.environ",{"FMI_PDF_EXPORT_DIR":str(Path(self.temp.name)/"Downloads")}):
            self.click("PDF lokal speichern")
            self.click("Bestätigen")
            directory=Path(self.temp.name)/"Downloads"
            self.wait(lambda:any(directory.glob("FMI-*-V082-01-R*.pdf")))
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

    def test_real_class_mismatch_adopts_only_as_documentation_through_hdmi_widgets(self):
        import os
        from benning_hardware import USB_COMPLETE
        from benning_output import report_checks

        self.click("Geführte Prüfung")
        self.enter("Prüfnummer","HDMI084")
        self.enter("Gerätebeschreibung","Bench fixture")
        for caption in ("Prüfung beginnen","Ohne Befund","Schutzklasse I",
                        "Netz + 500 V geprüft","PASS","STORE + Slot gesehen",
                        "Prüfperson","Bench Operator","Funktion","Ohne Befund","Zum Import"):
            self.click(caption)
        self.wait(lambda:self.core.phase=="waiting")
        pulled=self.core.store.import_bytes(USB_COMPLETE,"usb")
        self.rx.status=ReceiverStatus("imported","usb",batch=pulled.batch)
        self.click("Vorhandene Messung")
        self.click("033")
        self.wait(lambda:self.button("Geprüfte Prüfart übernehmen") is not None)

        def copy():
            return "\n".join(widget.text() for widget in self.surface.findChildren(QLabel) if widget.isVisible())

        self.assertIn("Im Leitfaden gewählt: Klasse I",copy())
        self.assertIn("BENNING-Prüfart: Klasse II (übertragen)",copy())
        self.assertIsNone(self.button("Messung bestätigen"))
        if directory:=os.environ.get("FMI_V084_HDMI_PREVIEW"):
            path=Path(directory)
            path.mkdir(parents=True,exist_ok=True)
            self.surface.scroll.verticalScrollBar().setValue(0)
            self.app.processEvents()
            self.assertTrue(self.window.grab().save(str(path/"hdmi-480x800-class-warning.png")))
        self.click("Andere Messung wählen")
        self.wait(lambda:self.core.selected is None)
        self.click("044")
        self.wait(lambda:"Kabel · Gut" in copy())
        self.click("Abbrechen")
        self.wait(lambda:self.core.phase=="guide")
        self.assertIsNone(self.core.report)
        self.click("Zum Import")
        self.click("Vorhandene Messung")
        self.click("033")
        self.click("Geprüfte Prüfart übernehmen")
        self.wait(lambda:self.surface.overlay is not None)
        self.assertIsNone(self.core.report)
        self.click("Bestätigen")
        self.wait(lambda:self.core.phase=="report")
        self.assertEqual(self.core.report["record"]["protection_class"],"Klasse II")
        self.assertEqual(self.core.report["record"]["verdict"],"bestanden")
        exam=self.core.report["examination"]
        self.assertEqual((exam["procedure"],exam["class_reconciliation"]["selected"]),("II","I"))
        self.assertNotIn("voltage_confirmed",exam)
        self.assertIn("Keine Freigabe",dict(report_checks(self.core.report))["Freigabe"])

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

    def test_all_digits_on_each_keypad_with_actual_clicks(self):
        from hdmi_keyboard import Keyboard
        expected={"number":"0123456789","ticket":"000100020123456789","ipv4":"198.230.45.67"}
        for mode,keys in expected.items():
            with self.subTest(mode=mode):
                self.surface.enter_text("Keyboard test","",32,lambda _:None,mode=mode)
                self.app.processEvents()
                keyboard=self.surface.overlay
                self.assertIsInstance(keyboard,Keyboard)
                for digit in keys:
                    self.click(digit)
                self.assertEqual(keyboard.edit.text(),keys)
                self.assertTrue(keyboard.done_button.isEnabled())
                self.click("Übernehmen")
                self.assertIsNone(self.surface.overlay)

    def test_alphabet_symbol_navigation_and_password_controls(self):
        self.surface.enter_text("Keyboard test","",220,lambda _:None,secret=True)
        self.app.processEvents()
        keyboard=self.surface.overlay
        self.click("Anzeigen")
        self.assertEqual(keyboard.edit.echoMode(),keyboard.edit.Normal)
        self.click("Verbergen")
        self.assertEqual(keyboard.edit.echoMode(),keyboard.edit.Password)

        def type_layer(chars):
            for value in dict.fromkeys(chars):
                self.wait(lambda:any(b.isVisible() and b.property("keyValue")==value
                                     for b in keyboard.findChildren(QPushButton)))
                key=next(b for b in keyboard.findChildren(QPushButton)
                         if b.isVisible() and b.property("keyValue")==value)
                keyboard.edit.clear()
                QTest.mouseClick(key,Qt.LeftButton)
                self.assertEqual(keyboard.edit.text(),value)

        type_layer("qwertzuiopasdfghjklyxcvbnm")
        self.click("⇧")
        QTest.mouseClick(next(b for b in keyboard.findChildren(QPushButton)
                             if b.isVisible() and b.text()=="A"),Qt.LeftButton)
        self.assertTrue(keyboard.edit.text().endswith("A"))
        self.click("←")
        self.click("→")
        self.click("⌫")
        self.click("Leerzeichen")
        self.assertTrue(keyboard.edit.text().endswith(" "))
        self.click("123")
        from hdmi_keyboard import MORE,SYMBOLS
        type_layer("".join(SYMBOLS))
        self.click("#+=")
        type_layer("".join(MORE))
        self.click("ABC")
        self.app.processEvents()
        from hdmi_keyboard import ACCENTS
        for base,variants in ACCENTS.items():
            for variant in variants:
                letter=next(b for b in keyboard.findChildren(QPushButton)
                            if b.isVisible() and b.property("keyValue")==base)
                keyboard.edit.clear()
                QTest.mousePress(letter,Qt.LeftButton)
                self.wait(keyboard.accent_row.isVisible)
                QTest.mouseRelease(letter,Qt.LeftButton)
                accent=next(b for b in keyboard.accent_row.findChildren(QPushButton)
                            if b.isVisible() and b.property("keyValue")==variant)
                QTest.mouseClick(accent,Qt.LeftButton)
                self.assertEqual(keyboard.edit.text(),variant)
        self.click("Abbrechen")
        self.assertIsNone(self.surface.overlay)

    def test_drag_scroll_suppresses_a_click_after_90_degree_rotation(self):
        self.surface.rotation.start(90)
        self.surface.rotation.done(True)
        self.surface.route("settings")
        self.click("Prüfpersonen")
        for i in range(24):
            self.core.operators.rename(f"Bench {i:02}")
        self.surface.open_people()
        bar=self.surface.scroll.verticalScrollBar()
        self.wait(lambda:bar.maximum()>100)
        edit=self.button("Bearbeiten")
        start=self.window.mapFromScene(self.window.proxy.mapToScene(
            edit.mapTo(self.surface,edit.rect().center())))
        viewport=self.window.viewport()
        end=start+QPoint(115,0)
        QTest.mousePress(viewport,Qt.LeftButton,pos=start)
        QApplication.sendEvent(viewport,QMouseEvent(QEvent.MouseMove,QPointF(end),
                                                    Qt.NoButton,Qt.LeftButton,Qt.NoModifier))
        QTest.mouseRelease(viewport,Qt.LeftButton,pos=end)
        self.assertGreater(bar.value(),70)
        self.assertIsNone(self.surface.overlay)

    def test_integrated_calibration_and_saved_cold_mapping_at_90(self):
        from hdmi_touch import TouchManager
        from touch_calibration import apply
        root=Path(self.temp.name)
        identity="usb-fixture-1"
        self.surface.rotation.start(90)
        self.surface.rotation.done(True)
        choices=lambda preferred:[(identity,"/dev/input/eventFixture")]
        def reader(*args):
            return SimpleNamespace(close=lambda:None)
        manager=TouchManager(self.window,self.surface,"HDMI-A-1",config=root/"touch.json",devices=choices,reader=reader)
        self.surface.touch_manager=manager
        self.addCleanup(manager.detach)
        self.surface.route("display")
        self.click("Touchscreen kalibrieren")
        self.wait(lambda:manager.collection is not None)
        for _ in range(5):
            page=manager.collection[0]
            dest=self.window.mapFromScene(self.window.proxy.mapToScene(QPointF(page.mapTo(self.surface,page.target()))))
            x=dest.x()/self.window.viewport().width()
            y=dest.y()/self.window.viewport().height()
            manager.point(QEvent.TouchEnd,(1-x,y))
        match=self.button("Bestätigen")
        self.assertIsNotNone(match)
        actual=self.window.mapFromScene(self.window.proxy.mapToScene(QPointF(match.mapTo(self.surface,match.rect().center()))))
        point=(1-actual.x()/self.window.viewport().width(),actual.y()/self.window.viewport().height())
        manager.point(QEvent.TouchBegin,point)
        manager.point(QEvent.TouchEnd,point)
        self.assertTrue((root/"touch.json").exists())
        manager.timer.stop()
        manager.detach()
        rebooted=TouchManager(self.window,self.surface,"HDMI-A-1",config=root/"touch.json",devices=choices,reader=reader)
        self.addCleanup(rebooted.detach)
        self.assertTrue(rebooted.raw)
        for point in ((0,0),(1,0),(1,1),(0,1)):
            actual=apply(rebooted.matrix,point)
            self.assertAlmostEqual(actual[0],1-point[0])
            self.assertAlmostEqual(actual[1],point[1])

    def test_frontend_close_and_expired_owner_can_resume_with_widget_click(self):
        from hdmi_frontend import RotatedSurface, Surface
        from time import monotonic
        self.click("Geführte Prüfung")
        self.enter("Prüfnummer","0014")
        self.enter("Gerätebeschreibung","Bench kettle")
        self.click("Prüfung beginnen")
        self.wait(lambda:self.core.phase=="guide" and self.core.live_owner()==self.surface.client)
        old=self.surface.client
        self.window.close()
        self.surface=Surface(transport=self.transport)
        self.window=RotatedSurface(self.surface,0)
        self.window.resize(480,800)
        self.window.show()
        self.addCleanup(self.window.close)
        self.wait(lambda:self.surface.state.get("control")=="other")
        self.assertIsNone(self.button("Ohne Befund"))
        with patch("station_core.monotonic",return_value=monotonic()+21):
            self.click("An dieser Anzeige fortsetzen")
            self.click("Bestätigen")
            self.click("Ohne Befund")
            self.wait(lambda:self.core.guide.step=="kind")
            self.assertNotEqual(old,self.core.live_owner())
            self.assertEqual(self.core.draft["ticket"],"0014")
