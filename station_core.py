"""Authoritative examination state. No display, UART or GUI dependencies."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import asdict
import json
import logging
from pathlib import Path
import socket
import sqlite3
import subprocess
from threading import RLock
from time import monotonic
from uuid import uuid4

from benning_csv import slot_value
from benning_guide import Guide, STEPS
from benning_output import measurement_summary, report_checks, result_kind, selected_fields, visible_measurements
from benning_receiver import Receiver
from benning_store import Measurements, PHASES, SOURCES
from examination_rules import fresh_slot, validate_selection
from operator_store import Operators
from novelty import ITEMS, render as novelty_receipt
from personality import PET_REPLIES, report_counts, system_metrics
import random
from report_web import publish
from slogan_store import SloganStore
from station import receipt, send, simulate
import station_config as config
from station_network import NetworkError, NetworkManager
from web_access import read_status

LOG = logging.getLogger(__name__)
VERSION = "0.8.3"
FORMAT = 1
STATES = ("entry","guide","waiting","review","report")
MODES = {"auto":("usb","rs232"),"usb":("usb",),"rs232":("rs232",),
         "file":("file-csv","file-txt"),"simulation":()}
ACTIVE_STAGES = ("guide","waiting","review")
OWNER_LEASE = 20
OWNER_OPS = frozenset(("draft.edit","draft.discard","language.report","person.pick","exam.submit",
                       "exam.function","guide.choose","guide.back","guide.cancel","review.manual",
                       "review.select","review.back","review.confirm","import.reset"))
CYCLE = ("Offen","Ohne Befund","Mangel","Nicht geprüft")
WAIT_BODY = {
    "rs232":("print","Beendeten Slot am BENNING per Ordner (14) aufrufen. Slot prüfen und Druckertaste (15) drücken."),
    "file":("lcd","Datei in der lokalen Verwaltung importieren. Der Tester sendet in diesem Modus keine Daten."),
    "usb":("recall","Ergebnis zuerst per Diskette (13) speichern. Alle Leitungen und Prüflinge vom BENNING entfernen. USB verbinden und Ordner (14) ca. 5 s halten."),
}


def limited(value, maximum, allow_empty=True):
    if (not isinstance(value,str) or len(value)>maximum or
            (not allow_empty and not value.strip()) or any(not c.isprintable() for c in value)):
        raise ValueError("Ungültige Eingabe.")
    return value


class StationCore:
    def __init__(self, db, *, receiver=None, config_path=None, cache=None, host=config.PRINTER_HOST,
                 printer_port=config.PRINTER_PORT, sender=send, publisher=publish,
                 base_url="", auto_port=None, network=None, allow_power=False, power=None, hotspot_fallback=False, web_status=None):
        self.db=Path(db)
        self.store=Measurements(db)
        with closing(self.store.db()):
            pass
        self.operators=Operators(self.store.db)
        self.receiver=receiver or Receiver(self.store)
        self.config_path=config_path
        self.config=config.load(config_path)
        self.host,self.printer_port,self.sender=host,printer_port,sender
        self.publisher,self.fixed_url,self.base_url,self.auto_port=publisher,base_url,base_url,auto_port
        self.downloads_online=True
        self.network=network or NetworkManager()
        self.allow_power=allow_power
        self.hotspot_fallback=hotspot_fallback
        self.hotspot_due=monotonic()+90
        self.power=power or self.system_power
        self.lock=RLock()
        self.sequence=0
        self.epoch=uuid4().hex
        self.completed=OrderedDict()
        self.editors={}
        self.owner=None
        self.draft=None
        self.guide=None
        self.baseline={}
        self.examination=None
        self.selected=None
        self.wait_note=""
        self.batch=None
        self.slots=[]
        self.last_import_check=0
        self.next_config_check=0
        self.suggested_seen=None
        self.report_id=None
        self.report=None
        self.links={}
        self.jobs={}
        self.last_print={}
        self.print_note=""
        self.novelty_note=""
        self.network_note=""
        self.ssid=self.ip=""
        self.access_points={}
        self.last_network_check=0
        self.probe_note=""
        self.wifi_generation=0
        self.milestone_until=0
        self.power_note=""
        self.pools={name:ThreadPoolExecutor(max_workers=1,thread_name_prefix=name)
                    for name in ("printer","network","power","personality")}
        self.cache=cache or SloganStore()
        # Kept for the frozen protocol 71 adapter. Its slogan component is blank.
        self.slogan=("","")
        self.web_status=web_status
        self.web_connection={}
        self.draft_checkpoint=None
        self.recovery_note=""
        self.pet_reply="Ein kleiner Werkstattwolf sagt hallo."
        self.pet_count=None
        self.pet_pending=0
        self.engineering={}
        self.metric_generation=0
        self.next_metrics=0
        self.milestone=0
        self.maintenance_dirty=True
        self.achievement_stats={}
        self.achievements_pending={}
        self.last_operating_sample=monotonic()
        self.next_achievement_sample=0
        self.restore_checkpoint()

    def restore_checkpoint(self):
        with closing(self.store.db()) as db,db:
            db.execute("CREATE TABLE IF NOT EXISTS fmi_resume (id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL)")
            row=db.execute("SELECT data FROM fmi_resume WHERE id=1").fetchone()
        if not row:
            return
        try:
            saved=json.loads(row["data"])
            draft=saved["draft"]
            if not draft:
                return
            if draft["stage"]=="report":
                self.report_id=saved["report"]
                self.report=self.get_report(self.report_id)
            else:
                draft=dict(draft,id=uuid4().hex,version=0,stage="entry")
                self.baseline=self.store.snapshot(tuple(SOURCES))
                self.recovery_note="Entwurf nach Neustart wiederhergestellt. Prüfaufbau erneut kontrollieren und Prüfung neu beginnen."
            self.draft=draft
        except (ValueError,KeyError,TypeError):
            LOG.warning("Stored draft checkpoint could not be restored")

    def checkpoint(self):
        value=json.dumps({"draft":self.draft,"report":self.report_id},ensure_ascii=False)
        if value==self.draft_checkpoint:
            return
        with closing(self.store.db()) as db,db:
            db.execute("INSERT INTO fmi_resume VALUES(1,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",(value,))
        self.draft_checkpoint=value

    @staticmethod
    def system_power(action):
        subprocess.run(["loginctl","--no-ask-password",{"halt":"poweroff","reboot":"reboot"}[action]],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=8)

    @property
    def language(self):
        return self.config["language"]

    @property
    def phase(self):
        return self.draft["stage"] if self.draft else None

    def endpoint(self):
        return self.config.get("printer_host",self.host),self.config.get("printer_port",self.printer_port)

    def job(self, pool, action, function, *args):
        if pool in self.jobs:
            raise ValueError("Eine Aktion läuft bereits.")
        self.jobs[pool]=(action,self.pools[pool].submit(function,*args))

    def start(self):
        self.receiver.start()

    def close(self):
        self.receiver.close()
        for name,pool in self.pools.items():
            pool.shutdown(wait=name in ("printer","personality"),cancel_futures=True)

    def refresh_import(self):
        state=self.receiver.status
        sources=MODES[self.receiver.mode]
        if self.receiver.mode=="auto" and state.source in sources:
            sources=(state.source,)
        batch=self.store.latest(sources) if sources else None
        if batch!=self.batch:
            self.batch=batch
            self.slots=self.store.slots(batch["source"]) if batch else []
            if self.selected and not any(self.identity(r)==self.identity(self.selected) for r in self.slots):
                self.selected=None
                if self.phase=="review":
                    self.wait_note="Import geändert. Speicherplatz erneut auswählen."
                    self.advance("waiting")
            self.sequence+=1
        if self.phase=="waiting" and self.batch and state.state not in ("receiving","error","interrupted","reset-pending"):
            batch=self.batch
            if batch["id"]==self.suggested_seen:
                return
            self.suggested_seen=batch["id"]
            note,slot=fresh_slot(self.baseline,batch["source"],self.store.snapshot((batch["source"],)))
            self.wait_note=note
            if slot and batch["reason"]!="baseline":
                self.selected=next((r for r in self.slots if r["slot"]==slot and r["batch"]==batch["id"]),None)
                if self.selected:
                    self.advance("review")

    @staticmethod
    def identity(row):
        return (row["batch"],row["record_id"])

    def touch(self):
        self.sequence+=1
        if self.draft:
            self.draft["version"]+=1

    def advance(self,stage):
        self.draft["stage"]=stage
        self.touch()

    def require_draft(self, args, stages, *, version=False):
        if not self.draft or args.get("draft")!=self.draft["id"]:
            raise ValueError("Der Entwurf ist nicht mehr aktiv.")
        if self.phase not in stages:
            raise ValueError("Die Prüfung ist bereits in einer anderen Phase.")
        if version and (type(args.get("version")) is not int or args["version"]!=self.draft["version"]):
            raise ValueError("Der Entwurf hat sich geändert.")

    def begin(self, args):
        if self.draft and self.phase!="report":
            raise ValueError("Zuerst den aktiven Entwurf fortsetzen oder verwerfen.")
        mode=args.get("mode")
        if mode not in ("guided","direct"):
            raise ValueError("Ungültige Eingabe.")
        self.recovery_note=""
        self.baseline=self.store.snapshot(tuple(SOURCES))
        self.draft=dict(id=uuid4().hex,version=0,stage="entry",mode=mode,
                        ticket="",device="",phase=0,slot="",report_language=None,
                        examiner=None,remarks="",autofill=True)
        self.selected=self.examination=self.guide=None
        self.wait_note=""
        self.touch()

    def edit(self,args):
        self.require_draft(args,("entry","guide"))
        changes=args.get("changes")
        old=args.get("previous")
        if not isinstance(changes,dict) or not isinstance(old,dict) or set(changes)!=set(old):
            raise ValueError("Ungültige Eingabe.")
        clean={}
        for key,value in changes.items():
            if self.draft.get(key)!=old[key]:
                raise ValueError("Der Entwurf hat sich geändert.")
            if key in ("ticket","device","remarks"):
                if (key=="remarks")!=(self.phase=="guide"):
                    raise ValueError("Ungültige Eingabe.")
                value=limited(value,32 if key=="ticket" else 64)
            elif key=="phase" and self.phase=="entry":
                if type(value) is not int or not 0<=value<len(PHASES):
                    raise ValueError("Ungültige Prüfart.")
            elif key=="slot" and self.phase=="entry":
                value=slot_value(value) if value else ""
            elif key=="autofill" and self.phase=="entry" and type(value) is bool:
                pass
            else:
                raise ValueError("Ungültige Eingabe.")
            clean[key]=value
        if clean:
            self.draft.update(clean)
            self.touch()

    def fields(self):
        draft=self.draft
        return Measurements.repair_fields(draft["ticket"],draft["device"],PHASES[draft["phase"]])

    def start_examination(self,args,command):
        self.require_draft(args,("entry",),version=True)
        ticket,device,_=self.fields()
        self.recovery_note=""
        if self.receiver.mode=="simulation":
            if command=="review.find":
                raise ValueError("Simulation ist aktiv.")
            report=simulate(ticket,device,language=self.report_language())
            ident=self.store_report(report)
            self.finish(ident,report)
            return
        if command=="exam.start" and self.draft["mode"]=="guided":
            self.guide=Guide()
            people=self.operators.examiners()
            if self.draft["examiner"] is None:
                self.draft["examiner"]=people[0]["id"] if people and people[0]["last_used"] else None
            self.advance("guide")
        elif command=="review.find":
            self.refresh_import()
            slot=self.draft["slot"] or (self.batch["newest"] if self.batch and self.draft["autofill"] else "")
            self.selected=next((row for row in self.slots if row["slot"]==slot),None)
            self.wait_note="Vorhandenes Testergebnis: Slot und Datum bewusst bestätigen."
            self.advance("review")
        else:
            self.await_import()

    def await_import(self):
        self.suggested_seen=None
        self.selected=None
        self.wait_note=""
        self.advance("waiting")
        self.refresh_import()

    def report_language(self):
        return self.draft["report_language"] or self.language

    def guide_submit(self,args):
        self.require_draft(args,("guide",),version=True)
        if self.guide.step!="exam":
            raise ValueError("Prüfung zuerst dokumentieren.")
        examiner=self.operators.active_name(self.draft["examiner"])
        self.examination=self.guide.examination(examiner,self.draft["remarks"])
        if self.guide.stored and not self.guide.blocked:
            self.await_import()
        else:
            ident,report=self.store.create_incomplete(*self.fields(),self.examination,
                         examiner_id=self.draft["examiner"],language=self.report_language())
            self.finish(ident,report)

    def measurement_origin(self,row):
        prior=self.baseline.get(row["source"])
        if not prior:
            return "operator-selected"
        if row["batch"]<=prior[0]:
            return "existing"
        return "identical" if prior[1].get(row["slot"])==row["record_id"] else "changed"

    def save_selected(self,args):
        self.require_draft(args,("review",),version=True)
        self.refresh_import()
        if (not self.selected or args.get("record")!=list(self.identity(self.selected)) or
                self.receiver.status.state=="receiving"):
            raise ValueError("Import läuft oder Auswahl geändert. Bitte erneut auswählen.")
        validate_selection(self.examination,self.selected["original"])
        origin=self.measurement_origin(self.selected)
        if origin=="identical" and args.get("same_reading_confirmed") is not True:
            raise ValueError("Identische Messung ausdrücklich als neue Prüfung bestätigen.")
        examiner_id=self.draft["examiner"]
        examination=self.examination
        if examination is None and examiner_id is not None:
            examination={"examiner":self.operators.active_name(examiner_id)}
        ident,report=self.store.create_report(*self.fields(),self.selected,require_current=True,
                    examination=examination,examiner_id=examiner_id,language=self.report_language(),
                    measurement_source=origin)
        self.finish(ident,report)

    def store_report(self, report):
        with closing(self.store.db()) as db, db:
            return db.execute("INSERT INTO reports(data) VALUES(?)",(json.dumps(report),)).lastrowid

    def finish(self,ident,report):
        self.report_id,self.report=ident,report
        self.guide=self.examination=None
        self.selected=None
        self.maintenance_dirty=True
        self.advance("report")

    def get_report(self,ident):
        if type(ident) is not int or ident<1:
            raise ValueError("Ungültige Eingabe.")
        with closing(self.store.db()) as db:
            row=db.execute("SELECT data FROM reports WHERE id=?",(ident,)).fetchone()
        if not row:
            raise ValueError("Bericht nicht gefunden.")
        report=json.loads(row["data"])
        if not isinstance(report,dict) or report.get("source") not in ("SIMULATOR","BENNING","EXAMINATION"):
            raise ValueError("Ungültiger gespeicherter Bericht.")
        return report

    def history(self):
        with closing(self.store.db()) as db:
            rows=db.execute("""SELECT id,
                json_extract(data,'$.ticket') ticket,json_extract(data,'$.device') device,
                json_extract(data,'$.created') created,json_extract(data,'$.source') source
                FROM reports WHERE json_valid(data) ORDER BY id DESC LIMIT 80""")
            return [dict(row) for row in rows]

    def queue_print(self, ident, confirmed, *, test=False):
        if confirmed is not True:
            raise ValueError("Bitte zuerst bestätigen.")
        if "printer" in self.jobs:
            raise ValueError("Ein Druckauftrag läuft bereits.")
        now=monotonic()
        self.last_print={k:v for k,v in self.last_print.items() if now-v<4}
        key="test" if test else ident
        if key in self.last_print:
            raise ValueError("Doppelter Druckauftrag unterdrückt.")
        report=simulate("DRUCKTEST","Epson / ESC-POS Verbindungstest",language=self.language) if test else self.get_report(ident)
        endpoint,settings=self.endpoint(),dict(self.config)
        kind="test" if test else "print-simulation" if report["source"]=="SIMULATOR" else "print"
        self.job("printer",kind,lambda: self.sender(*endpoint,receipt(report,settings)))
        self.last_print[key]=now
        self.print_note="Druckdaten werden gesendet ..."

    def net_action(self,name,args):
        if "network" in self.jobs:
            raise ValueError("WLAN-Aktion läuft bereits.")
        if name=="wifi.scan":
            self.job("network","scan",self.network.scan)
        elif name=="wifi.connect":
            net=self.access_points.get(args.get("network"))
            if not net:
                raise ValueError("WLAN bitte erneut auswählen.")
            self.job("network","connect",self.network.connect,net,limited(args.get("password",""),64))
        elif args.get("confirmed") is not True:
            raise ValueError("Bitte zuerst bestätigen.")
        elif name=="wifi.hotspot":
            self.job("network","hotspot",self.network.hotspot)
        else:
            self.hotspot_fallback=False
            self.job("network","status",self.network.stop_hotspot)
        self.network_note="Bitte warten ..."

    def report_link(self,ident):
        if not self.base_url:
            raise ValueError("PDF-Link nicht verfügbar. Bitte erneut öffnen.")
        key=(ident,self.base_url)
        if key not in self.links:
            if len(self.links)>=32:
                self.links.pop(next(iter(self.links)))
            self.links[key]=self.publisher(self.db,dict(self.get_report(ident),_download_id=ident),self.base_url)
        return self.links[key]

    def person(self,name,args):
        if name=="person.pick":
            self.require_draft(args,("entry","guide"),version=True)
            ident=args.get("examiner")
            if (self.phase=="guide" and self.guide.step!="exam") or type(ident) is not int or ident<1:
                raise ValueError("Ungültige Eingabe.")
            self.operators.active_name(ident)
            self.draft["examiner"]=ident
            self.touch()
        elif name=="person.save":
            ident=args.get("examiner")
            if ident is not None and (type(ident) is not int or ident<1):
                raise ValueError("Ungültige Eingabe.")
            return self.operators.rename(limited(args.get("name"),48,False),ident)
        elif name=="person.active":
            ident=args.get("examiner")
            active=args.get("active")
            if type(ident) is not int or type(active) is not bool or args.get("confirmed") is not True:
                raise ValueError("Bitte zuerst bestätigen.")
            if not active and self.draft and self.draft["examiner"]==ident and self.phase!="report":
                self.draft["examiner"]=None
                self.touch()
            self.operators.set_active(ident,active)

    def lease(self, source, kind, draft_id, field=None):
        if field not in (None,"ticket","device","remarks","slot","phase","autofill"):
            raise ValueError("Ungültige Eingabe.")
        key=(source,field)
        now=monotonic()
        for editor,(draft,expires) in list(self.editors.items()):
            if expires<=now or not self.draft or draft!=self.draft["id"]:
                del self.editors[editor]
        if kind is False:
            if draft_id is None or self.editors.get(key,(None,))[0]==draft_id:
                self.editors.pop(key,None)
        elif (kind is True and self.draft and draft_id==self.draft["id"] and
              self.phase in ("entry","guide") and (key in self.editors or len(self.editors)<12)):
            if field is not None:
                self.guard_editors(source,{field})
            self.editors[key]=(draft_id,now+20)
        else:
            raise ValueError("Der Entwurf hat sich geändert.")

    def guard_editors(self,source,fields=None):
        if not self.draft:
            return
        now=monotonic()
        if any(name!=source and draft==self.draft["id"] and expires>now and
               (fields is None or field in fields)
               for (name,field),(draft,expires) in self.editors.items()):
            raise ValueError("Der Entwurf wird an einer anderen Anzeige bearbeitet.")

    @staticmethod
    def controller(source):
        # Qt generates a process UUID; the web gateway mints a session+tab ID.
        # Legacy device commands keep their existing API and cannot displace a live controller.
        return source.startswith("web-") or len(source)==32 and all(c in "0123456789abcdef" for c in source)

    def live_owner(self):
        if self.phase not in ACTIVE_STAGES or not self.owner:
            return None
        holder,draft,expires=self.owner
        return holder if draft==self.draft["id"] and expires>monotonic() else None

    def claim_owner(self,source):
        self.owner=(source,self.draft["id"],monotonic()+OWNER_LEASE)

    def control(self,source,args):
        self.require_draft(args,ACTIVE_STAGES,version=True)
        if args.get("confirmed") is not True:
            raise ValueError("Bitte zuerst bestätigen.")
        holder=self.live_owner()
        action=args.get("action")
        if action=="release" and holder==source:
            self.owner=None
            self.editors={key:value for key,value in self.editors.items() if key[0]!=source}
        elif action=="resume" and holder is None:
            self.guard_editors(source)
            self.claim_owner(source)
        else:
            raise ValueError("Diese Prüfung wird an einer anderen Anzeige bedient.")
        self.touch()

    def guard_owner(self,source):
        if self.phase in ACTIVE_STAGES:
            holder=self.live_owner()
            if holder and holder!=source:
                raise ValueError("Diese Prüfung wird an einer anderen Anzeige bedient.")
            if not holder and self.controller(source):
                raise ValueError("Prüfung an dieser Anzeige ausdrücklich fortsetzen.")

    def command(self, request, source="local"):
        """Serialize public state mutations and replay responses by client/key."""
        if not isinstance(request,dict) or set(request)-{"id","op","args","epoch"}:
            return {"ok":False,"error":"Ungültige Eingabe."}
        key,op,args=request.get("id"),request.get("op"),request.get("args",{})
        if (not isinstance(op,str) or len(op)>40 or not isinstance(args,dict) or
                (key is not None and (not isinstance(key,str) or len(key)>80))):
            return {"ok":False,"error":"Ungültige Eingabe."}
        with self.lock:
            try:
                if request.get("epoch",self.epoch)!=self.epoch:
                    raise ValueError("Die Station wurde neu gestartet.")
                if key and (source,key) in self.completed:
                    return self.completed[(source,key)]
                if op=="state":
                    holder=self.live_owner()
                    if holder==source:
                        self.claim_owner(source)
                    data=self.snapshot()
                    if self.phase in ACTIVE_STAGES:
                        data["control"]="yours" if holder==source else "other" if holder else "available"
                elif op=="draft.control":
                    data=self.control(source,args)
                elif op=="draft.editor":
                    if args.get("active") is True:
                        self.guard_owner(source)
                    data=self.lease(source,args.get("active"),args.get("draft"),args.get("field"))
                else:
                    if op in OWNER_OPS:
                        self.guard_owner(source)
                    if op=="draft.edit" and isinstance(args.get("changes"),dict):
                        self.guard_editors(source,set(args["changes"]))
                    if op in ("exam.start","review.find","exam.submit","guide.cancel","guide.back","draft.discard"):
                        self.guard_editors(source)
                    if op=="review.confirm" and source=="nextion":
                        # Frozen panel still requires the operator to select and use the slot explicitly.
                        args=dict(args,same_reading_confirmed=True)
                    data=self.dispatch(op,args)
                    if op in ("exam.start","review.find") and self.phase in ACTIVE_STAGES and self.controller(source):
                        self.claim_owner(source)
                    elif self.phase not in ACTIVE_STAGES:
                        self.owner=None
                    if op in ("draft.new","draft.edit","draft.discard","exam.start","exam.submit",
                              "review.confirm","language.report","person.pick","person.active"):
                        self.checkpoint()
                result={"ok":True,"data":data}
            except (ValueError,KeyError,TypeError,sqlite3.Error,OSError) as error:
                if isinstance(error,(sqlite3.Error,OSError)):
                    LOG.warning("Command %s failed (%s)",op,type(error).__name__)
                result={"ok":False,"error":str(error) if isinstance(error,ValueError) else "Aktion fehlgeschlagen."}
            # Only replay bounded mutations. Never cache report copies or secrets.
            if key and op not in ("state","history","report.get","report.view","people","templates","draft.editor"):
                if len(self.completed)>=256:
                    self.completed.popitem(last=False)
                self.completed[(source,key)]=result
            return result

    def dispatch(self,op,args):
        if op=="state":
            return self.snapshot()
        if op=="history":
            return self.history()
        if op=="people":
            return self.operators.examiners(include_inactive=True)[:100]
        if op=="templates":
            return self.operators.appliances(self.language)
        if op=="report.get":
            return self.get_report(args.get("report"))
        if op=="report.view":
            report=self.get_report(args.get("report"))
            return {"kind":result_kind(report),"fields":selected_fields(report,self.language),
                    "measurements":[measurement_summary(m,language=self.language) for m in visible_measurements(report)],
                    "checks":report_checks(report,self.language)}
        if op=="report.qr":
            from reportlab.graphics.barcode.qrencoder import QRCode, QRErrorCorrectLevel
            url=self.report_link(args.get("report"))
            qr=QRCode(None,QRErrorCorrectLevel.M)
            qr.addData(url)
            qr.make()
            return {"url":url,"modules":qr.modules}
        if op=="draft.new":
            return self.begin(args)
        if op=="draft.edit":
            return self.edit(args)
        if op=="draft.discard":
            self.require_draft(args,STATES,version=True)
            if args.get("confirmed") is not True:
                raise ValueError("Bitte zuerst bestätigen.")
            self.draft=self.guide=self.selected=self.examination=None
            self.sequence+=1
            return
        if op in ("exam.start","review.find"):
            return self.start_examination(args,op)
        if op=="exam.submit":
            return self.guide_submit(args)
        if op=="review.confirm":
            return self.save_selected(args)
        if op=="import.reset":
            self.require_draft(args,("waiting","review"),version=True)
            if args.get("confirmed") is not True or not hasattr(self.receiver,"confirm_reset"):
                raise ValueError("Bitte zuerst bestätigen.")
            self.receiver.confirm_reset(args.get("reset"))
            self.selected=None
            self.advance("waiting")
            self.refresh_import()
            self.wait_note="Speicher-Reset bestätigt. Messung und Slot bewusst auswählen."
            return
        if op in ("guide.choose","guide.back","guide.cancel","exam.function"):
            self.require_draft(args,("guide",),version=True)
            if op=="guide.choose":
                index=args.get("choice")
                if args.get("step")!=self.guide.step:
                    raise ValueError("Der angezeigte Prüfschritt ist veraltet.")
                if type(index) is not int or not self.guide.choose(index):
                    LOG.warning("Guide choice rejected: step=%s type=%s",self.guide.step,type(index).__name__)
                    raise ValueError("Ungültige Auswahl im Prüfschritt.")
            elif op=="guide.back":
                if self.guide.step=="visual":
                    self.guide=None
                    self.draft["stage"]="entry"
                elif not self.guide.back():
                    raise ValueError("Abgebrochenen Lauf dokumentieren oder Vorgang beenden.")
            elif op=="guide.cancel":
                if args.get("confirmed") is not True:
                    raise ValueError("Bitte zuerst bestätigen.")
                self.guide=self.examination=None
                self.baseline=self.store.snapshot(tuple(SOURCES))
                self.draft["stage"]="entry"
            else:
                value=args.get("value")
                if self.guide.step!="exam" or value not in CYCLE:
                    raise ValueError("Ungültige Eingabe.")
                self.guide.functional=value
            self.touch()
        elif op in ("review.manual","review.select","review.back"):
            self.require_draft(args,("waiting","review"),version=True)
            if op=="review.manual":
                self.selected=None
                self.wait_note="Vorhandene Messung bewusst auswählen."
                self.advance("review")
            elif op=="review.back":
                self.selected=None
                self.advance("guide" if self.guide else "entry")
            else:
                key=args.get("record")
                self.refresh_import()
                row=next((r for r in self.slots if list(self.identity(r))==key),None)
                if not row or self.phase!="review":
                    raise ValueError("Import geändert. Speicherplatz erneut auswählen.")
                self.selected=row
                self.touch()
        elif op=="language.report":
            self.require_draft(args,("entry","guide"),version=True)
            self.draft["report_language"]=config.validated("language",args.get("language"))
            self.touch()
        elif op=="settings.save":
            updates=args.get("values")
            if not isinstance(updates,dict) or not updates:
                raise ValueError("Ungültige Eingabe.")
            if "tester_mode" in updates:
                if self.phase in ("guide","waiting","review") or not hasattr(self.receiver,"set_mode"):
                    raise ValueError("Prüfung zuerst beenden.")
                mode=config.validated("tester_mode",updates["tester_mode"])
                if mode=="rs232" and not self.receiver.has_rs232:
                    raise ValueError("RS232-Port zuerst lokal konfigurieren.")
            previous_language=self.language
            self.config=config.save(updates,self.config_path)
            if "tester_mode" in updates:
                self.receiver.set_mode(mode)
                self.refresh_import()
            if previous_language!=self.language:
                self.award("switches")
            self.sequence+=1
            if self.config["professional"]:
                self.milestone=0
                self.achievements_pending.clear()
        elif op in ("person.pick","person.save","person.active"):
            return self.person(op,args)
        elif op=="report.print":
            return self.queue_print(args.get("report"),args.get("confirmed"))
        elif op=="novelty.print":
            return self.novelty(args)
        elif op=="printer.test":
            return self.queue_print(None,args.get("confirmed"),test=True)
        elif op=="report.link":
            return self.report_link(args.get("report"))
        elif op=="printer.probe":
            def probe(endpoint):
                with socket.create_connection(endpoint,timeout=3):
                    return True
            self.job("printer","probe",probe,self.endpoint())
            self.probe_note="TCP-Verbindung wird geprüft ..."
        elif op in ("wifi.scan","wifi.connect","wifi.hotspot","wifi.stop"):
            return self.net_action(op,args)
        elif op in ("power.halt","power.reboot"):
            if (not self.allow_power or args.get("confirmed") is not True or
                    "printer" in self.jobs or self.phase in ("guide","waiting","review")):
                raise ValueError("Systemaktion nicht erlaubt oder fehlgeschlagen.")
            self.job("power","power",self.power,op.partition(".")[2])
            self.power_note="Systemaktion wird angefordert ..." if self.config["professional"] or op=="power.reboot" else "Bis bald, Werkstattteam!"
        elif op=="personality.treat":
            if self.config["professional"] or self.phase in ("guide","waiting","review"):
                raise ValueError("Aktion fehlgeschlagen.")
            if monotonic()>=getattr(self,"next_treat",0):
                self.next_treat=monotonic()+2
                self.award("treats")
        elif op=="personality.pet":
            if self.config["professional"] or self.phase in ("guide","waiting","review"):
                raise ValueError("Aktion fehlgeschlagen.")
            self.pet_pending=min(16,self.pet_pending+1)
        elif op=="personality.engineering":
            self.award("engineering")
        elif op=="system.info":
            if "personality" not in self.jobs and monotonic()>=self.next_metrics:
                self.next_metrics=monotonic()+8
                self.job("personality","metrics",self.metrics)
            return dict(self.engineering)
        else:
            raise ValueError("Unbekannter Befehl.")

    def award(self,key,count=1):
        if not self.config["professional"]:
            self.achievements_pending[key]=self.achievements_pending.get(key,0)+count

    def novelty(self,args):
        if (self.config["professional"] or self.phase in ("guide","waiting","review") or
                args.get("confirmed") is not True or args.get("kind") not in ITEMS):
            raise ValueError("Bitte zuerst bestätigen.")
        if "printer" in self.jobs or monotonic()-self.last_print.get("novelty",-5)<4:
            raise ValueError("Doppelter Druckauftrag unterdrückt.")
        self.job("printer","novelty",self.sender,*self.endpoint(),novelty_receipt(args["kind"],self.language,self.config["feed_mm"]))
        self.last_print["novelty"]=monotonic()
        self.novelty_note="Spassbeleg wird gedruckt ..."

    def metrics(self):
        with closing(self.store.db()) as db:
            total=db.execute("SELECT count(*) FROM reports").fetchone()[0]
        return {"system":system_metrics(self.db,self.endpoint()),"reports":report_counts(self.db),
                "personality":self.cache.counts(),"version":VERSION,"total":total}

    def maintenance(self, updates):
        exams,_=report_counts(self.db)
        self.cache.milestones(exams)
        return self.cache.achievements(updates)

    def tick(self):
        with self.lock:
            now=monotonic()
            if now>=self.next_config_check:
                self.next_config_check=now+2
                if self.web_status:
                    self.web_connection=read_status(self.web_status)
                    if self.auto_port:
                        self.update_download_base()
                settings=config.load(self.config_path)
                if settings!=self.config:
                    self.config=settings
                    self.sequence+=1
                    if settings["professional"]:
                        self.milestone=0
            if now>=self.last_import_check:
                self.last_import_check=now+.55
                try:
                    self.refresh_import()
                except sqlite3.Error:
                    LOG.warning("BENNING cache refresh failed")
            for pool,(action,future) in list(self.jobs.items()):
                if not future.done():
                    continue
                del self.jobs[pool]
                try:
                    value=future.result()
                except Exception as error:
                    LOG.warning("%s job failed (%s)",pool,type(error).__name__)
                    if pool=="network":
                        if action=="poll":
                            self.ssid=self.ip=""
                            self.update_download_base()
                        if action=="hotspot":
                            self.hotspot_due=now+180
                        self.network_note=str(error) if isinstance(error,NetworkError) else ""
                    elif pool=="printer":
                        if action=="probe":
                            self.probe_note="TCP-Verbindung fehlgeschlagen."
                        elif action=="novelty":
                            self.novelty_note="Druckfehler. Beleg prüfen, dann ggf. erneut drucken."
                        else:
                            self.print_note="Druckfehler. Beleg prüfen, dann ggf. erneut drucken."
                    elif pool=="power":
                        self.power_note="Systemaktion nicht erlaubt oder fehlgeschlagen."
                    continue
                if pool=="network":
                    if action=="scan":
                        self.wifi_generation+=1
                        self.access_points={f"{self.wifi_generation}:{i}":net for i,net in enumerate(value)}
                        self.network_note="Netzwerke suchen"
                    else:
                        self.ssid,self.ip=value[:2]
                        self.update_download_base()
                        self.network_note=""
                        if self.ssid:
                            self.hotspot_due=now+90
                        elif action=="poll" and self.hotspot_fallback and now>=self.hotspot_due:
                            self.hotspot_due=now+180
                            self.job("network","hotspot",self.network.hotspot)
                elif pool=="printer":
                    if action=="probe":
                        self.probe_note="TCP-Verbindung erfolgreich."
                    elif action=="novelty":
                        self.novelty_note="Spassbeleg gesendet."
                    else:
                        self.print_note="Druckdaten gesendet. Bitte Beleg prüfen."
                        if action=="print":
                            self.award("prints")
                elif action=="pet":
                    self.pet_count=value
                    self.achievement_stats={**self.achievement_stats,"pets":value}
                    self.pet_reply=random.choice([reply for reply in PET_REPLIES if reply!=self.pet_reply])
                elif action=="maintenance":
                    self.achievement_stats=value
                    self.pet_count=max(self.pet_count or 0,self.achievement_stats["pets"])
                elif action=="metrics":
                    self.engineering=value
                    self.metric_generation+=1
            if self.milestone and now>=self.milestone_until:
                self.milestone=0
            if (self.auto_port or self.access_points or self.hotspot_fallback) and now>=self.last_network_check and "network" not in self.jobs:
                self.last_network_check=now+12
                self.job("network","poll",self.network.status)
            if self.config["professional"]:
                self.last_operating_sample=now
                self.achievements_pending.clear()
            elif now-self.last_operating_sample>=60:
                self.award("seconds",int(now-self.last_operating_sample))
                self.last_operating_sample=now
            if self.pet_pending and "personality" not in self.jobs:
                increment,self.pet_pending=self.pet_pending,0
                self.job("personality","pet",self.cache.pet,increment)
            if ("personality" not in self.jobs and not self.config["professional"] and
                    self.phase not in ("guide","waiting","review") and
                    (self.maintenance_dirty or
                     self.achievements_pending and now>=self.next_achievement_sample)):
                self.maintenance_dirty=False
                updates,self.achievements_pending=self.achievements_pending,{}
                self.next_achievement_sample=now+10
                self.job("personality","maintenance",self.maintenance,updates)

    def update_download_base(self):
        ip=self.web_connection.get("ip") or self.ip
        base=(f"http://{ip}:{self.auto_port}" if ip and self.auto_port else self.fixed_url) if self.downloads_online else ""
        if base!=self.base_url:
            self.base_url=base
            self.links.clear()

    def snapshot(self):
        """Bounded JSON state. Original report content is fetched on demand."""
        state=self.receiver.status
        guide=None
        if self.guide:
            g=self.guide
            step=STEPS[g.step]
            guide={"step":g.step,"title":step.title,"instruction":{lang:g.instruction(lang) for lang in ("de","en")},
                   "help":step.help,"art":g.art,"choices":[label for label,_ in g.choices()],
                   "phase":step.phase,"rows":g.rows(),"functional":g.functional,"stored":g.stored,"blocked":g.blocked}
            if g.step in ("start","running","low_continue","energise"):
                # Keep the unchanged safety graph; only group its existing observations.
                guide["actions"]={"primary":[3,4],"observations":[0,1,5,6]}
        get_row=lambda row: {"key":list(self.identity(row)),"slot":row["slot"],
                 "date":row["original"]["tester_date"],"verdict":row["original"]["verdict"],
                 "class":row["original"]["protection_class"],"origin":self.measurement_origin(row)}
        import_source=state.source or self.receiver.mode
        art,body=WAIT_BODY.get(import_source,WAIT_BODY["usb"])
        return {"format":FORMAT,"epoch":self.epoch,"sequence":self.sequence,"language":self.language,
                "settings":dict(self.config,printer_host=self.endpoint()[0],printer_port=self.endpoint()[1],tester_mode=self.receiver.mode),
                "draft":dict(self.draft) if self.draft else None,"guide":guide,
                "report_language":self.report_language() if self.draft else self.language,
                "receiver":dict(asdict(state),mode=self.receiver.mode),"batch":self.batch,
                "slots":[get_row(r) for r in self.slots[:999]],"import_art":art,"import_body":body,
                "selected":get_row(self.selected) if self.selected else None,"wait_note":self.wait_note,
                "report":self.report_id,"report_kind":result_kind(self.report) if self.report else None,
                "download_base":self.base_url,"web":self.web_connection,"recovery_note":self.recovery_note,"novelty_note":self.novelty_note,
                "printing":"printer" in self.jobs,"print_note":self.print_note,"probe_note":self.probe_note,
                "wifi":{"ssid":self.ssid,"ip":self.ip,"busy":"network" in self.jobs,"note":self.network_note,
                        "networks":[{"id":i,"name":n.name,"security":n.security,"signal":n.signal,"saved":bool(n.saved)}
                                    for i,n in self.access_points.items()]},
                "power":{"enabled":self.allow_power,"note":self.power_note},
                "personality":{"slogan":None,
                               "pets":self.pet_count,"pet_reply":self.pet_reply,"milestone":self.milestone,
                               "achievements":{} if self.config["professional"] else self.achievement_stats}}
