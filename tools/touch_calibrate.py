#!/usr/bin/env python3
"""Render one per-device libinput rule. Interactive sampling opens only input RX."""
from argparse import ArgumentParser
from contextlib import closing
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from touch_calibration import ROTATIONS, TARGETS, fit, rotation, rule


def sample(path, output, comp_rotation):
    from evdev import InputDevice, ecodes as e
    from PyQt5.QtCore import QSocketNotifier, QTimer, Qt
    from PyQt5.QtGui import QPainter, QColor
    from PyQt5.QtWidgets import QApplication, QWidget

    with closing(InputDevice(path)) as touch:
        caps=touch.capabilities(absinfo=False)
        axes=caps.get(e.EV_ABS, [])
        multi=e.ABS_MT_POSITION_X in axes and e.ABS_MT_POSITION_Y in axes
        x,y=(e.ABS_MT_POSITION_X,e.ABS_MT_POSITION_Y) if multi else (e.ABS_X,e.ABS_Y)
        ranges={axis:touch.absinfo(axis) for axis in (x,y)}
        if any(info.max<=info.min for info in ranges.values()):
            raise ValueError("Device has no usable absolute touch axes")
        app=QApplication([])
        result=[]

        class Calibration(QWidget):
            def __init__(self):
                super().__init__()
                self.samples=[]
                self.values={}
                self.release=False
                self.slot=0
                self.points=QSocketNotifier(touch.fd,QSocketNotifier.Read,self)
                self.points.activated.connect(self.receive)

            def receive(self):
                try:
                    events=touch.read()
                    for event in events:
                        if event.type==e.EV_ABS:
                            if event.code==e.ABS_MT_SLOT:
                                self.slot=event.value
                            if multi and self.slot!=0:
                                continue
                            if event.code in (x,y):
                                self.values[event.code]=event.value
                            elif multi and event.code==e.ABS_MT_TRACKING_ID and event.value<0:
                                self.release=True
                        elif not multi and event.type==e.EV_KEY and event.code==e.BTN_TOUCH:
                            self.release=event.value==0
                        elif event.type==e.EV_SYN and event.code==e.SYN_REPORT and self.release:
                            self.release=False
                            if all(axis in self.values for axis in (x,y)):
                                self.samples.append(tuple((self.values[axis]-ranges[axis].min)/
                                     (ranges[axis].max-ranges[axis].min) for axis in (x,y)))
                                if len(self.samples)==len(TARGETS):
                                    result.extend(self.samples)
                                    app.quit()
                                    return
                                self.update()
                except BlockingIOError:
                    return
                except OSError:
                    app.quit()

            def keyPressEvent(self,event):
                if event.key()==Qt.Key_Escape:
                    app.quit()

            def paintEvent(self,event):
                painter=QPainter(self)
                painter.fillRect(self.rect(),QColor("#101923"))
                if len(self.samples)>=len(TARGETS):
                    return
                x,y=TARGETS[len(self.samples)]
                cx,cy=round(x*self.width()),round(y*self.height())
                painter.setPen(QColor("#ffb457"))
                painter.drawEllipse(cx-20,cy-20,40,40)
                painter.drawLine(cx-30,cy,cx+30,cy)
                painter.drawLine(cx,cy-30,cx,cy+30)
                painter.drawText(0,self.height()//3,self.width(),45,Qt.AlignCenter,
                                 f"Touch crosshair / Ziel berühren   {len(self.samples)+1} / {len(TARGETS)}")
        widget=Calibration()
        if output:
            screen=next((screen for screen in app.screens() if screen.name()==output),None)
            if not screen:
                raise ValueError("Unknown Qt output")
            widget.winId()
            widget.windowHandle().setScreen(screen)
        QTimer.singleShot(60000,app.quit)
        touch.grab()
        try:
            widget.showFullScreen()
            app.exec()
        finally:
            touch.ungrab()
        if not result:
            raise ValueError("Calibration cancelled or timed out")
        return fit(result,compositor_rotation=comp_rotation)


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("--device",help="Linux touchscreen event node or persistent /dev/input symlink")
    p.add_argument("--id-path")
    p.add_argument("--interactive",action="store_true")
    p.add_argument("--output",help="Qt display name for interactive sampling")
    p.add_argument("--rotate",choices=ROTATIONS,type=int,default=0)
    p.add_argument("--compositor-rotation",choices=ROTATIONS,type=int,default=0)
    p.add_argument("--swap",action="store_true")
    p.add_argument("--invert-x",action="store_true")
    p.add_argument("--invert-y",action="store_true")
    p.add_argument("--reset",action="store_true",help="Print an identity rule")
    a=p.parse_args()
    try:
        path=a.id_path
        if a.device:
            device=str(Path(a.device).resolve())
            if not re.fullmatch(r"/dev/input/event[0-9]+",device):
                raise ValueError("Use a touchscreen event node")
            props=dict(line.split("=",1) for line in subprocess.run(
                ["udevadm","info","--query=property",f"--name={device}"],check=True,
                capture_output=True,text=True,timeout=3).stdout.splitlines() if "=" in line)
            if props.get("ID_INPUT_TOUCHSCREEN")!="1":
                raise ValueError("The selected device is not classified as a touchscreen")
            if path and path!=props.get("ID_PATH"):
                raise ValueError("--id-path does not match the selected device")
            path=props.get("ID_PATH")
        if a.interactive and not a.reset:
            if not a.device or a.rotate or a.swap or a.invert_x or a.invert_y:
                raise ValueError("Interactive sampling needs a device and only the compositor rotation")
            matrix=sample(device,a.output,a.compositor_rotation)
        elif a.reset:
            matrix=rotation()
        else:
            matrix=rotation(a.rotate,swap=a.swap,invert_x=a.invert_x,invert_y=a.invert_y)
        print(rule(matrix,device_path=path),end="")
    except (ImportError,OSError,ValueError,subprocess.SubprocessError) as error:
        p.error(str(error))


if __name__=="__main__":
    main()
