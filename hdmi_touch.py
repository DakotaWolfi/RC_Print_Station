"""Kiosk pointer arbitration and optional per-device raw touchscreen calibration."""
import json
import os
from pathlib import Path
import tempfile

from PyQt5.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt, QSocketNotifier, QTimer
from PyQt5.QtGui import QColor, QMouseEvent, QPainter
from PyQt5.QtWidgets import QApplication, QPushButton, QScrollArea, QScrollBar, QWidget

from display_presence import read, touchscreens
from touch_calibration import TARGETS, apply, fit

CONFIG=Path.home()/".config/rc-printstation/touchscreen.json"


class DragScroll(QObject):
    """Resolve a gesture in the viewport before forwarding any click to Qt."""
    def __init__(self, view, surface):
        super().__init__(view)
        self.view=view
        self.surface=surface
        self.press=None
        self.passing=False
        viewport=view.viewport()
        viewport.setAttribute(Qt.WA_AcceptTouchEvents)
        viewport.installEventFilter(self)

    def logical(self,point):
        return self.view.proxy.mapFromScene(self.view.mapToScene(point))

    def scroll_at(self,point):
        target=self.surface.childAt(self.logical(point).toPoint())
        while target and target!=self.surface:
            if isinstance(target,QScrollBar) or target.property("wantsStroke"):
                return None
            if isinstance(target,QScrollArea):
                bar=target.verticalScrollBar()
                return bar if bar.maximum()>bar.minimum() else None
            target=target.parentWidget()
        return None

    def pointer(self,kind,point):
        mouse={QEvent.TouchBegin:QEvent.MouseButtonPress,QEvent.TouchUpdate:QEvent.MouseMove,
               QEvent.TouchEnd:QEvent.MouseButtonRelease}
        if kind==QEvent.TouchCancel:
            if self.press:
                self.press=None
                self.surface.dragging_pointer=False
            elif self.touch_down:
                # Release outside the viewport, never activate a pressed control.
                self.pointer(QEvent.TouchEnd,QPoint(-200,-200))
            self.touch_down=False
            return
        self.touch_down=kind!=QEvent.TouchEnd
        viewport=self.view.viewport()
        change=Qt.NoButton if kind==QEvent.TouchUpdate else Qt.LeftButton
        buttons=Qt.NoButton if kind==QEvent.TouchEnd else Qt.LeftButton
        QApplication.sendEvent(viewport,QMouseEvent(mouse[kind],QPointF(point),change,buttons,Qt.NoModifier))

    touch_down=False

    def eventFilter(self,obj,event):
        if self.passing:
            return False
        kind=event.type()
        if kind in (QEvent.TouchBegin,QEvent.TouchUpdate,QEvent.TouchEnd,QEvent.TouchCancel):
            points=event.touchPoints()
            if kind==QEvent.TouchCancel or points:
                self.pointer(kind,points[0].pos().toPoint() if points else QPoint())
            return True
        if kind==QEvent.MouseButtonPress and event.button()==Qt.LeftButton:
            if self.surface.blanked:
                return False
            bar=self.scroll_at(event.pos())
            if bar:
                self.press=(event.pos(),self.logical(event.pos()),bar,bar.value(),False)
                self.surface.dragging_pointer=True
                return True
        if self.press and kind in (QEvent.MouseMove,QEvent.MouseButtonRelease):
            start,logical,bar,position,dragged=self.press
            now=self.logical(event.pos())
            dragged=dragged or (event.pos()-start).manhattanLength()>=10
            if dragged:
                try:
                    bar.setValue(position+round(logical.y()-now.y()))
                except RuntimeError:
                    # A background refresh or navigation replaced this scroll area.
                    self.press=None
                    self.surface.dragging_pointer=False
                    return True
            if kind==QEvent.MouseMove:
                self.press=start,logical,bar,position,dragged
            else:
                self.press=None
                self.surface.dragging_pointer=False
                if not dragged:
                    self.passing=True
                    try:
                        viewport=self.view.viewport()
                        QApplication.sendEvent(viewport,QMouseEvent(
                            QEvent.MouseButtonPress,QPointF(start),Qt.LeftButton,Qt.LeftButton,event.modifiers()))
                        QApplication.sendEvent(viewport,QMouseEvent(
                            QEvent.MouseButtonRelease,QPointF(event.pos()),Qt.LeftButton,Qt.NoButton,event.modifiers()))
                    finally:
                        self.passing=False
            return True
        return False


