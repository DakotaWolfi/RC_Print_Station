"""Native picker for appliance templates and the examiner directory."""
import sqlite3

from operator_store import Operators

PAGE_SIZE=6


class Picker:
    def __init__(self,ui):
        self.ui=ui
        self.store=Operators(ui.measurements.db)
        self.reset()

    def reset(self):
        self.mode=""
        self.offset=0
        self.selected=None
        self.edit=None
        self.include_inactive=False
        self.confirm=None
        self.note=""
        self.rows=[]

    def open(self,mode,selected=None):
        self.reset()
        self.mode=mode
        self.selected=selected

    def draw(self):
        if self.ui.settings.page!="picker":
            return
        ui=self.ui
        people=self.mode=="people"
        entries=self.store.examiners(include_inactive=self.include_inactive) if people else self.store.appliances(ui.language)
        self.offset=min(self.offset,max(0,(len(entries)-1)//PAGE_SIZE*PAGE_SIZE))
        self.rows=entries[self.offset:self.offset+PAGE_SIZE]
        ui.say("pTitle","Prüfperson auswählen" if people else "Gerät auswählen",52)
        chosen=next((row for row in entries if people and row["id"]==self.selected),None)
        if not people:
            detail=ui.tr("Zuletzt verwendet und Vorlagen")
        elif chosen:
            detail=ui.tr("Auswahl: {name}" if chosen["active"] else "Inaktiv: {name}",name=chosen["name"])
        else:
            detail=ui.tr("Prüfperson antippen oder neu erfassen")
        ui.text("pSelected",detail,64)
        for i in range(PAGE_SIZE):
            label=""
            if i<len(self.rows):
                row=self.rows[i]
                if people:
                    label=("> " if row["id"]==self.selected else "")+row["name"]
                    if not row["active"]:
                        label+=ui.tr("  (inaktiv)")
                else:
                    label=row[0]
            ui.text(f"pRow{i}",label,67)
        ui.say("pNote",self.note,94)
        ui.say("bToggle","Nur aktive" if self.include_inactive else "Auch inaktive",14)
        ui.say("bState","Bestätigen" if self.confirm is not None else
                "Aktivieren" if chosen and not chosen["active"] else "Deaktivieren",16)
        for name,flag in (("pPeople",people),("pChoose",chosen and chosen["active"]),
                          ("pEditOk",chosen),("pPrev",self.offset>0),
                          ("pNext",self.offset+PAGE_SIZE<len(entries))):
            ui.cmd(f"{name}.val={int(bool(flag))}")
        ui.cmd(f"pCount.val={len(self.rows)}")
        ui.cmd("click hLayout,0")

    def enter(self):
        if self.ui.settings.page=="picker":
            try:
                self.draw()
            except (sqlite3.Error,ValueError) as exc:
                self.ui.say("pNote",str(exc) if isinstance(exc,ValueError) else "Namensliste nicht verfügbar.",94)

    def handle(self,frame):
        action,_,payload=frame.partition(b"\x00")
        page=self.ui.settings.page
        ui=self.ui
        try:
            if page=="entry" and action==b"RC61:DRAFT":
                ticket,device=payload.decode("iso-8859-15").split("\x00")
                ui.text("tTicketView",ticket,34)
                ui.text("tDeviceView",device,66)
            elif page=="entry" and action==b"RC61:APPLIANCES":
                self.open("appliance")
            elif page=="guide" and action==b"RC61:PEOPLE" and ui.workflow.guide and ui.workflow.guide.step=="exam":
                self.open("people",ui.workflow.examiner_id)
            elif page=="keyboard" and action==b"RC61:NAME" and self.mode=="people" and self.edit is not None:
                self.selected=self.store.rename(payload.decode("iso-8859-15"),self.edit or None)
                self.edit=None
                self.note="Prüfperson gespeichert. Auswahl übernehmen."
            elif page=="picker" and self.mode:
                if action.startswith(b"RC61:ROW:"):
                    index=int(action[9:])
                    if not 0<=index<len(self.rows):
                        return
                    self.confirm=None
                    self.note=""
                    if self.mode=="people":
                        self.selected=self.rows[index]["id"]
                    else:
                        ui.text("entry.tDevice",self.rows[index][0],64)
                        ui.cmd("pRoute.val=2")
                        return
                elif action in (b"RC61:PREV",b"RC61:NEXT"):
                    self.offset=max(0,self.offset+(PAGE_SIZE if action.endswith(b"NEXT") else -PAGE_SIZE))
                elif self.mode=="people":
                    if action==b"RC61:TOGGLE":
                        self.include_inactive=not self.include_inactive
                        self.offset=0
                        self.confirm=None
                        self.note=""
                    elif action==b"RC61:USE" and self.selected is not None:
                        self.store.active_name(self.selected)
                        ui.workflow.examiner_id=self.selected
                        ui.cmd("pRoute.val=3")
                        return
                    elif action in (b"RC61:ADD",b"RC61:EDIT"):
                        chosen=next((row for row in self.store.examiners(include_inactive=True)
                                     if row["id"]==self.selected),None)
                        if action==b"RC61:EDIT" and chosen is None:
                            return
                        self.edit=chosen["id"] if action==b"RC61:EDIT" else 0
                        ui.text("picker.pEdit",chosen["name"] if self.edit else "",48)
                        ui.cmd("pRoute.val=1")
                        return
                    elif action==b"RC61:STATE" and self.selected is not None:
                        chosen=next((row for row in self.store.examiners(include_inactive=True)
                                     if row["id"]==self.selected),None)
                        if chosen is None:
                            return
                        if self.confirm==self.selected:
                            self.store.set_active(self.selected,not chosen["active"])
                            if chosen["active"] and ui.workflow.examiner_id==self.selected:
                                ui.workflow.examiner_id=None
                            self.confirm=None
                            self.note="Prüfperson deaktiviert." if chosen["active"] else "Prüfperson aktiviert."
                        else:
                            self.confirm=self.selected
                            self.note="Änderung mit «Bestätigen» übernehmen."
            self.enter()
        except (ValueError,sqlite3.Error) as exc:
            self.note=str(exc) if isinstance(exc,ValueError) else "Datenbank momentan nicht verfügbar."
            self.enter()
