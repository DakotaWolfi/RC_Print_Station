"""Small lazily loaded HDMI pet widget with a tap fallback."""
from time import monotonic
from PyQt5.QtCore import QPointF, Qt, QTimer, QEvent
from PyQt5.QtGui import QColor, QPainter, QPen, QPolygonF
from PyQt5.QtWidgets import QWidget


class Wolf(QWidget):
    def __init__(self, pet):
        super().__init__()
        self.pet=pet
        self.last=0
        self.start=None
        self.excited=False
        self.setFixedSize(160,142)
        self.setAccessibleName("FMI workshop wolf")
        self.setAttribute(Qt.WA_AcceptTouchEvents,True)

    def stroke(self,point):
        if self.start is not None and (point-self.start).manhattanLength()>24 and monotonic()-self.last>.6:
            self.last=monotonic()
            self.start=point
            self.excited=True
            self.pet()
            self.update()
            QTimer.singleShot(850,self.calm)

    def calm(self):
        self.excited=False
        self.update()

    def mousePressEvent(self,event):
        self.start=event.localPos()

    def mouseMoveEvent(self,event):
        if event.buttons() & Qt.LeftButton:
            self.stroke(event.localPos())

    def mouseReleaseEvent(self,event):
        self.start=None

    def event(self,event):
        if event.type() in (QEvent.TouchBegin,QEvent.TouchUpdate,QEvent.TouchEnd):
            points=event.touchPoints()
            if points and event.type()==QEvent.TouchBegin:
                self.start=points[0].pos()
            elif points and event.type()==QEvent.TouchUpdate:
                self.stroke(points[0].pos())
            else:
                self.start=None
            return True
        return super().event(event)

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#314a5d"))
        p.drawEllipse(14,5,132,132)
        lift=7 if self.excited else 0
        def shape(colour,points):
            p.setBrush(QColor(colour))
            p.drawPolygon(QPolygonF([QPointF(x,y) for x,y in points]))
        shape("#8ba5b7",((36,69),(36,28-lift),(61,49),(96,49),(124,28-lift),(126,69),
                          (138,88),(80,129),(22,88)))
        shape("#edf4f8",((28,88),(59,80),(80,97),(101,80),(132,88),(80,125)))
        shape("#142331",((72,99),(88,99),(80,107)))
        p.setPen(QPen(QColor("#142331"),4,Qt.SolidLine,Qt.RoundCap))
        if self.excited:
            p.drawArc(53,65,15,11,0,180*16)
            p.drawArc(92,65,15,11,0,180*16)
            p.setPen(Qt.NoPen)
            shape("#f68c97",((108,18),(114,11),(120,15),(125,11),(132,18),(120,31)))
        else:
            p.drawPoint(60,72)
            p.drawPoint(99,72)