def candidates(preferred="",sysroot=Path("/sys/class/input"),udev=Path("/run/udev/data")):
    result=[]
    for path in touchscreens(sysroot,udev):
        if preferred and os.path.realpath(preferred)!=os.path.realpath(path):
            continue
        event=sysroot/Path(path).name
        props=dict(line[2:].split("=",1) for line in read(udev/("c"+read(event/"dev"))).splitlines()
                   if line.startswith("E:") and "=" in line)
        identity=props.get("ID_PATH")
        if identity and props.get("ID_INPUT_TOUCHSCREEN")=="1":
            result.append((identity,path))
    return result


class EvdevTouch(QObject):
    """Single contact forwarding for type-B multitouch and single-touch panels."""
    def __init__(self,parent,path,on_point,disconnected):
        super().__init__(parent)
        from evdev import InputDevice,ecodes as e
        self.e=e
        self.dev=InputDevice(path)
        self.on_point=on_point
        self.disconnected=disconnected
        self.slot=0
        self.active=False
        self.sent=False
        self.coords={}
        try:
            axes=self.dev.capabilities(absinfo=False).get(e.EV_ABS,[])
            self.multi={e.ABS_MT_SLOT,e.ABS_MT_POSITION_X,e.ABS_MT_POSITION_Y}.issubset(axes)
            self.xy=(e.ABS_MT_POSITION_X,e.ABS_MT_POSITION_Y) if self.multi else (e.ABS_X,e.ABS_Y)
            self.ranges={axis:self.dev.absinfo(axis) for axis in self.xy}
            if any(info.max<=info.min for info in self.ranges.values()):
                raise ValueError("touch axis range")
            self.dev.grab()
        except BaseException:
            self.dev.close()
            raise
        self.notify=QSocketNotifier(self.dev.fd,QSocketNotifier.Read,self)
        self.notify.activated.connect(self.receive)

    def receive(self):
        e=self.e
        try:
            for event in self.dev.read():
                kind,code,value=event.type,event.code,event.value
                if kind==e.EV_ABS:
                    if self.multi and code==e.ABS_MT_SLOT:
                        self.slot=value
                    elif not self.multi or self.slot==0:
                        if code in self.xy:
                            self.coords[code]=value
                        elif self.multi and code==e.ABS_MT_TRACKING_ID:
                            self.active=value>=0
                elif not self.multi and kind==e.EV_KEY and code==e.BTN_TOUCH:
                    self.active=bool(value)
                elif kind==e.EV_SYN and code==e.SYN_DROPPED:
                    self.on_point(QEvent.TouchCancel,(0,0))
                    self.active=self.sent=False
                    self.coords.clear()
                elif kind==e.EV_SYN and code==e.SYN_REPORT and (self.active or self.sent):
                    if all(axis in self.coords for axis in self.xy):
                        point=tuple((self.coords[axis]-self.ranges[axis].min)/
                                    (self.ranges[axis].max-self.ranges[axis].min) for axis in self.xy)
                        phase=QEvent.TouchUpdate if self.sent and self.active else (
                            QEvent.TouchBegin if self.active else QEvent.TouchEnd)
                        self.sent=self.active
                        self.on_point(phase,point)
        except BlockingIOError:
            pass
        except OSError:
            self.disconnected()

    def close(self):
        self.notify.setEnabled(False)
        try:
            self.dev.ungrab()
        except OSError:
            pass
        self.dev.close()
        self.deleteLater()


