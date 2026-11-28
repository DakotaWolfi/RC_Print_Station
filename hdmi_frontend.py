"""Responsive Qt Widgets frontend for the local Printstation socket."""
import argparse
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import sys
from time import monotonic
from uuid import uuid4

from PyQt5.QtCore import QEvent, QRect, QSize, Qt, QTimer, QStandardPaths
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap, QTransform
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QGraphicsScene, QGraphicsView, QPushButton, QScrollArea, QSizePolicy, QStackedLayout,
    QStyle, QStyleOptionButton, QStylePainter, QVBoxLayout, QWidget,
)

from benning_output import RESULTS, result_kind, measurement_summary, visible_measurements, report_checks, selected_fields
from benning_store import PHASES
from i18n import tr
from hdmi_keyboard import Keyboard
from hdmi_touch import DragScroll, TouchManager
from pdf_export import pdf_filename, save_pdf
from display_rotation import ANGLES, Rotation
from novelty import ITEMS, preview_path
from station_ipc import DEFAULT_SOCKET, request

ROOT=Path(__file__).resolve().parent
NATIVE=ROOT/"hmi/native/pictures"

ACTIVE=("guide","waiting","review")
PASSIVE={"state","history","people","templates","report.get","report.link","system.info","draft.editor","personality.pet","personality.treat"}
STYLE="""
QWidget { background: #101923; color: #edf4f8; font-family: 'DejaVu Sans'; font-size: 16px; }
QFrame[card="true"] { background: #182838; border: 1px solid #2d4354; border-radius: 12px; }
QLabel { background: transparent; }
QLabel[muted="true"] { color: #aebfcb; }
QLabel[title="true"] { font-size: 29px; font-weight: 700; }
QLabel[section="true"] { color: #ffd098; font-weight: 700; font-size: 15px; }
QPushButton, QComboBox, QLineEdit {
    color: #edf4f8; background: #223748; border: 1px solid #3d586c; border-radius: 9px;
    padding: 7px 12px; min-height: 32px;
}
QComboBox QAbstractItemView { background: #223748; color: #edf4f8; selection-background-color: #435f75; }
QPushButton[primary="true"] { color: #17202a; background: #ffb457; border-color: #ffb457; font-weight: 700; }
QPushButton:hover, QComboBox:hover { border-color: #86bad4; }
QPushButton:pressed { background: #44627a; }
QPushButton:focus, QLineEdit:focus, QComboBox:focus { border: 2px solid #79cbe0; }
QPushButton:disabled { color: #9eabb4; background: #1c2b38; border-color: #293e50; }
QScrollArea { border: 0; }
QScrollBar:vertical { width: 12px; background: #142431; }
QScrollBar::handle:vertical { background: #4f6a7c; border-radius: 5px; min-height: 30px; }
"""


