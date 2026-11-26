"""Operator selection and confirmation for the native BENNING pages."""
from datetime import datetime
import sqlite3
import time
from zoneinfo import ZoneInfo

from benning_csv import outcome, slot_value
from benning_store import PHASES
from benning_output import RESULTS, date_format, tester_date, verdict_text
from i18n import error_text

MODE_NAME={"auto":"Auto","usb":"USB CSV","rs232":"RS232 (Test)","file":"Datei","simulation":"Simulation"}
SOURCES_BY_MODE={"auto":("usb","rs232"),"usb":("usb",),"rs232":("rs232",),
                 "file":("file-csv","file-txt"),"simulation":()}
STATUS={"searching":"Suche Tester / USB","disconnected":"Tester nicht verbunden",
        "file":"Dateiimport / kein serieller Empfang","simulation":"Simulation",
        "receiving":"Empfange","imported":"Import gespeichert"}


class TesterPanel:
    def __init__(self,ui,store,receiver):
        self.ui=ui
        self.store=store
        self.receiver=receiver
        self.batch=None
        self.slots=[]
        self.last_check=float("-inf")
        self.last_view=None
        self.last_view_batch=None
        self.start_batch=0
        self.offset=0
        self.selected=None
        self.pending=None
        self.autofill=True
        self.note=""

    @property
    def mode(self):
        return self.receiver.mode

    def refresh(self,force=False):
        status=self.receiver.status
        now=time.monotonic()
        if force or now-self.last_check>=2 or status.batch!=self.last_view_batch:
            sources=SOURCES_BY_MODE[self.mode]
            if self.mode=="auto" and status.source:
                sources=(status.source,)
            self.last_check=now
            self.last_view_batch=status.batch
            batch=self.store.latest(sources) if sources else None
            if batch!=self.batch:
                had_batch=self.batch is not None
                self.batch=batch
                self.slots=self.store.slots(batch["source"]) if batch else []
                if self.selected and not any(self.key(row)==self.key(self.selected) for row in self.slots):
                    self.selected=None
                    self.note="Import geändert. Speicherplatz erneut auswählen."
                self.offset=0
                if not had_batch and self.pending and self.autofill:
                    self.selected=self.selected_default()
                    if self.selected:
                        self.offset=self.slots.index(self.selected)//4*4
            return True
        return False

    @staticmethod
    def key(row):
        return row["source"],row["batch"],row["record_id"]

    def start_draft(self):
        self.refresh(force=True)
        self.start_batch=self.batch["id"] if self.batch else 0
        self.selected=self.pending=None
        self.autofill=True
        self.note=""
        self.offset=0
        if self.mode!="simulation":
            self.update_entry()

    def status_line(self):
        state=self.receiver.status
        t=self.ui.tr
        label=t(MODE_NAME[state.source or self.mode])
        if state.detail:
            return f"{label}: {error_text(self.ui.language,state.detail)}"
        if state.state=="receiving":
            return t("{mode}: Empfange {count} Bytes",mode=label,count=state.received)
        if state.state in ("waiting","imported"):
            trigger="PRINT" if state.source=="rs232" else "RECALL"
            return t("{mode}: verbunden / wartet auf {action}",mode=label,action=trigger)
        return f"{label}: "+t(STATUS.get(state.state,"Kommunikationsfehler"))

    def freshness(self,row):
        if not row:
            return "RECALL / PRINT auslösen oder Datei importieren."
        if not self.batch or row["batch"]!=self.batch["id"]:
            return "Älterer Cache. Datum und Slot prüfen."
        if self.batch["id"]<=self.start_batch:
            return "Vor dieser Eingabe importiert. Datum und Slot prüfen."
        if self.mode=="file":
            return "Dateiimport. Datum und Slot bestätigen."
        if row["source"]=="rs232":
            return "Druckbericht. Datum, Slot und Prüfobjekt bestätigen."
        reason=self.batch["reason"]
        if reason=="single-change" and row["slot"]==self.batch["newest"]:
            return "Ein Slot seit dem letzten Import geändert."
        if reason=="unchanged":
            return "Keine Änderung erkannt. Datum und Slot prüfen."
        return "Reihenfolge unklar. Datum und Slot ausdrücklich bestätigen."

    def selected_default(self):
        if self.batch:
            return next((r for r in self.slots if r["slot"]==self.batch["newest"]),None)
        return None

    def update_entry(self):
        if self.autofill and self.batch:
            self.ui.text("entry.tSlot",self.batch["newest"],3)
        elif self.autofill:
            self.ui.text("entry.tSlot","",3)
        self.ui.text("entry.tTester",self.status_line(),92)

    def enter(self):
        self.last_view=None
        self.last_check=float("-inf")
        self.poll()
        if self.mode=="simulation" and self.ui.settings.page=="entry":
            self.update_entry()

    def draw(self):
        if self.ui.settings.page!="tester":
            return
        t=self.ui.text
        c=self.ui.cmd
        t("mLink",self.status_line(),92)
        language=self.ui.language
        stamp=self.ui.tr("Noch kein Import")
        if self.batch:
            ts=datetime.fromisoformat(self.batch["imported"]).astimezone(ZoneInfo("Europe/Zurich"))
            timestamp=ts.strftime(date_format(language)+" %H:%M")
            stamp=self.ui.tr("{mode} importiert / {count} Slots · {stamp}",
                             mode=self.batch["records"],count=len(self.slots),stamp=timestamp)
        t("mImport",stamp,52)
        page=self.slots[self.offset:self.offset+4]
        for index in range(4):
            value="-"
            if index<len(page):
                item=page[index]
                r=item["original"]
                label=self.ui.tr(RESULTS[outcome(r["verdict"]) or "unknown"][0])
                value=f'{item["slot"]}   {tester_date(r,language)}   {label}'
            t(f"mRow{index}",value,42)
        c(f"mCount.val={len(page)}")
        c(f"mPrev.val={int(self.offset>0)}")
        c(f"mNext.val={int(self.offset+4<len(self.slots))}")
        if self.selected:
            r=self.selected["original"]
            selection=f'{self.selected["slot"]} · {tester_date(r,language)} · {verdict_text(r["verdict"],language)}'
        else:
            selection=self.ui.tr("Keine Messung ausgewählt")
        t("mSelected",selection,55)
        t("mNote",error_text(language,self.note or self.freshness(self.selected)),100)
        c(f'mReady.val={int(self.selected is not None and self.pending is not None and self.receiver.status.state!="receiving")}')

    def poll(self):
        if self.mode=="simulation":
            return
        try:
            self.refresh()
            state=(self.receiver.status,self.batch)
            if state!=self.last_view:
                self.last_view=state
                if self.ui.settings.page=="entry":
                    self.update_entry()
                elif self.ui.settings.page=="tester":
                    self.draw()
        except sqlite3.Error:
            message="BENNING-Datenbank gerade nicht verfügbar."
            if self.ui.settings.page=="tester":
                self.ui.say("mNote",message,86)
                self.ui.cmd("mReady.val=0")
            elif self.ui.settings.page=="entry":
                self.ui.say("entry.tTester",message,92)

    def review(self,fields):
        if len(fields)!=5 or fields[3] not in ("0","1","2") or fields[4] not in ("0","1"):
            raise ValueError("Ungültige Prüfart oder Auswahl.")
        ticket,device,slot,phase,auto=fields
        if not ticket.strip() or not device.strip():
            raise ValueError("Prüfnummer und Gerätebeschreibung eingeben.")
        self.pending=(ticket,device,PHASES[int(phase)])
        self.note=""
        self.autofill=auto=="1"
        self.refresh(force=True)
        if self.autofill:
            self.selected=self.selected_default()
        elif slot:
            slot=slot_value(slot)
            self.selected=next((r for r in self.slots if r["slot"]==slot),None)
            if not self.selected:
                self.note="Eingegebener Slot fehlt. Bitte aus der Liste auswählen."
        else:
            self.selected=None
            self.note="Bitte einen Speicherplatz auswählen."
        if self.selected:
            index=self.slots.index(self.selected)
            self.offset=index//4*4

    def handle(self,frame):
        action,_,payload=frame.partition(b"\x00")
        page=self.ui.settings.page
        try:
            if action==b"RC5:NEW" and page=="home":
                self.start_draft()
            elif action in (b"RC5:AUTOON",b"RC5:AUTOOFF") and page=="entry":
                self.autofill=action==b"RC5:AUTOON"
                self.update_entry()
            elif action==b"RC5:REVIEW" and page=="entry" and self.mode!="simulation":
                self.pending=self.selected=None
                self.review(payload.decode("iso-8859-15").split("\x00"))
            elif action==b"RC5:BROWSE" and page=="entry":
                self.pending=None
                self.refresh(force=True)
                self.selected=self.selected_default()
                self.note="Messung ansehen. Protokoll über Eingabe erstellen."
            elif page=="tester" and action in (b"RC5:PREV",b"RC5:NEXT"):
                delta=4 if action.endswith(b"NEXT") else -4
                self.offset=max(0,min(self.offset+delta,max(0,(len(self.slots)-1)//4*4)))
            elif page=="tester" and action in (b"RC5:SEL:0",b"RC5:SEL:1",b"RC5:SEL:2",b"RC5:SEL:3"):
                index=self.offset+int(action[-1:])
                if self.pending and self.autofill:
                    self.note="Für eine andere Messung automatische Auswahl auf der Eingabeseite ausschalten."
                elif index<len(self.slots):
                    self.selected=self.slots[index]
                    self.note="Slot übernommen. Über Eingabe fortfahren." if self.pending is None else ""
                    if not self.autofill:
                        self.ui.text("entry.tSlot",self.selected["slot"],3)
            elif page=="tester" and action==b"RC5:USE" and self.pending and self.selected:
                chosen=self.key(self.selected)
                self.refresh(force=True)
                if not self.selected or self.key(self.selected)!=chosen or self.receiver.status.state=="receiving":
                    self.note="Import läuft oder Auswahl geändert. Bitte erneut auswählen."
                else:
                    ident,report=self.ui.workflow.save_selection(self.selected)
                    self.pending=None
                    self.ui.finish_draft(ident,report)
            else:
                return
        except (ValueError,sqlite3.Error) as exc:
            self.note=str(exc) if isinstance(exc,ValueError) else "BENNING-Datenbank gerade nicht verfügbar."
            if page=="entry":
                self.pending=self.selected=None
                self.ui.text("entry.tStatus",error_text(self.ui.language,self.note),80)
        self.draw()