class CalibrationPage(QWidget):
    def __init__(self,surface):
        super().__init__(surface)
        self.surface=surface
        self.stage=0
        self.cancel=QPushButton(surface.t("Abbrechen"),self)
        self.cancel.clicked.connect(lambda _:surface.close_overlay(False))

    def resizeEvent(self,event):
        self.cancel.setGeometry(12,self.height()-58,130,48)
        super().resizeEvent(event)

    def target(self):
        x,y=TARGETS[self.stage]
        return QPoint(round(self.width()*x),round(self.height()*y))

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),QColor("#101923"))
        spot=self.target()
        p.setPen(QColor("#ffb457"))
        p.drawEllipse(spot,19,19)
        p.drawLine(spot+QPoint(-26,0),spot+QPoint(26,0))
        p.drawLine(spot+QPoint(0,-26),spot+QPoint(0,26))
        p.drawText(QRect(30,self.height()//3,self.width()-60,60),Qt.AlignCenter|Qt.TextWordWrap,
                   self.surface.t("Ziel berühren · {n} von 5",n=self.stage+1))


class TouchManager(QObject):
    def __init__(self,view,surface,output,preferred="",*,config=CONFIG,devices=candidates,reader=EvdevTouch):
        super().__init__(view)
        self.view,self.surface=view,surface
        self.output,self.preferred=output or "default",preferred
        self.config,self.devices,self.reader=Path(config),devices,reader
        self.raw=None
        self.path=None
        self.matrix=None
        self.previous=None
        self.collection=None
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.connect_saved)
        self.timer.start(2000)
        self.connect_saved()

    def load(self):
        try:
            data=json.loads(self.config.read_text())
            return data if isinstance(data,dict) else {}
        except (OSError,ValueError):
            return {}

    def write(self,data):
        self.config.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        fd,temp=tempfile.mkstemp(prefix=".touch-",dir=self.config.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as out:
                json.dump(data,out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temp,self.config)
        finally:
            Path(temp).unlink(missing_ok=True)

    def connect_saved(self):
        if self.raw or self.previous:
            return
        saved=self.load().get(self.output,{})
        for identity,path in self.devices(self.preferred):
            matrix=saved.get(identity) if isinstance(saved,dict) else None
            if (isinstance(matrix,list) and len(matrix)==6 and
                    all(type(v) in (int,float) and abs(v)<=3 for v in matrix)):
                try:
                    self.attach(path,matrix)
                except (ImportError,ValueError,OSError):
                    pass
                return

    def attach(self,path,matrix):
        self.detach()
        self.raw=self.reader(self,path,self.point,self.disconnect)
        self.path,self.matrix=path,matrix

    def detach(self):
        if self.raw:
            self.raw.close()
        self.raw=self.path=self.matrix=None

    def disconnect(self):
        self.view.gesture.pointer(QEvent.TouchCancel,QPoint())
        self.detach()
        if self.previous:
            self.surface.close_overlay(False)

    def start(self,identity,path):
        if self.previous or self.surface.overlay:
            return
        self.previous=(self.path,self.matrix)
        try:
            self.attach(path,None)
        except (ImportError,OSError,ValueError):
            self.restore()
            self.surface.dialog("Touchscreen kalibrieren",
                                "Rohdaten des Touchscreens sind nicht verfügbar. Gerät und Eingaberechte prüfen.")
            return
        self.collection=CalibrationPage(self.surface),[],[],identity
        self.surface.open_overlay(self.collection[0],self.collection_closed)
        timer=QTimer(self.collection[0],singleShot=True)
        timer.timeout.connect(lambda:self.surface.close_overlay(False) if self.collection else None)
        timer.start(45000)

    def collection_closed(self,accepted):
        if not accepted:
            self.restore()

    def restore(self):
        self.collection=None
        previous,self.previous=self.previous,None
        if previous:
            path,matrix=previous
            try:
                if path and self.raw and self.path==path:
                    self.matrix=matrix
                elif path:
                    self.attach(path,matrix)
                else:
                    self.detach()
            except (ImportError,OSError,ValueError):
                self.detach()

    def point(self,phase,point):
        if self.collection:
            if phase==QEvent.TouchEnd:
                self.sample(point)
            return
        if self.matrix:
            x,y=apply(self.matrix,point)
            p=QPoint(round(x*self.view.viewport().width()),round(y*self.view.viewport().height()))
            self.view.gesture.pointer(phase,p)

    def sample(self,point):
        page,raw,targets,identity=self.collection
        raw.append(point)
        logical=page.mapTo(self.surface,page.target())
        # Map the painted target into the existing viewport once. The saved
        # affine map feeds that viewport; Qt does the only inverse scene rotation.
        dest=self.view.mapFromScene(self.view.proxy.mapToScene(QPointF(logical)))
        targets.append((dest.x()/self.view.viewport().width(),dest.y()/self.view.viewport().height()))
        if len(raw)<len(TARGETS):
            page.stage+=1
            page.update()
            return
        try:
            matrix=fit(raw,targets)
        except ValueError:
            self.surface.close_overlay(False)
            self.surface.dialog("Touchscreen kalibrieren","Messpunkte stimmen nicht überein. Kalibrierung wiederholen.")
            return
        self.collection=None
        self.matrix=matrix
        self.surface.close_overlay(True)
        self.surface.dialog("Touchscreen kalibrieren","Antippen zum Speichern. Ohne Bestätigung wird die alte Kalibrierung wiederhergestellt.",
                            lambda:None,closed=lambda keep:self.finish(identity,keep))
        pane=self.surface.overlay
        timer=QTimer(pane,singleShot=True)
        timer.timeout.connect(lambda:self.surface.close_overlay(False) if self.surface.overlay is pane else None)
        timer.start(15000)

    def finish(self,identity,keep):
        if keep:
            try:
                data=self.load()
                section=data.get(self.output,{})
                data[self.output]={**section,identity:self.matrix} if isinstance(section,dict) else {identity:self.matrix}
                self.write(data)
            except OSError:
                self.surface.notify("Anzeigeeinstellung konnte nicht gespeichert werden.")
                self.restore()
            else:
                self.previous=None
        else:
            self.restore()

    def reset(self):
        data=self.load()
        data.pop(self.output,None)
        self.write(data)
        self.detach()
