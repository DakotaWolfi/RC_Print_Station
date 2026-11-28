"""Lazy illustrated workshop mascot. Interactions are decoupled from testing."""
from pathlib import Path
from time import monotonic

from PyQt5.QtCore import QEvent, QRect, Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPixmap
from PyQt5.QtWidgets import QSizePolicy, QWidget

ART=Path(__file__).resolve().parent/"assets/wolf"


class Wolf(QWidget):
    def __init__(self, pet, treat=lambda:None, *, home=False):
        super().__init__()
        self.pet=pet
        self.home=home
        self.setProperty("wantsStroke",not home)
        self.treat=treat
        self.last=monotonic()
        self.start=None
        self.moved=False
        self.sprite="idle"
        self.art={}
        self.setMinimumHeight(155)
        self.setMaximumSize(285,270)
        self.setSizePolicy(QSizePolicy.Expanding,QSizePolicy.Preferred)
        self.setAccessibleName("FMI workshop wolf")
        self.setAttribute(Qt.WA_AcceptTouchEvents,True)
        self.reset=QTimer(self,singleShot=True)
        self.reset.timeout.connect(self.calm)
        self.nap=QTimer(self,singleShot=True)
        self.nap.timeout.connect(lambda:self.show_sprite("sleep"))
        self.blink=QTimer(self)
        self.blink.timeout.connect(self.blink_once)

    def showEvent(self,event):
        self.nap.start(18000)
        self.blink.start(6000)
        super().showEvent(event)

    def hideEvent(self,event):
        self.nap.stop()
        self.blink.stop()
        self.reset.stop()
        super().hideEvent(event)

    def show_sprite(self,name):
        if name not in self.art:
            self.art[name]=QPixmap(str(ART/f"{name}.webp"))
        self.sprite=name
        self.update()

    def blink_once(self):
        if self.sprite=="idle":
            self.show_sprite("sleep")
            self.reset.start(140)

    def react(self,name):
        if not self.home and monotonic()-self.last<.45 and self.sprite!="idle":
            return
        self.last=monotonic()
        self.show_sprite(name)
        self.nap.stop()
        self.reset.start(1000)
        if name=="happy":
            self.pet()
        elif name=="treat":
            self.treat()

    def calm(self):
        self.show_sprite("idle")
        self.nap.start(18000)

    def stroke(self,point):
        if self.start is not None and not self.moved and (point-self.start).manhattanLength()>20:
            self.moved=True
            if not self.home:
                self.react("happy")

    def press(self,point):
        self.start=point
        self.moved=False

    def end(self):
        if self.start is not None and not self.moved:
            self.react("happy")
        self.start=None

    def mousePressEvent(self,event):
        self.press(event.localPos())

    def mouseMoveEvent(self,event):
        self.stroke(event.localPos())

    def mouseReleaseEvent(self,event):
        self.end()

    def event(self,event):
        kind=event.type()
        if kind in (QEvent.TouchBegin,QEvent.TouchUpdate,QEvent.TouchEnd,QEvent.TouchCancel):
            points=event.touchPoints()
            if points and kind==QEvent.TouchBegin:
                self.press(points[0].pos())
            elif points and kind==QEvent.TouchUpdate:
                self.stroke(points[0].pos())
            elif kind==QEvent.TouchEnd:
                self.end()
            else:
                self.start=None
            return True
        return super().event(event)

    def paintEvent(self,event):
        if self.sprite not in self.art:
            self.art[self.sprite]=QPixmap(str(ART/f"{self.sprite}.webp"))
        pix=self.art[self.sprite]
        if pix.isNull():
            return
        p=QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        s=pix.size()
        s.scale(self.width(),self.height()-10,Qt.KeepAspectRatio)
        y=4 if self.sprite in ("happy","treat","awoo") else 10
        p.drawPixmap(QRect((self.width()-s.width())//2,y,s.width(),s.height()),pix)
        if self.sprite=="happy":
            p.setPen(QColor("#ff9c9c"))
            p.drawText(self.width()-38,25,"♥")
