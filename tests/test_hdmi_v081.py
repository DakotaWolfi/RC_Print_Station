"""Native layout and keyboard tests. Use /usr/bin/python3 with Qt offscreen."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

try:
    from PyQt5.QtCore import Qt
    from PyQt5.QtTest import QTest
    from PyQt5.QtWidgets import QApplication, QMenu, QPushButton
except ImportError:
    QApplication=None


@unittest.skipIf(QApplication is None,"Install system PyQt5")
class NativeUsabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        from hdmi_frontend import Surface
        from tools.render_v080_previews import fixture, showcase
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.core=fixture(Path(temp.name))
        self.addCleanup(self.core.close)
        self.scenes={lang:list(showcase(self.core,lang)) for lang in ("de","en")}
        self.surface=Surface(preview=True)
        self.addCleanup(self.surface.close)

    def test_navigation_preserves_draft(self):
        s=self.surface
        s.show_state(self.scenes["de"][1][1])
        s.route("settings")
        s.route("printer")
        s.go_back()
        self.assertEqual(s.view,"settings")
        s.go_back()
        self.assertEqual(s.view,"work")
        original=dict(s.state["draft"])
        s.go_home()
        self.assertEqual(s.view,"home")
        s.go_back()
        self.assertEqual(s.state["draft"],original)
        self.assertEqual(s.view,"work")

    def test_keys_and_keyboard_bounds(self):
        from hdmi_keyboard import Keyboard
        s=self.surface
        for width,height in ((480,800),(800,480),(600,1024),(1024,600)):
            s.resize(width,height)
            s.show()
            for lang in self.scenes:
                s.show_state(self.scenes[lang][0][1])
                for mode in ("text","ticket","ipv4","number"):
                    with self.subTest(width=width,height=height,lang=lang,mode=mode):
                        pane=Keyboard(s,"Bearbeiten","",64,mode=mode)
                        pane.show()
                        self.app.processEvents()
                        self.assertLessEqual(pane.width(),width)
                        self.assertLessEqual(pane.height(),height)
                        for item in pane.findChildren(QPushButton):
                            if item.isVisible():
                                self.assertGreaterEqual(item.height(),44)
                                self.assertTrue(pane.rect().contains(item.geometry()),item.text())
                        if mode=="text":
                            value="z" if lang=="de" else "y"
                            key=next(k for k in pane.findChildren(QPushButton) if k.text()==value)
                            QTest.mouseClick(key,Qt.LeftButton)
                            self.assertEqual(pane.edit.text(),value)
                            QTest.keyClick(pane.edit,Qt.Key_Backspace)
                            self.assertEqual(pane.edit.text(),"")
                            QTest.keyClicks(pane.edit,"Physical")
                            self.assertEqual(pane.edit.text(),"Physical")
                            a=next(k for k in pane.findChildren(QPushButton) if k.text()=="a")
                            QTest.mousePress(a,Qt.LeftButton)
                            QTest.qWait(510)
                            menu=a.findChild(QMenu)
                            self.assertTrue(menu.isVisible())
                            menu.actions()[0].trigger()
                            menu.hide()
                            self.assertTrue(pane.edit.text().endswith("ä"))
                        elif mode=="ipv4":
                            self.assertFalse(pane.done_button.isEnabled())
                            QTest.keyClicks(pane.edit,"169.254.25.23")
                            self.assertTrue(pane.done_button.isEnabled())
                        pane.reject()
                        self.assertEqual(pane.result(),0)
                        pane.deleteLater()

    def test_header_and_pages_at_all_dimensions(self):
        s=self.surface
        for width,height in ((480,800),(800,480),(600,1024),(1024,600)):
            for lang,scenes in self.scenes.items():
                s.resize(width,height)
                s.show()
                for name,state,report in scenes:
                    with self.subTest(width=width,height=height,lang=lang,scene=name):
                        s.loaded_report=state["report"] if report else None
                        s.report=report
                        s.show_state(state)
                        self.app.processEvents()
                        for key in (s.logo,s.home,s.back,s.lang,s.menu):
                            self.assertTrue(s.rect().contains(key.geometry()))
                            self.assertGreaterEqual(key.height(),48)
                        self.assertEqual(s.size().width(),width)
                        self.assertEqual(s.scroll.horizontalScrollBar().maximum(),0)
                for page in ("settings","printer","wifi","display","tester","people","personality","system","pet","workshop"):
                    s.route(page)
                    self.app.processEvents()
                    self.assertEqual(s.scroll.horizontalScrollBar().maximum(),0)
                s.route("work",False)