class TouchButton(QPushButton):
    """Keep long multilingual labels fully visible at touch-sized widths."""
    def __init__(self,text):
        super().__init__(text)
        self.setMinimumHeight(48)
        policy=QSizePolicy(QSizePolicy.Ignored,QSizePolicy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def heightForWidth(self,width):
        inset=52 if not self.icon().isNull() else 22
        rect=self.fontMetrics().boundingRect(QRect(0,0,max(12,width-inset),1000),Qt.TextWordWrap,self.text())
        return max(48,rect.height()+16)

    def paintEvent(self,event):
        option=QStyleOptionButton()
        self.initStyleOption(option)
        option.text=""
        option.icon=QIcon()
        painter=QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton,option)
        colour="#17202a" if self.property("primary") else "#edf4f8"
        if not self.isEnabled():
            colour="#9eabb4"
        painter.setPen(QColor(colour))
        icon=self.icon()
        inset=10
        if not icon.isNull():
            painter.drawPixmap(13,(self.height()-23)//2,icon.pixmap(QSize(23,23)))
            inset=42
        painter.drawText(self.rect().adjusted(inset,4,-10,-4),Qt.AlignCenter|Qt.TextWordWrap,self.text())


def button(text,fn,primary=False):
    item=TouchButton(text)
    item.setProperty("primary",primary)
    item.clicked.connect(lambda _checked=False:fn())
    return item

def label(text, *, role=None):
    item=QLabel()
    item.setTextFormat(Qt.PlainText)
    item.setText(text)
    item.setWordWrap(True)
    item.setTextInteractionFlags(Qt.TextSelectableByKeyboard | Qt.TextSelectableByMouse)
    if role:
        item.setProperty(role,True)
    return item


class QRCodeWidget(QWidget):
    def __init__(self,text,size=240):
        super().__init__()
        from reportlab.graphics.barcode.qrencoder import QRCode,QRErrorCorrectLevel
        code=QRCode(None,QRErrorCorrectLevel.M)
        code.addData(text)
        code.make()
        self.matrix=code.modules
        self.setFixedSize(size,size)
        self.setAccessibleName("QR code")

    def paintEvent(self,event):
        p=QPainter(self)
        p.fillRect(self.rect(),Qt.white)
        n=len(self.matrix)
        size=self.width()//(n+8)
        margin=(self.width()-size*n)//2
        for row,values in enumerate(self.matrix):
            for col,dark in enumerate(values):
                if dark:
                    p.fillRect(margin+col*size,margin+row*size,size,size,Qt.black)


class Surface(QWidget):
    def __init__(self,socket=DEFAULT_SOCKET,transport=request,preview=False):
        super().__init__()
        self.socket,self.transport=socket,transport
        self.client=uuid4().hex
        self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix="hdmi-ipc")
        self.future=None
        self.outgoing=deque(maxlen=12)
        self.sync_pending=False
        self.next_poll=0
        self.state={}
        self.view="work"
        self.route_stack=[]
        self.notice=""
        self.connected=False
        self.epoch=None
        self.preview=preview
        self.last_signature=None
        self.debounce=0
        self.interacting=False
        self.dragging_pointer=False
        self.touch_manager=None
        self.export_job=None
        self.edit_depth=0
        self.editor_draft=None
        self.lease_at=0
        self.report=None
        self.report_id=None
        self.loaded_report=None
        self.history=[]
        self.templates=[]
        self.people=[]
        self.details={}
        self.url=""
        self.mascot_tap_at=None
        self.rotation=None
        self.confirmed_ref=None
        self.next_info=0
        self.review_page=0
        self.last_input=monotonic()
        self.blanked=False
        self.backlight=None
        self.applied_brightness=None
        self.blank=QWidget(self)
        self.blank.setStyleSheet("background:black")
        self.blank.hide()
        self.setMinimumSize(320,360)
        self.setWindowTitle("FMI Printstation")
        self.setStyleSheet(STYLE)
        self.stack=QStackedLayout(self)
        self.main_panel=QWidget()
        self.stack.addWidget(self.main_panel)
        self.overlay=None
        self.overlay_close=None
        layout=QVBoxLayout(self.main_panel)
        layout.setContentsMargins(14,10,14,10)
        layout.setSpacing(8)
        top=QHBoxLayout()
        top.setSpacing(8)
        self.logo=QPushButton("FMI")
        self.logo.setAccessibleName("FMI")
        self.logo.setFixedSize(61,48)
        self.logo.setStyleSheet("font-weight: 800; color: #ffb457; padding: 3px;")
        top.addWidget(self.logo)
        self.home=button("⌂",self.go_home)
        self.home.setFixedSize(51,48)
        self.home.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        top.addWidget(self.home)
        self.back=button("←",self.go_back)
        self.back.setFixedSize(51,48)
        self.back.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        top.addWidget(self.back)
        self.brand=label("Repair Café Riehen")
        self.brand.setStyleSheet("font-weight: 750; font-size: 19px;")
        top.addWidget(self.brand,1)
        top.addStretch()
        self.lang=button("DE / EN",self.change_language)
        self.lang.setFixedSize(93,48)
        self.lang.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        top.addWidget(self.lang)
        self.menu=button("☰",self.toggle_menu)
        self.menu.setFixedSize(53,48)
        self.menu.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Fixed)
        self.menu.setAccessibleName("Station menu")
        top.addWidget(self.menu)
        layout.addLayout(top)
        self.status=label("",role="muted")
        layout.addWidget(self.status)
        self.scroll=QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(self.scroll,1)
        self.toast=label("")
        self.toast.setStyleSheet("color:#ffcf94")
        self.toast.hide()
        layout.addWidget(self.toast)
        self.timer=QTimer(self)
        self.timer.timeout.connect(self.pump)
        if not preview:
            self.timer.start(70)
        QApplication.instance().installEventFilter(self)
        self.show_state({})

    def t(self,key,**data):
        return tr(self.state.get("language","de"),str(key),**data)

    def closeEvent(self,event):
        self.timer.stop()
        if self.overlay:
            self.close_overlay(False)
        QApplication.instance().removeEventFilter(self)
        self.pool.shutdown(wait=False,cancel_futures=True)
        super().closeEvent(event)

    def call(self,op,args=None,callback=None):
        if self.preview:
            return
        packet={"op":op,"args":args or {},"client":self.client}
        if self.epoch:
            packet["epoch"]=self.epoch
        if op!="state":
            packet["id"]=uuid4().hex
        if len(self.outgoing)>=12:
            self.notify("Eine Aktion läuft bereits.")
            return
        if op not in PASSIVE:
            if self.sync_pending:
                return
            self.sync_pending=True
            self.main_panel.setEnabled(False)
        self.outgoing.append((packet,callback))
        self.next_poll=0

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.TouchBegin,QEvent.MouseButtonPress):
            self.interacting=True
            self.debounce=monotonic()+.4
        elif event.type() in (QEvent.TouchEnd,QEvent.TouchCancel,QEvent.MouseButtonRelease):
            self.interacting=False
            self.debounce=monotonic()+.12
        if self.overlay and event.type()==QEvent.KeyPress and event.key()==Qt.Key_Escape:
            self.close_overlay(False)
            return True
        if event.type() in (QEvent.KeyPress,QEvent.MouseButtonPress,QEvent.TouchBegin,QEvent.Wheel):
            # In a deployed kiosk there is one surface per process.
            self.last_input=monotonic()
            if self.blanked:
                self.blank.hide()
                self.blanked=False
                return True
        return False

    def dim(self, brightness):
        if not self.backlight or self.applied_brightness==brightness:
            return
        self.applied_brightness=brightness
        node=Path("/sys/class/backlight")/self.backlight
        try:
            high=int((node/"max_brightness").read_text())
            (node/"brightness").write_text(str(max(1,round(high*brightness/100))))
        except (ValueError,OSError):
            self.notify("Helligkeit wird von diesem Display nicht unterstützt.")

    def pump(self):
        if self.export_job and self.export_job.done():
            try:
                dest=self.export_job.result()
                self.notify(self.t("PDF gespeichert: {path}",path=dest))
            except (OSError,ValueError):
                self.notify("PDF konnte nicht gespeichert werden.")
            self.export_job=None
        config=self.state.get("settings",{})
        if config:
            self.dim(config["brightness"])
        standby=config.get("standby",0)
        active=(self.state.get("draft") or {}).get("stage") in ACTIVE
        if self.blanked and (active or not standby):
            self.blank.hide()
            self.blanked=False
        elif not self.blanked and standby and not active and not self.edit_depth and monotonic()-self.last_input>=standby:
            self.blank.setGeometry(self.rect())
            self.blank.show()
            self.blank.raise_()
            self.blanked=True
        if self.future and self.future[0].done():
            future,packet,callback=self.future
            self.future=None
            if packet["op"] not in PASSIVE:
                self.next_poll=0
            try:
                result=future.result()
                self.connected=True
                if result["ok"]:
                    if packet["op"]=="state":
                        self.show_state(result["data"])
                    elif callback:
                        callback(result["data"])
                elif "neu gestartet" in result.get("error",""):
                    self.epoch=None
                    self.outgoing.clear()
                    self.notify(result["error"])
                else:
                    self.next_poll=0
                    self.notify(result["error"])
            except (OSError,ValueError,KeyError):
                self.connected=False
                self.outgoing.clear()
                self.next_poll=0
                self.status.setText(self.t("Verbindung zur Station wird gesucht."))
                if packet["op"]!="state":
                    self.notify("Status der Aktion prüfen. Bitte nicht sofort wiederholen.")
        if self.editor_draft and monotonic()>=self.lease_at:
            self.lease_at=monotonic()+5
            self.call("draft.editor",{"active":True,**self.editor_draft})
        if self.view=="info" and monotonic()>=self.next_info:
            self.next_info=monotonic()+2
            self.call("system.info",callback=self.set_info)
        if not self.future:
            if self.outgoing:
                packet,callback=self.outgoing.popleft()
            elif monotonic()>=self.next_poll:
                packet,callback={"op":"state","client":self.client},None
                self.next_poll=monotonic()+.35
            else:
                return
            self.future=(self.pool.submit(self.transport,self.socket,packet),packet,callback)

    def notify(self,text):
        self.notice=self.t(text) if text else ""
        self.toast.setText(self.notice)
        self.toast.setVisible(bool(self.notice))

    def show_state(self,state):
        if not any(packet["op"] not in PASSIVE for packet,_ in self.outgoing):
            self.sync_pending=False
            self.main_panel.setEnabled(True)
        new_epoch=state.get("epoch")
        if self.epoch and new_epoch!=self.epoch:
            self.report_id=self.loaded_report=self.report=None
            self.url=""
            self.view="work"
            self.outgoing.clear()
            if self.overlay and not isinstance(self.overlay,Keyboard):
                self.close_overlay(False)
            self.notify("Die Station wurde neu gestartet.")
        self.epoch=new_epoch
        if self.state.get("download_base")!=state.get("download_base"):
            self.url=""
            self.qr_requested=None
        self.state=state
        work=state.get("draft") or {}
        tests=state.get("receiver") or {}
        status={"waiting":"Verbunden","receiving":"Empfang läuft ...","imported":"Import gespeichert",
                "disconnected":"Nicht verbunden","searching":"Suche Tester / USB",
                "simulation":"Simulation","file":"Datei","error":"Kommunikationsfehler",
                "interrupted":"Transfer unterbrochen"}
        value=self.t(status.get(tests.get("state"),"Verbindung zur Station wird gesucht."))
        if tests.get("detail"):
            value+="  ·  "+self.t(tests["detail"])
        self.status.setText("BENNING  /  "+value)
        self.status.setAccessibleName(self.status.text())
        self.home.setAccessibleName(self.t("Startseite"))
        self.back.setAccessibleName(self.t("Zurück"))
        self.menu.setAccessibleName(self.t("Einstellungen"))
        self.lang.setText("EN / DE" if state.get("language")=="en" else "DE / EN")
        signature={k:v for k,v in state.items() if k not in ("sequence","receiver")}
        signature["receiver"]=(tests.get("state"),tests.get("detail"))
        if (self.view in ("home","work","pet") and self.last_signature and signature!=self.last_signature
                and signature.keys()==self.last_signature.keys()
                and all(signature[key]==self.last_signature[key] for key in signature if key!="personality")):
            self.last_signature=signature
            personality=state["personality"]
            if self.view=="pet" and hasattr(self,"pet_amount"):
                self.pet_amount.setText(self.t("Streicheleinheiten: {count}",count=personality.get("pets") or 0))
                self.pet_response.setText(self.t(personality["pet_reply"]))
            return
        if (signature!=self.last_signature and not self.edit_depth and not self.dragging_pointer and
                (not self.interacting or monotonic()>self.debounce) and
                self.scroll.verticalScrollBar().isSliderDown() is False):
            self.last_signature=signature
            if self.view in ("pet","novelty","novelty_preview","achievements") and (state.get("settings",{}).get("professional") or work.get("stage") in ACTIVE):
                self.view="work"
            self.render()

    def route(self,view,remember=True):
        if self.overlay:
            return
        if remember and view!=self.view:
            self.route_stack=(self.route_stack+[self.view])[-12:]
        self.view=view
        self.notify("")
        self.render()

    def change_language(self):
        self.call("settings.save",{"values":{"language":"de" if self.state.get("language")=="en" else "en"}})

    def go_home(self):
        self.route_stack.clear()
        self.route("home" if self.state.get("draft") else "work",False)

    def go_back(self):
        if self.overlay:
            return
        if self.route_stack:
            self.route(self.route_stack.pop(),False)
        elif self.view!="work":
            self.route("work",False)
        else:
            stage=(self.state.get("draft") or {}).get("stage")
            if stage=="guide":
                self.draft_action("guide.back")
            elif stage in ("waiting","review"):
                self.draft_action("review.back")
            else:
                self.go_home()

    def toggle_menu(self):
        self.route("settings")


    def leisure(self):
        return bool(self.state and not self.state.get("settings",{}).get("professional") and
                    (self.state.get("draft") or {}).get("stage") not in ACTIVE)

    def pet_gate(self):
        if not self.leisure():
            return
        now=monotonic()
        if self.mascot_tap_at is not None and now-self.mascot_tap_at<=.7:
            self.mascot_tap_at=None
            self.route("pet")
        else:
            self.call("personality.pet")
            self.mascot_tap_at=now

    def open_overlay(self,pane,closed):
        if self.overlay:
            pane.deleteLater()
            return False
        self.overlay=pane
        self.overlay_close=closed
        self.edit_depth+=1
        self.stack.addWidget(pane)
        self.stack.setCurrentWidget(pane)
        pane.setFocus()
        return True

    def close_overlay(self,accepted):
        pane,self.overlay=self.overlay,None
        if pane is None:
            return
        callback,self.overlay_close=self.overlay_close,None
        self.stack.setCurrentWidget(self.main_panel)
        self.stack.removeWidget(pane)
        pane.hide()
        self.edit_depth-=1
        if callback:
            callback(accepted)
        pane.deleteLater()
        self.render()

    def dialog(self,title,body,action=None,closed=None):
        pane=QWidget(self)
        pane.setObjectName("operatorOverlay")
        layout=QVBoxLayout(pane)
        layout.setContentsMargins(16,14,16,14)
        layout.addWidget(label(self.t(title),role="title"))
        text=QScrollArea()
        text.setWidgetResizable(True)
        text.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        content=label(self.t(body))
        content.setAlignment(Qt.AlignTop|Qt.AlignLeft)
        text.setWidget(content)
        layout.addWidget(text,1)
        choices=QHBoxLayout()
        choices.addWidget(button(self.t("Abbrechen" if action else "Schliessen"),lambda:self.close_overlay(False)))
        if action:
            choices.addWidget(button(self.t("Bestätigen"),lambda:self.close_overlay(True),True))
        layout.addLayout(choices)
        context=self.ref()
        def finished(accepted):
            if closed:
                closed(accepted)
            if accepted and action:
                self.confirmed_ref=context
                try:
                    action()
                finally:
                    self.confirmed_ref=None
        return self.open_overlay(pane,finished)

    def question(self,title,action):
        return self.dialog("Bestätigen",title,action)

    def enter_text(self,title,value,limit,callback,secret=False,mode="text",closed=None):
        editor=Keyboard(self,self.t(title),value,limit,secret,mode,embedded=True)
        def finish(accepted):
            try:
                if accepted:
                    callback(editor.edit.text())
            finally:
                editor.edit.clear()
                if closed:
                    closed()
        editor.finished.connect(lambda code:self.close_overlay(bool(code)))
        if not self.open_overlay(editor,finish):
            if closed:
                closed()
            return
        editor.edit.setFocus()
        editor.edit.selectAll()

    def select(self,title,values,current,callback):
        pane=QWidget(self)
        pane.setObjectName("operatorOverlay")
        layout=QVBoxLayout(pane)
        self.section(layout,title)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner=QWidget()
        choices=QVBoxLayout(inner)
        selected=[current]
        def pick(index):
            selected[0]=index
            self.close_overlay(True)
        for i,value in enumerate(values):
            choices.addWidget(button(self.t(value),lambda i=i:pick(i),i==current))
        choices.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll,1)
        layout.addWidget(button(self.t("Abbrechen"),lambda:self.close_overlay(False)))
        self.open_overlay(pane,lambda ok:callback(selected[0]) if ok else None)

    def ref(self):
        d=self.state.get("draft") or {}
        return {"draft":d.get("id"),"version":d.get("version")}

    def draft_action(self,op,extra=None):
        self.call(op,dict(self.confirmed_ref or self.ref(),**(extra or {})))

    def edit(self,key,previous,value,ref=None):
        self.call("draft.edit",dict(ref or self.ref(),previous={key:previous},changes={key:value}))

    def field(self,key,title,value,limit):
        ref=self.ref()
        lease={"draft":ref["draft"],"field":key}
        def edit_locked(_=None):
            if self.overlay:
                self.call("draft.editor",{"active":False,**lease})
                return
            self.editor_draft=lease
            self.lease_at=monotonic()+5
            def release():
                self.editor_draft=None
                self.call("draft.editor",{"active":False,**lease})
            self.enter_text(title,value,limit,lambda text:self.edit(key,value,text,ref),
                            mode="ticket" if key=="ticket" else "text",closed=release)
        def open_editor():
            if self.overlay or self.editor_draft:
                return
            if self.preview:
                edit_locked()
            else:
                self.call("draft.editor",{"active":True,**lease},edit_locked)
        item=button(self.t(title)+"  ·  "+(value or self.t("Eingeben")),open_editor)
        item.setToolTip(value)
        return item

    def toggle_report_language(self):
        language="de" if self.state.get("report_language")=="en" else "en"
        self.draft_action("language.report",{"language":language})

    def section(self,layout,title,subtitle=""):
        layout.addWidget(label(self.t(title),role="title"))
        if subtitle:
            layout.addWidget(label(self.t(subtitle),role="muted"))

    def columns(self,widgets, *, limit=2):
        panel=QWidget()
        grid=QGridLayout(panel)
        grid.setContentsMargins(0,0,0,0)
        grid.setSpacing(7)
        count=min(limit,3 if self.width()>=760 else 2 if self.width()>=600 else 1)
        for i,w in enumerate(widgets):
            grid.addWidget(w,i//count,i%count)
        for i in range(count):
            grid.setColumnStretch(i,1)
        return panel

    def actions(self,layout,items,limit=2):
        layout.addWidget(self.columns([button(self.t(name),fn,primary) for name,fn,primary in items],limit=limit))

    def art(self,key,*,card=False):
        lang=self.state.get("language")
        path=NATIVE/f"g_{key}_en.png"
        if lang!="en" or not path.exists():
            path=NATIVE/f"g_{key}.png"
        item=QLabel()
        item.setAlignment(Qt.AlignCenter)
        icon=ROOT/"assets/benning"/f"{key}.png"
        if icon.is_file():
            path=icon
        size=(114,114) if card else (min(700,max(250,self.width()-62)),180)
        item.setPixmap(QPixmap(str(path)).scaled(*size,Qt.KeepAspectRatio,Qt.SmoothTransformation))
        item.setAccessibleName("BENNING ST 725")
        return item

    def render(self):
        current=self.scroll.verticalScrollBar().value()
        focus=QApplication.focusWidget()
        focus_name=focus.accessibleName() if focus and hasattr(focus,"accessibleName") else ""
        scroll_key=(self.view,self.state.get("draft",{}).get("stage") if self.state.get("draft") else None,
                    (self.state.get("guide") or {}).get("step"))
        if scroll_key!=getattr(self,"scroll_key",None):
            current=0
        self.scroll_key=scroll_key
        old=self.scroll.takeWidget()
        if old:
            old.deleteLater()
        body=QWidget()
        v=QVBoxLayout(body)
        v.setContentsMargins(5,4,5,4)
        v.setSpacing(9)
        if not self.state:
            self.section(v,"FMI Printstation","Verbindung zur Station wird gesucht.")
        else:
            menus={"home":self.render_home,"history":self.render_history,"settings":self.render_settings,
                   "wifi":self.render_wifi,"people":self.render_people,"templates":self.render_templates,
                   "connection":self.render_connection,"download":self.render_download,"achievements":self.render_achievements,
                   "printer":self.render_printer,"display":self.render_display,
                   "tester":self.render_tester,"personality":self.render_personality,"system":self.render_system,
                   "report":self.render_report,"pet":self.render_pet,"info":self.render_info,"novelty":self.render_novelty,"novelty_preview":self.render_novelty_preview}
            if self.view in menus:
                menus[self.view](v)
            else:
                self.render_work(v)
        v.addStretch()
        for item in body.findChildren(QPushButton):
            if not item.accessibleName():
                item.setAccessibleName(item.text())
        self.scroll.setWidget(body)
        if current:
            self.scroll.verticalScrollBar().setValue(current)
        if focus_name:
            match=next((item for item in body.findChildren(QPushButton) if item.accessibleName()==focus_name),None)
            if match:
                match.setFocus()

    def render_work(self,v):
        d=self.state.get("draft")
        stage=d.get("stage") if d else None
        if stage in ACTIVE and self.state.get("control") in ("other","available"):
            self.section(v,"Aktive Prüfung")
            if self.state["control"]=="other":
                v.addWidget(label(self.t("Diese Prüfung wird an einer anderen Anzeige bedient.")))
                v.addWidget(label(self.t("Bei Verbindungsverlust wird Fortsetzen nach 20 Sekunden angeboten.")))
            else:
                v.addWidget(label(self.t("Prüfaufbau und Anzeige am Tester vor dem Fortsetzen erneut prüfen.")))
                self.actions(v,[("An dieser Anzeige fortsetzen",lambda:self.question(
                    "Prüfung auf dieser Anzeige fortsetzen?",lambda:self.draft_action(
                    "draft.control",{"action":"resume","confirmed":True})),True)])
            return
        if stage=="entry":
            return self.render_entry(v,d)
        if stage=="guide":
            self.render_guide(v,d)
        elif stage in ("waiting","review"):
            self.render_import(v,d,stage=="review")
        elif stage=="report" and self.state.get("report")!=getattr(self,"dismissed",None):
            self.render_report(v)
        else:
            self.render_home(v)
        if stage in ACTIVE and self.state.get("control")=="yours":
            self.actions(v,[("Anzeige wechseln",lambda:self.question(
                "Prüfung für eine andere Anzeige freigeben?",lambda:self.draft_action(
                "draft.control",{"action":"release","confirmed":True})),False)])

    def render_home(self,v):
        self.section(v,"FMI Printstation","Prüfprotokolle")
        if self.state.get("draft") and self.state["draft"]["stage"]!="report":
            self.actions(v,[("Prüfung fortsetzen",lambda:self.route("work",False),True)])
        else:
            self.actions(v,[("Geführte Prüfung",lambda:self.begin("guided"),True),
                            ("Direkt",lambda:self.begin("direct"),False)])
        self.actions(v,[("Verlauf",self.open_history,False),("Web-Verbindung",lambda:self.route("connection"),False)])
        if self.leisure():
            from hdmi_personality import Wolf
            mascot=Wolf(self.pet_gate,home=True)
            mascot.setFixedSize(160,min(155,max(92,self.height()//4)))
            v.addWidget(mascot,alignment=Qt.AlignHCenter)
            v.addWidget(button(self.t("Werkstattwolf"),lambda:self.route("pet")))


    def begin(self,mode):
        self.dismissed=None
        self.route("work",False)
        self.call("draft.new",{"mode":mode})

    def render_entry(self,v,d):
        self.section(v,"Prüfung erfassen","Geführte Prüfung" if d["mode"]=="guided" else "Direkt")
        v.addWidget(self.columns([self.field("ticket","Prüfnummer",d["ticket"],32),
                                  self.field("device","Gerätebeschreibung",d["device"],64)]))
        v.addWidget(self.columns([button(self.t("Vorlagen"),self.open_templates),
                                  button(self.t("Prüfperson"),self.open_people),
                                  button(self.t("Bericht: {language}",language=self.state["report_language"].upper()),
                                         self.toggle_report_language)]))
        if self.state.get("recovery_note"):
            v.addWidget(label(self.t(self.state["recovery_note"]),role="section"))
        ref={"draft":d["id"],"version":d["version"]}
        phase_label=self.t("Prüfart")+" · "+self.t(PHASES[d["phase"]])
        v.addWidget(button(phase_label,lambda:self.select("Prüfart",PHASES,d["phase"],
                                      lambda n:self.edit("phase",d["phase"],n,ref))))
        self.actions(v,[("Prüfung beginnen",lambda:self.draft_action("exam.start"),True),
                        ("Vorhandene Messung",lambda:self.draft_action("review.find"),False),
                        ("Entwurf verwerfen",lambda:self.question("Entwurf verwerfen?",
                         lambda:self.draft_action("draft.discard",{"confirmed":True})),False)])

    def render_guide(self,v,d):
        g=self.state.get("guide")
        if not g:
            return
        ref=self.ref()
        self.section(v,g["title"])
        v.addWidget(label(self.t("Phase {step}  ·  BENNING ST 725 CH",step=g["phase"]),role="section"))
        if g["art"]!="lcd" and not g.get("rows"):
            v.addWidget(self.art(g["art"]))
        if not (g["step"]=="start" and g.get("rows")):
            v.addWidget(label(g["instruction"][self.state["language"]]))
        cards=[]
        horizontal=self.width()>=760
        for art,title,body in g.get("rows",()):
            card=QWidget()
            row=QVBoxLayout(card) if horizontal else QHBoxLayout(card)
            row.setContentsMargins(0,0,0,0)
            if art:
                image=self.art(art,card=True)
                row.addWidget(image)
            copy=QVBoxLayout()
            copy.addWidget(label(self.t(title),role="section"))
            copy.addWidget(label(self.t(body)))
            row.addLayout(copy,1)
            cards.append(card)
        if cards:
            v.addWidget(self.columns(cards,limit=3) if horizontal else self.columns(cards,limit=1))
        if g["step"]=="exam":
            if not self.people and d["examiner"] and not getattr(self,"people_requested",False):
                self.people_requested=True
                self.call("people",callback=lambda rows:self.set_list("people",rows,refresh=True))
            self.actions(v,[("Prüfperson",self.open_people,False)])
            person=next((p["name"] for p in self.people if p["id"]==d["examiner"]),None)
            if person:
                v.addWidget(label(person,role="muted"))
            v.addWidget(self.field("remarks","Bemerkung",d["remarks"],64))
            values=("Offen","Ohne Befund","Mangel","Nicht geprüft")
            ref=self.ref()
            v.addWidget(button(self.t("Funktion")+" · "+self.t(g["functional"]),
                lambda:self.select("Funktion",values,values.index(g["functional"]),
                    lambda n:self.call("exam.function",dict(ref,value=values[n])))))
            self.actions(v,[("Zum Import" if g["stored"] and not g["blocked"] else "Unvollständig speichern",
                             lambda:self.draft_action("exam.submit"),True)])
        else:
            def choose(index):
                self.call("guide.choose",dict(ref,choice=index,step=g["step"]))
            options=g.get("actions")
            if options:
                indices=options["observations"]
                actions=[(g["choices"][i],lambda i=i:choose(i),False) for i in options["primary"]]
                actions.append(("Meldung oder Unsicherheit",lambda:self.select(
                    "Anzeige am BENNING",tuple(g["choices"][i] for i in indices),-1,
                    lambda n:choose(indices[n])),False))
                self.actions(v,actions,limit=3)
                v.addWidget(label(self.t("Während der Messung warten. Danach Ergebnis oder Meldung wählen."),role="muted"))
            else:
                self.actions(v,[(choice,lambda i=i:choose(i),i==0)
                                for i,choice in enumerate(g["choices"])],limit=3)
        self.actions(v,[("Zurück",lambda:self.draft_action("guide.back"),False),
                        ("Hilfe",lambda:self.dialog("Hilfe",g["help"]),False),
                        ("Abbrechen",lambda:self.question("Prüfung abbrechen?",
                          lambda:self.draft_action("guide.cancel",{"confirmed":True})),False)])

    def render_import(self,v,d,review):
        self.section(v,"Messung bestätigen" if review else "Messung übertragen")
        if not review:
            v.addWidget(self.art(self.state["import_art"]))
            v.addWidget(label(self.t(self.state["import_body"])))
            error=self.state["receiver"].get("detail")
            if error:
                v.addWidget(label(self.t(error),role="section"))
        note=self.state.get("wait_note")
        if note:
            v.addWidget(label(self.t(note),role="muted"))
        reset=self.state["receiver"].get("reset")
        if self.state["receiver"].get("state")=="reset-pending" and reset:
            self.actions(v,[("Speicher-Reset bestätigen",lambda:self.question(
                "Speicher am BENNING geleert und USB-Export vollständig empfangen?",
                lambda:self.draft_action("import.reset",{"reset":reset,"confirmed":True})),False)])
            self.actions(v,[("Zurück",lambda:self.draft_action("review.back"),False)])
            return
        selected=self.state.get("selected")
        if review:
            if selected:
                v.addWidget(label(f"{selected['slot']}  ·  {selected['date']}  ·  {selected['verdict']}",role="section"))
            entries=[]
            slots=self.state["slots"]
            self.review_page=min(self.review_page,max(0,(len(slots)-1)//16))
            for row in slots[self.review_page*16:self.review_page*16+16]:
                tag=f"{row['slot']} · {row['date']} · {row['verdict']}"
                key=row["key"]
                entries.append(button(tag,lambda _=False,k=key:self.draft_action("review.select",{"record":k})))
            if selected:
                same=selected.get("origin")=="identical"
                def accept():
                    self.draft_action("review.confirm",{"record":selected["key"],"same_reading_confirmed":same})
                self.actions(v,[("Messung bestätigen",lambda:self.question(
                    "Identischer Datensatz. Wurde die Prüfung neu durchgeführt?",accept) if same else accept(),True)])
            if entries:
                v.addWidget(self.columns(entries))
                controls=[]
                if self.review_page:
                    controls.append(("Zurückblättern",lambda:self.change_slot_page(-1),False))
                if (self.review_page+1)*16<len(slots):
                    controls.append(("Weitere",lambda:self.change_slot_page(1),False))
                if controls:
                    self.actions(v,controls)
        else:
            self.actions(v,[("Vorhandene Messung",lambda:self.draft_action("review.manual"),False)])
        self.actions(v,[("Zurück",lambda:self.draft_action("review.back"),False)])

    def change_slot_page(self,delta):
        self.review_page+=delta
        self.scroll.verticalScrollBar().setValue(0)
        self.render()

    def open_history(self):
        self.call("history",callback=self.set_history)
        self.route("history")

    def set_history(self,rows):
        self.history=rows
        if self.view=="history":
            self.render()

    def render_history(self,v):
        self.section(v,"Verlauf")
        for row in self.history:
            title=f"#{row['id']} · {row.get('ticket') or ''}  {row.get('device') or ''}"
            v.addWidget(button(title,lambda _=False,i=row["id"]:self.open_report(i)))
        self.actions(v,[("Zurück",lambda:self.route("work"),False)])

    def open_report(self,ident):
        self.report_id=ident
        self.url=""
        self.route("report")

    def set_report(self,report,ident):
        if self.report_id==ident or (self.view=="work" and self.state.get("report")==ident):
            self.loaded_report=ident
            self.report=report
            self.render()

    def render_report(self,v):
        ident=self.report_id if self.view=="report" else self.state.get("report")
        self.section(v,"Prüfprotokoll")
        if not ident:
            return
        if self.loaded_report!=ident:
            if not self.preview and not any(packet["op"]=="report.get" for packet,_ in self.outgoing):
                self.call("report.get",{"report":ident},lambda report:self.set_report(report,ident))
            v.addWidget(label(self.t("Bitte warten ...")))
            return
        r=self.report
        language=self.state["language"]
        kind=result_kind(r)
        status=label(self.t(RESULTS[kind][0]))
        status.setStyleSheet(f"color:{RESULTS[kind][1]};font-size:34px;font-weight:800;padding:10px 0px;")
        v.addWidget(status)
        v.addWidget(label("   ·   ".join(f"{self.t(key)}  {value}" for key,value in selected_fields(r,language))))
        for measurement in visible_measurements(r):
            name,value,limit,state,kind=measurement_summary(measurement,language=language)
            row=label("    ".join(filter(None,(name,value,limit,state))))
            row.setStyleSheet(f"color:{RESULTS[kind][1]};padding:4px 0px;")
            v.addWidget(row)
        for key,value in report_checks(r,language):
            v.addWidget(label(f"{self.t(key)}  ·  {value}",role="muted"))
        notes=self.state.get("print_note")
        if notes:
            v.addWidget(label(self.t(notes),role="section"))
        self.actions(v,[("Beleg drucken",lambda:self.question("Beleg jetzt drucken?",lambda:
                             self.call("report.print",{"report":ident,"confirmed":True})),True),
                        ("PDF / QR-Code",lambda:self.open_download(ident),False),
                        ("Zurück",lambda:self.dismiss_report(ident),False)])

    def open_download(self,ident):
        self.url=""
        self.url_report=ident
        self.qr_requested=None
        self.route("download")

    def set_url(self,url,ident,base):
        if self.view=="download" and self.url_report==ident and self.state.get("download_base")==base:
            self.url=url
            self.render()

    def render_download(self,v):
        self.section(v,"PDF herunterladen")
        if self.report:
            kind=result_kind(self.report)
            result=label(self.t(RESULTS[kind][0]),role="title")
            result.setStyleSheet(f"color:{RESULTS[kind][1]}; font-weight:800; font-size:30px;")
            v.addWidget(result)
            for key,value in report_checks(self.report,self.state["language"]):
                if key in ("Protokoll","Freigabe"):
                    v.addWidget(label(f"{self.t(key)} · {value}",role="muted"))
        if self.url:
            v.addWidget(QRCodeWidget(self.url),alignment=Qt.AlignHCenter)
            v.addWidget(label(self.url))
        else:
            base=self.state.get("download_base")
            if base and getattr(self,"qr_requested",None)!=base:
                self.qr_requested=base
                ident=self.url_report
                self.call("report.link",{"report":ident},lambda url:self.set_url(url,ident,base))
            v.addWidget(label(self.t("Bitte warten ..." if base else "PDF-Link nicht verfügbar. Bitte erneut öffnen.")))
            if base:
                v.addWidget(button(self.t("Aktualisieren"),lambda:self.open_download(self.url_report)))
        if self.report and self.loaded_report==self.url_report:
            self.actions(v,[("PDF lokal speichern",self.confirm_export,True)])
        self.actions(v,[("Zurück",self.go_back,False)])

    def confirm_export(self):
        if self.export_job or self.loaded_report!=self.url_report:
            return
        directory=Path(os.environ.get("FMI_PDF_EXPORT_DIR") or
                       QStandardPaths.writableLocation(QStandardPaths.DownloadLocation))
        report,ident=self.report,self.url_report
        target=directory/pdf_filename(report,ident)
        self.question(self.t("PDF hier speichern? {path}",path=target),
                      lambda:setattr(self,"export_job",self.pool.submit(save_pdf,directory,report,ident)))

    def render_connection(self,v):
        self.section(v,"Web-Verbindung")
        web=self.state.get("web") or {}
        status={"reachable":"Web-HMI im Stationsnetz","no-address":"Web-HMI wartet auf eine lokale Adresse.",
                "loopback":"Web-HMI nur lokal am Stationsrechner.","proxy":"Web-HMI über HTTPS."}
        v.addWidget(label(self.t(status.get(web.get("status"),"Web-HMI ist nicht verfügbar.")),role="section"))
        if web.get("hostname") or web.get("port"):
            v.addWidget(label(" · ".join(str(v) for v in (web.get("hostname"),web.get("ip"),web.get("port")) if v)))
        wifi=self.state.get("wifi") or {}
        if wifi.get("ssid"):
            v.addWidget(label(self.t("WLAN")+" · "+wifi["ssid"]))
        if wifi.get("ssid")=="FMI-RC-Printstation":
            v.addWidget(label(self.t("Gerät mit dem geschützten Stations-Hotspot verbinden.")))
        urls=web.get("urls") or []
        if urls:
            v.addWidget(QRCodeWidget(urls[0]),alignment=Qt.AlignHCenter)
            for url in urls:
                v.addWidget(label(url))
        self.actions(v,[("Zurück",self.go_back,False)])

    def dismiss_report(self,ident):
        if self.view=="report":
            self.route("history")
        else:
            self.dismissed=ident
            self.route("work")

    def open_templates(self):
        self.call("templates",callback=lambda rows:self.set_list("templates",rows))
        self.route("templates")

    def set_list(self,view,rows,refresh=False):
        setattr(self,view,rows)
        if self.view==view or refresh:
            self.render()

    def render_templates(self,v):
        self.section(v,"Vorlagen")
        d=self.state.get("draft") or {}
        if d.get("stage")=="entry":
            for name,_ in self.templates:
                v.addWidget(button(name,lambda _=False,text=name:self.choose_template(d,text)))
        self.actions(v,[("Zurück",lambda:self.route("work"),False)])

    def choose_template(self,d,value):
        self.edit("device",d["device"],value,{"draft":d["id"],"version":d["version"]})
        self.route("work")

    def open_people(self):
        self.call("people",callback=lambda rows:self.set_list("people",rows))
        self.route("people")

    def render_people(self,v):
        self.section(v,"Prüfperson auswählen")
        for person in self.people:
            panel=QVBoxLayout()
            actions=QHBoxLayout()
            name=button(person["name"],lambda _=False,p=person:self.choose_person(p))
            name.setEnabled(person["active"] and ((self.state.get("draft") or {}).get("stage")=="entry" or
                              (self.state.get("guide") or {}).get("step")=="exam"))
            panel.addWidget(name)
            actions.addWidget(button(self.t("Bearbeiten"),lambda _=False,p=person:self.edit_person(p)))
            actions.addWidget(button(self.t("Deaktivieren" if person["active"] else "Aktivieren"),
                            lambda _=False,p=person:self.question("Änderung bestätigen?",lambda:self.call(
                                "person.active",{"examiner":p["id"],"active":not p["active"],"confirmed":True},
                                lambda _:self.open_people()))))
            panel.addLayout(actions)
            v.addLayout(panel)
        self.actions(v,[("Neu",lambda:self.edit_person({}),True)])

    def choose_person(self,p):
        self.call("person.pick",dict(self.ref(),examiner=p["id"]),lambda _:self.route("work"))

    def edit_person(self,p):
        self.enter_text("Prüfperson",p.get("name",""),48,lambda n:self.call(
                        "person.save",{"name":n,"examiner":p.get("id")},lambda _:self.open_people()))

    def configure(self,key,value):
        self.call("settings.save",{"values":{key:value}})

    def render_settings(self,v):
        self.section(v,"Einstellungen","Station")
        entries=(
            ("Drucker","printer",lambda:self.route("printer")),
            ("WLAN","wifi",lambda:self.route("wifi")),
            ("Anzeige","display",lambda:self.route("display")),
            ("Prüfgerät","tester",lambda:self.route("tester")),
            ("Prüfpersonen","people",self.open_people),
            ("Persönlichkeit","personality",lambda:self.route("personality")),
            ("System","system",lambda:self.route("system")),
        )
        tiles=[]
        for name,icon,fn in entries:
            tile=button(self.t(name),fn)
            tile.setIcon(QIcon(str(ROOT/"assets/interfaces"/f"{icon}.svg")))
            tiles.append(tile)
        v.addWidget(self.columns(tiles,limit=3))

    def render_personality(self,v):
        self.section(v,"Persönlichkeit")
        c=self.state["settings"]
        self.actions(v,[("Professioneller Modus: Aus" if not c["professional"] else "Professioneller Modus: Ein",
                         lambda:self.configure("professional",not c["professional"]),True)])

    def render_tester(self,v):
        self.section(v,"Prüfgerät","BENNING ST 725")
        r=self.state["receiver"]
        v.addWidget(label(f"{r.get('transport') or r.get('source') or r.get('mode','')}"))
        v.addWidget(label(self.status.text(),role="muted"))
        if "tester_mode" in self.state["settings"]:
            self.actions(v,[(name,lambda m=mode:self.question("Änderung bestätigen?",
                            lambda:self.configure("tester_mode",m)),False)
                            for mode,name in (("auto","Automatisch"),("usb","USB-CSV"),("rs232","RS232-PRINT"),
                                              ("file","Datei"),("simulation","Simulation"))])

    def render_printer(self,v):
        self.section(v,"Drucker")
        c=self.state["settings"]
        self.actions(v,[(f"Epson  {c['printer_host']}",lambda:self.enter_text("IPv4-Adresse",c["printer_host"],15,
                        lambda x:self.configure("printer_host",x),mode="ipv4"),False),
                        (f"TCP  {c['printer_port']}",lambda:self.enter_text("TCP-Port",str(c["printer_port"]),5,
                        lambda x:self.configure("printer_port",int(x)) if x.isascii() and x.isdecimal() else self.notify("Ungültige Eingabe."),mode="number"),False),
                        ("TCP-Verbindung testen",lambda:self.call("printer.probe"),False),
                        ("Testbeleg drucken",lambda:self.question("Beleg jetzt drucken?",lambda:self.call("printer.test",{"confirmed":True})),False),
                        ("Kopf: Grafik" if c["graphic"] else "Kopf: Text",lambda:self.configure("graphic",not c["graphic"]),False),
                        (f"{self.t('Papiervorschub')}  {c['feed_mm']} mm",lambda:self.enter_text("Papiervorschub",
                         str(c["feed_mm"]),3,lambda x:self.configure("feed_mm",int(x)) if x.isascii() and x.isdecimal() else self.notify("Ungültige Eingabe."),mode="number"),False)])
        for element in ("probe_note","print_note"):
            if self.state.get(element):
                v.addWidget(label(self.t(self.state[element]),role="muted"))

    def render_display(self,v):
        self.section(v,"Anzeige")
        c=self.state["settings"]
        self.actions(v,[(self.t("Helligkeit")+" "+str(c["brightness"])+" %",
                        lambda:self.configure("brightness",next((n for n in (25,50,75,100) if n>c["brightness"]),25)),False),
                        (self.t("Standby")+" "+str(c["standby"])+" s",
                        lambda:self.configure("standby",next((n for n in (30,60,120,300,600) if n>c["standby"]),0)),False)])
        if self.rotation:
            self.actions(v,[(f"{n}°"+(" ✓" if n==self.rotation.saved else ""),
                             lambda n=n:self.preview_rotation(n),False) for n in ANGLES])
        self.actions(v,[("Touchscreen kalibrieren",self.calibrate_touch,False)])
        if self.touch_manager and self.touch_manager.raw:
            self.actions(v,[("Touch-Kalibrierung zurücksetzen",lambda:self.question(
                "Gespeicherte Touch-Kalibrierung zurücksetzen?",self.reset_touch),False)])

    def reset_touch(self):
        try:
            self.touch_manager.reset()
        except OSError:
            self.notify("Anzeigeeinstellung konnte nicht gespeichert werden.")

    def calibrate_touch(self):
        manager=self.touch_manager
        devices=manager.devices(manager.preferred) if manager else []
        if not devices:
            self.dialog("Touchscreen kalibrieren","Kein unterstützter Linux-Touchscreen gefunden.")
        elif len(devices)==1:
            manager.start(*devices[0])
        else:
            self.select("Touchscreen auswählen",tuple(d[1]+" · "+d[0] for d in devices),-1,
                        lambda n:manager.start(*devices[n]))

    def preview_rotation(self,angle):
        if self.overlay or not self.rotation:
            return
        self.rotation.start(angle)
        def finish(committed):
            try:
                self.rotation.done(committed)
            except OSError:
                self.notify("Anzeigeeinstellung konnte nicht gespeichert werden.")
        self.dialog("Anzeige drehen", "Ausrichtung innerhalb von 15 Sekunden bestätigen.",
                    lambda:None,closed=finish)
        pane=self.overlay
        timer=QTimer(pane,singleShot=True)
        timer.timeout.connect(lambda:self.close_overlay(False) if self.overlay is pane else None)
        timer.start(15000)

    def render_system(self,v):
        self.section(v,"System")
        self.actions(v,[("Engineering-Modus",self.open_info,False)])
        if self.state["power"]["enabled"]:
            self.actions(v,[("Jetzt neu starten",lambda:self.question("Station neu starten?",lambda:
                             self.call("power.reboot",{"confirmed":True})),False),
                            ("Jetzt ausschalten",lambda:self.question("Station ausschalten?",lambda:
                             self.call("power.halt",{"confirmed":True})),False)])
        if self.state["power"]["note"]:
            v.addWidget(label(self.t(self.state["power"]["note"]),role="section"))

    def render_wifi(self,v):
        self.section(v,"WLAN")
        wifi=self.state["wifi"]
        v.addWidget(label("  ·  ".join(filter(None,(wifi.get("ssid"),wifi.get("ip"),self.t(wifi.get("note",""))))),
                          role="muted"))
        self.actions(v,[("Netzwerke suchen",lambda:self.call("wifi.scan"),True),
                       ("Hotspot beenden" if wifi["ssid"]=="FMI-RC-Printstation" else "FMI Hotspot starten",
                         lambda:self.question("Änderung bestätigen?",lambda:self.call(
                            "wifi.stop" if wifi["ssid"]=="FMI-RC-Printstation" else "wifi.hotspot",{"confirmed":True})),False)])
        for net in wifi.get("networks",[])[:80]:
            text=f"{net['name']}   ·   {net['signal']} %  ·  {self.t(net['security'])}"
            if net["saved"]:
                text+="  ·  "+self.t("Gespeichert")
            v.addWidget(button(text,lambda _=False,n=net:self.join(n)))
        self.actions(v,[("Zurück",self.go_back,False)])

    def join(self,net):
        action=lambda password:self.call("wifi.connect",{"network":net["id"],"password":password})
        if net["saved"] or net["security"]=="Offen":
            self.question("WLAN verbinden?",lambda:action(""))
        else:
            self.enter_text("Passwort","",64,action,True)

    def open_info(self):
        self.call("personality.engineering")
        self.call("system.info",callback=self.set_info)
        self.route("info")

    def set_info(self,details):
        if details==self.details:
            return
        self.details=details
        if self.view=="info":
            self.render()

    def render_info(self,v):
        self.section(v,"Engineering-Modus","Diagnose · nur Anzeige")
        if self.details:
            temperature,load,ram,disk,uptime,printer=self.details["system"]
            exams,passed=self.details["reports"]
            pets,(requests,tokens,_)=self.details["personality"]
            cells={
                "CPU-Temperatur":f"{temperature} °C" if temperature is not None else self.t("Nicht verfügbar"),
                "CPU-Last (1 min)":load if load is not None else self.t("Nicht verfügbar"),
                "RAM / Datenträger":f"{ram} % / {disk} %" if ram is not None else self.t("Nicht verfügbar"),
                "Betriebszeit":f"{uptime} s" if uptime is not None else self.t("Nicht verfügbar"),"Backend":self.details["version"],"Drucker (TCP)":self.t("Erreichbar" if printer else "Nicht erreichbar"),
                "Prüfungen / bestandene Tests":f"{exams} / {passed}","Gespeicherte Berichte":self.details["total"],
                "Streicheleinheiten":pets,
            }
            v.addWidget(self.columns([label(f"{self.t(key)}  ·  {value}") for key,value in cells.items()]))
        self.actions(v,[("Aktualisieren",lambda:self.call("system.info",callback=self.set_info),False),
                        ("Zurück",self.go_back,False)])

    def render_pet(self,v):
        from hdmi_personality import Wolf
        self.section(v,"Werkstattwolf","Ein kleiner Besuch in der Werkstatt")
        mascot=Wolf(lambda:self.call("personality.pet"),lambda:self.call("personality.treat"))
        mascot.setFixedSize(260,min(255,max(151,self.height()//3)))
        v.addWidget(mascot,alignment=Qt.AlignHCenter)
        p=self.state["personality"]
        self.pet_amount=label(self.t("Streicheleinheiten: {count}",count=p.get("pets") or 0))
        self.pet_response=label(self.t(p.get("pet_reply","Ein kleiner Werkstattwolf sagt hallo.")),role="muted")
        v.addWidget(self.pet_amount)
        v.addWidget(self.pet_response)
        v.addWidget(label(self.t("Fiktive Telemetrie: Werkstattlaune stabil."),role="muted"))
        self.actions(v,[("Streicheln",lambda:mascot.react("happy"),True),
                        ("Leckerli",lambda:mascot.react("treat"),False),
                        ("Awoo",lambda:mascot.react("awoo"),False),
                        ("Werkstatt-Meilensteine",lambda:self.route("achievements"),False),
                        ("Spassbelege",lambda:self.route("novelty"),False),
                        ("Zurück",lambda:self.route("work"),False)])
    def render_achievements(self,v):
        self.section(v,"Werkstatt-Meilensteine")
        p=self.state["personality"]
        progress=p.get("achievements",{})
        if progress:
            for key,name,goal in (("pets","Streicheleinheiten",10),("prints","Gedruckte Prüfbelege",10),
                                  ("exams","Dokumentierte Prüfungen",10),("switches","Sprachwechsel",5),
                                  ("seconds","Betriebsstunden",3600),("engineering","Engineering-Aufrufe",3),("treats","Leckerli",5)):
                total=progress.get(key,0)
                if key=="seconds":
                    total,goal=total//3600,goal//3600
                v.addWidget(label(("✓  " if total>=goal else "")+f"{self.t(name)}  ·  {total} / {goal}",role="muted"))

        self.actions(v,[("Zurück",self.go_back,False)])

    def render_novelty(self,v):
        self.section(v,"Spassbelege","Kein Prüfprotokoll oder Nachweis.")
        if self.state.get("novelty_note"):
            v.addWidget(label(self.t(self.state["novelty_note"]),role="muted"))
        for kind,title in ITEMS.items():
            v.addWidget(button(self.t(title),lambda kind=kind:self.open_novelty(kind)))
        self.actions(v,[("Zurück",self.go_back,False)])

    def open_novelty(self,kind):
        self.novelty_kind=kind
        self.route("novelty_preview")

    def render_novelty_preview(self,v):
        kind=self.novelty_kind
        self.section(v,ITEMS[kind],"Kein Prüfprotokoll oder Nachweis.")
        image=QLabel()
        image.setAlignment(Qt.AlignCenter)
        bitmap=QPixmap(str(preview_path(kind,self.state["language"])))
        image.setPixmap(bitmap.scaledToWidth(min(375,self.width()-65),Qt.SmoothTransformation))
        image.setAccessibleName(self.t("Spassbeleg-Vorschau"))
        v.addWidget(image)
        self.actions(v,[("Spassbeleg drucken",lambda:self.question("Spassbeleg drucken?",
            lambda:self.call("novelty.print",{"kind":kind,"confirmed":True})),True),
            ("Zurück",self.go_back,False)])
        if self.state.get("novelty_note"):
            v.addWidget(label(self.t(self.state["novelty_note"]),role="muted"))

    def resizeEvent(self,event):
        self.brand.setVisible(self.width()>=650)
        self.logo.setVisible(self.width()>=400)
        previous=getattr(self,"wide",None)
        self.wide=2 if self.width()>=760 else 1 if self.width()>=600 else 0
        if previous is not None and previous!=self.wide:
            QTimer.singleShot(0,self.render)
        super().resizeEvent(event)



class RotatedSurface(QGraphicsView):
    """Rotate the scene and let Qt inverse-map mouse/touch to the widget."""
    def __init__(self,surface,angle):
        scene=QGraphicsScene()
        super().__init__(scene)
        self.owned_scene=scene
        self.proxy=scene.addWidget(surface)
        self.angle=angle
        self.setTransform(QTransform().rotate(angle))
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.gesture=DragScroll(self,surface)

    def change_rotation(self,angle):
        self.angle=angle
        self.setTransform(QTransform().rotate(angle))
        self.fit_surface()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self.fit_surface()

    def fit_surface(self):
        w,h=self.viewport().width(),self.viewport().height()
        if self.angle in (90,270):
            w,h=h,w
        self.proxy.resize(w,h)
        self.setSceneRect(0,0,w,h)
        self.centerOn(w/2,h/2)

    def closeEvent(self,event):
        self.proxy.widget().close()
        super().closeEvent(event)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--socket",default=DEFAULT_SOCKET)
    p.add_argument("--window",action="store_true")
    p.add_argument("--screen",default="")
    p.add_argument("--size")
    p.add_argument("--touch-device",default=os.environ.get("FMI_HDMI_TOUCH_DEVICE",""))
    p.add_argument("--rotation",type=int,choices=(0,90,180,270),default=0)
    p.add_argument("--backlight",default=os.environ.get("FMI_HDMI_BACKLIGHT",""))
    a=p.parse_args()
    app=QApplication([sys.argv[0]])
    surface=Surface(a.socket)
    if a.backlight and a.backlight not in (".","..") and "/" not in a.backlight:
        surface.backlight=a.backlight
    window=RotatedSurface(surface,a.rotation)
    surface.rotation=Rotation(a.screen,window.change_rotation,a.rotation)
    if a.size:
        width,height=map(int,a.size.split("x",1))
        window.resize(width,height)
    if a.screen:
        screen=next((screen for screen in app.screens() if a.screen in screen.name()),None)
        if screen:
            window.setGeometry(screen.geometry())
            window.winId()
            window.windowHandle().setScreen(screen)
    window.show() if a.window else window.showFullScreen()
    surface.touch_manager=TouchManager(window,surface,a.screen,a.touch_device)
    try:
        return app.exec()
    finally:
        surface.touch_manager.detach()


if __name__=="__main__":
    raise SystemExit(main())
