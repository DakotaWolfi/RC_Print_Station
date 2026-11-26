"""HMI coordination for guided examination and fresh BENNING imports."""
import sqlite3

from benning_csv import outcome
from benning_guide import Guide, STEPS

ART=("lcd","class1","class2","iec","extension","store","recall","print","ports","key_i","key_ii","key_leak","key_voltage")
DISPLAY={"visual":"SICHTPRÜFUNG","kind":"SCHUTZKLASSE","class3":"SELV",
         "cable":"LEITUNGSTEST","running":"MESSUNG LÄUFT","warnings":"MELDUNG ABLESEN",
         "low":"Lo LOAD","high":"HIGH LOAD","table":"tAbLE","hot":"StOP / hot",
         "wrong":"PRÜFLAUF PRÜFEN","leak":"I LEAK BLINKT","unsaved":"FULL",
         "stop":"ABGEBROCHEN","special":"FACHVERFAHREN","exam":"SICHT UND FUNKTION"}


def fresh_slot(baseline,source,current):
    before=baseline.get(source)
    batch,records=current.get(source,(0,{}))
    if not before:
        return ("Erster Import. Slot manuell bestätigen.",None) if batch else ("",None)
    if batch<=before[0]:
        return "",None
    changed=[slot for slot,record in records.items() if before[1].get(slot)!=record]
    if before[1].keys()-records.keys() or len(changed)>1:
        return "Mehrere Änderungen oder Speicher-Reset. Slot manuell wählen.",None
    if not changed:
        return "Kein neuer Datensatz erkennbar. Vorhandenen Slot nur bewusst wählen.",None
    return "Neuer Datensatz empfangen. Slot, Datum und Ergebnis prüfen.",changed[0]


class WorkflowPanel:
    def __init__(self,ui):
        self.ui=ui
        self.tester=ui.tester
        self.store=ui.measurements
        self.reset()

    def reset(self):
        self.guide=None
        self.examiner_id=None
        self.baseline=None
        self.exam=None
        self.armed=False
        self.help=False
        self.import_view=None

    def start(self):
        self.reset()
        self.tester.start_draft()
        self.baseline=self.store.snapshot(("usb","rs232","file-csv","file-txt"))

    def enter(self):
        page=self.ui.settings.page
        if page=="guide":
            self.draw_guide()
        elif page=="importer":
            self.import_view=None
            self.poll()

    def draw_guide(self):
        if self.ui.settings.page!="guide":
            return
        ui=self.ui
        g=self.guide
        if g is None:
            ui.text("gTitle","Eingaben prüfen",52)
            ui.text("gBody","Zurück zur Eingabe. Angaben prüfen oder bei Host-Neustart neu beginnen.",230)
            ui.cmd("gCount.val=0")
            ui.cmd("gExam.val=0")
            ui.cmd("gBusy.val=0")
            return
        step=STEPS[g.step]
        ui.text("gTitle",step.title,52)
        ui.text("gProgress",f"Schritt {step.phase} von 7  ·  BENNING ST 725 CH",50)
        ui.text("gBody",step.help if self.help else g.instruction(),230)
        art="ports" if self.help and g.art in ("class1","class2","iec","extension") else g.art
        ui.cmd(f"gArt.val={ART.index(art)}")
        ui.cmd("click hArt,0")
        ui.text("gDisplay",DISPLAY.get(g.step,""),40)
        ui.cmd(f"vis gDisplay,{int(g.step in DISPLAY)}")
        ui.cmd(f"gExam.val={int(g.step=='exam')}")
        if g.step=="exam":
            try:
                examiner=ui.picker.store.active_name(self.examiner_id)
            except (ValueError,sqlite3.Error):
                self.examiner_id=None
                examiner=""
            ui.text("eName",examiner or "Keine Prüfperson gewählt",52)
        ui.text("gFunction","Funktion: "+g.functional,34)
        ui.text("gProceed","Zum Import" if g.stored else "Unvollständig speichern",30)
        choices=g.choices()
        grid=len(choices)>5
        for idx,(label,_) in enumerate(choices):
            ui.text(f"b{'Obs' if grid else 'Step'}{idx}",label,40)
        ui.cmd(f"gCount.val={len(choices)}")
        ui.cmd("click hLayout,0")
        ui.cmd("gBusy.val=0")

    def prepare(self,frame,guided):
        fields=frame.decode("iso-8859-15").split("\x00")
        self.tester.pending=self.tester.selected=None
        self.tester.review(fields)
        # Entry draft is shared with v0.5. Remove even a valid old selection here.
        self.tester.selected=None
        self.tester.note=""
        self.tester.autofill=False  # Explicit review permits selecting another row.
        if guided:
            self.guide=Guide()
            self.exam=None
            people=self.ui.picker.store.examiners()
            self.examiner_id=people[0]["id"] if people and people[0]["last_used"] else None
        elif self.baseline is None:
            self.baseline=self.store.snapshot(("usb","rs232","file-csv","file-txt"))

    def begin_import(self):
        self.armed=True
        self.import_view=None
        self.tester.selected=None
        self.help=False

    def poll(self):
        page=self.ui.settings.page
        if page!="importer":
            return
        ui=self.ui
        batch=self.tester.batch
        receiver=self.tester.receiver.status
        view=(receiver,batch and batch["id"],self.armed,self.help)
        if self.import_view==view or (self.import_view is not None and not self.armed):
            return
        self.import_view=view
        source=receiver.source or self.tester.mode
        ui.text("iStatus",self.tester.status_line(),105)
        ui.cmd(f"iAvailable.val={int(bool(self.armed and self.tester.slots))}")
        if source=="rs232":
            art="print"
            body="Beendeten Slot am BENNING per Ordner (14) aufrufen. Slot prüfen und Druckertaste (15) drücken."
        elif self.tester.mode=="file":
            art="lcd"
            body="Datei in der lokalen Verwaltung importieren. Der Tester sendet in diesem Modus keine Daten."
        else:
            art="recall"
            body="Ergebnis zuerst per Diskette (13) speichern. Alle Leitungen und Prüflinge vom BENNING entfernen. USB verbinden und Ordner (14) ca. 5 s halten."
        if self.help:
            body+=" Alte Daten nur über «Vorhandene Messung» wählen."
        ui.text("iBody",body,220)
        ui.cmd(f"iArt.val={ART.index(art)}")
        ui.cmd("click hArt,0")
        message="Warte auf eine neue Messung."
        slot=None
        if not self.armed or self.baseline is None:
            message="Zurück zur Eingabe und Import erneut starten."
        elif receiver.state in ("receiving","error","interrupted"):
            message="Empfang läuft ..." if receiver.state=="receiving" else "Empfang prüfen und erneut übertragen."
        elif batch:
            try:
                note,slot=fresh_slot(self.baseline,batch["source"],self.store.snapshot((batch["source"],)))
                message=note or message
            except sqlite3.Error:
                self.import_view=None
                message="BENNING-Datenbank momentan nicht verfügbar."
        if slot:
            selected=next((row for row in self.tester.slots if row["slot"]==slot and
                           row["batch"]==batch["id"]),None)
            if selected:
                self.choose_review(selected,message)
                ui.cmd("iAdvance.val=1")
        ui.text("iMessage",message,105)

    def choose_review(self,selected=None,note="Vorhandene Messung bewusst auswählen."):
        self.tester.selected=selected
        self.tester.note=note
        if selected:
            self.tester.offset=self.tester.slots.index(selected)//4*4
        self.armed=False

    def submit_exam(self,payload):
        if not self.guide or self.guide.step!="exam" or not self.tester.pending:
            raise ValueError("Prüfung zuerst dokumentieren.")
        remarks=payload.decode("iso-8859-15")
        if len(remarks)>64 or any(not c.isprintable() for c in remarks):
            raise ValueError("Bemerkung ungültig.")
        examiner=self.ui.picker.store.active_name(self.examiner_id)
        self.exam=self.guide.examination(examiner,remarks)
        if self.guide.stored and not self.guide.blocked:
            self.begin_import()
            self.ui.cmd("gAdvance.val=1")
        else:
            ident,report=self.store.create_incomplete(*self.tester.pending,self.exam,examiner_id=self.examiner_id)
            self.tester.pending=None
            self.ui.load_report(ident,report)
            self.ui.cmd("gAdvance.val=2")

    def save_selection(self,selected):
        if self.exam:
            record=selected["original"]
            if self.exam["observed"]!=outcome(record["verdict"]):
                raise ValueError("Testergebnis weicht von der bestätigten Anzeige ab. Auswahl prüfen.")
            actual=(record.get("protection_class") or "").upper()
            expected={"I":{"KLASSE I"},"II":{"KLASSE II"},"III":{"KLASSE II","KLASSE III"}}
            classes=expected.get(self.exam["procedure"],set())
            if classes and actual and actual not in classes:
                raise ValueError("Schutzklasse passt nicht zur geführten Prüfung. Slot prüfen.")
        return self.store.create_report(*self.tester.pending,selected,require_current=True,examination=self.exam,examiner_id=self.examiner_id if self.exam else None)

    def handle(self,frame):
        command,_,payload=frame.partition(b"\x00")
        page=self.ui.settings.page
        ui=self.ui
        try:
            if page=="home" and command==b"RC6:NEW":
                self.start()
            elif page=="entry" and command in (b"RC6:GUIDE",b"RC6:IMPORT",b"RC6:EXISTING"):
                if self.baseline is None:
                    raise ValueError("Neues Protokoll starten, um den Speicherstand zu erfassen.")
                if self.tester.mode=="simulation":
                    raise ValueError("Simulation ist aktiv.")
                guided=command==b"RC6:GUIDE"
                if not guided:
                    self.guide=self.exam=None
                self.prepare(payload,guided)
                if command==b"RC6:IMPORT":
                    self.begin_import()
                    ui.cmd("entry.route.val=2")
                elif guided:
                    ui.cmd("entry.route.val=1")
                else:
                    # Preserve a manually typed existing slot if it resolves.
                    self.tester.review(payload.decode("iso-8859-15").split("\x00"))
                    self.tester.autofill=False
                    self.tester.note="Vorhandenes Testergebnis: Slot und Datum bewusst bestätigen."
                    ui.cmd("entry.route.val=3")
            elif page=="guide" and command==b"RC6:HELP":
                self.help=not self.help
            elif page=="guide" and command==b"RC6:BACK":
                self.help=False
                if self.guide is None or self.guide.step=="visual":
                    ui.cmd("gAdvance.val=3")
                elif not self.guide.back():
                    self.ui.text("gError","Abgebrochenen Lauf dokumentieren oder Vorgang beenden.",82)
            elif page=="guide" and command==b"RC6:CANCEL":
                self.start()
                self.tester.pending=self.tester.selected=None
                ui.cmd("gAdvance.val=3")
            elif page=="guide" and command.startswith(b"RC6:STEP:") and self.guide:
                self.help=False
                ui.text("gError","",82)
                self.guide.choose(int(command[9:]))
            elif page=="guide" and command==b"RC6:FUNCTION" and self.guide and self.guide.step=="exam":
                options=("Offen","Ohne Befund","Mangel","Nicht geprüft")
                self.guide.functional=options[(options.index(self.guide.functional)+1)%len(options)]
            elif page=="guide" and command==b"RC6:EXAM":
                self.submit_exam(payload)
            elif page=="importer" and command==b"RC6:MANUAL" and self.armed and self.tester.slots:
                self.choose_review()
                ui.cmd("iAdvance.val=1")
            elif page=="importer" and command==b"RC6:HELP":
                self.help=not self.help
                self.import_view=None
                self.poll()
            elif page=="importer" and command==b"RC6:BACK":
                self.armed=False
                self.help=False
                ui.cmd("iAdvance.val=2")
            else:
                return
        except (sqlite3.Error,ValueError) as exc:
            message=str(exc) if isinstance(exc,ValueError) else "BENNING-Datenbank momentan nicht verfügbar."
            if page=="home":
                ui.text("home.tHint",message,64)
            elif page=="entry":
                ui.text("entry.tStatus",message,100)
                ui.cmd("entry.busy.val=0")
            elif page=="guide":
                ui.text("gError",message,82)
            elif page=="importer":
                ui.text("iMessage",message,105)
        self.draw_guide()
