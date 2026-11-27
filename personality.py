"""Home-only presentation and read-only metrics, off the station UART loop."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import logging
import random
import shutil
import socket
import sqlite3
import time

from benning_csv import PASS
from slogan_store import LIMIT, SloganStore

VERSION = "0.7.1"
PROTOCOL = 71
LOG = logging.getLogger(__name__)
PET_REPLIES = (
    "Schnurr... äh, wuff!", "Eine Pfote voller Dank.", "Ich passe auf die Werkbank auf.",
    "Das war genau die richtige Stelle.", "Der Wolf wedelt diskret.", "Wuff vom Werkstattwolf.",
    "Zuneigung erfolgreich empfangen.", "Der nächste Kaffee geht auf mich. Vielleicht.",
    "Mehr Pfoten, weniger Schrott.", "Die Pfoten bleiben bei mir.",
)


def report_counts(path):
    """Read aggregate statistics without pulling names, remarks or readings."""
    query = """
        WITH safe AS (
            SELECT id, CASE WHEN json_valid(data) THEN data ELSE '{{}}' END AS doc FROM reports
        ), real AS (
            SELECT id, json_extract(doc,'$.source') AS source,
                json_extract(doc,'$.record_id') AS reading,
                lower(trim(coalesce(json_extract(doc,'$.record.verdict'),
                                    json_extract(doc,'$.verdict'),''))) AS verdict
            FROM safe WHERE json_type(doc)='object'
        )
        SELECT count(*),count(DISTINCT CASE
            WHEN source='BENNING' AND verdict IN ({}) THEN
                CASE WHEN reading IS NULL THEN 'report:'||id ELSE 'record:'||reading END
            END)
        FROM real WHERE source IN ('BENNING','EXAMINATION')
    """.format(",".join("?" for _ in PASS))
    uri=Path(path).absolute().as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,timeout=.3)) as conn:
        return conn.execute(query,tuple(PASS)).fetchone()


def system_metrics(path, endpoint):
    def read_value(file, convert):
        try:
            return convert(Path(file).read_text())
        except (OSError,ValueError,KeyError,ZeroDivisionError):
            return None
    temperature = read_value("/sys/class/thermal/thermal_zone0/temp", lambda s: float(s)/1000)
    load = read_value("/proc/loadavg", lambda s: float(s.split()[0]))
    uptime = read_value("/proc/uptime", lambda s: int(float(s.split()[0])))
    def mem_used(text):
        values={line.split(":")[0]:int(line.split()[1]) for line in text.splitlines()
                if line.startswith(("MemTotal:","MemAvailable:"))}
        return 100-round(100*values["MemAvailable"]/values["MemTotal"])
    memory = read_value("/proc/meminfo",mem_used)
    disk = shutil.disk_usage(Path(path).absolute().parent)
    try:
        with socket.create_connection(endpoint,timeout=1):
            connected=True
    except OSError:
        connected=False
    return temperature,load,memory,round(100*disk.used/disk.total),uptime,connected


class Personality:
    def __init__(self, ui, reports, cache, *, eggs=True, clock=time.monotonic, metrics=system_metrics):
        self.ui,self.reports,self.store=ui,reports,SloganStore(cache)
        self.eggs,self.clock,self.metrics=eggs,clock,metrics
        self.worker=ThreadPoolExecutor(max_workers=1,thread_name_prefix="personality")
        self.job=None
        self.redraw_home=True
        self.redraw_pet=False
        self.next_stats=0
        self.next_metrics=0
        self.stats_dirty=False
        self.tap_count=0
        self.tap_until=0
        self.milestone=0
        self.milestone_until=0
        self.pet_reply="Ein kleiner Werkstattwolf sagt hallo."
        self.pet_count=None
        self.pet_pending=0

    def drive(self,kind,fn,*args):
        if self.job is None:
            self.job=(kind,self.worker.submit(fn,*args))

    def draw_home(self):
        if self.ui.settings.page=="home":
            self.ui.text("tSlogan","",LIMIT)

    def draw_pet(self):
        if self.ui.settings.page=="pet":
            if self.pet_count is not None:
                self.ui.say("tPets","Streicheleinheiten: {count}",46,count=self.pet_count)
            self.ui.say("tPetReply",self.pet_reply,LIMIT)

    def enter(self):
        page=self.ui.settings.page
        if page=="home":
            self.tap_count=0
            self.redraw_home=True
        elif page=="pet":
            self.next_metrics=0
            self.redraw_pet=True
        elif page=="engineering":
            self.next_metrics=0

    def active(self):
        return self.ui.workflow.guide is not None

    def event(self,frame):
        page=self.ui.settings.page
        if frame==b"RC71:LOGO" and page=="home" and self.eggs and not self.active():
            now=self.clock()
            if now>=self.tap_until:
                self.tap_count=0
            self.tap_count+=1
            self.tap_until=now+2
            if self.tap_count==5:
                self.tap_count=0
                self.ui.cmd("page pet")
        elif frame==b"RC71:ENGINEER" and page=="home" and not self.active():
            self.ui.cmd("page engineering")
        elif frame==b"RC71:PET" and page=="pet" and self.eggs:
            self.pet_pending=min(32,self.pet_pending+1)
            self.count_pets()

    def count_pets(self):
        if self.pet_pending and self.job is None:
            increment,self.pet_pending=self.pet_pending,0
            self.drive("pet",self.store.pet,increment)

    def stats(self, check_milestone=False):
        try:
            exams,passed=report_counts(self.reports)
        except sqlite3.Error:
            exams=passed=None
        milestone=self.store.milestones(exams) if check_milestone and exams is not None else 0
        return exams,passed,milestone

    def diagnostic(self,endpoint):
        return self.metrics(self.reports,endpoint),self.stats(),self.store.counts()

    def draw_diagnostic(self, result):
        if self.ui.settings.page!="engineering":
            return
        (temp,load,ram,disk,uptime,printer),(exams,passed,_),(pets,(requests,tokens,reserved))=result
        tr=self.ui.tr
        missing=tr("Nicht verfügbar")
        receiver=self.ui.tester.receiver.status.state
        tester=tr({"waiting":"Verbunden", "receiving":"Empfang läuft ...","imported":"Verbunden",
                   "disconnected":"Nicht verbunden","searching":"Suche Tester / USB","simulation":"Simulation",
                   "error":"Kommunikationsfehler","interrupted":"Transfer unterbrochen","file":"Datei"}.get(receiver,"Unbekannt"))
        values=(
            ("CPU-Temperatur",f"{temp:.1f} °C" if temp is not None else missing),
            ("CPU-Last (1 min)",f"{load:.2f}" if load is not None else missing),
            ("RAM / Datenträger",(f"{ram} %" if ram is not None else missing)+f" / {disk} %"),
            ("Betriebszeit",f"{uptime//86400} d  {uptime//3600%24:02d}:{uptime//60%60:02d}" if uptime is not None else missing),
            ("Backend / HMI-Protokoll",f"v{VERSION} / {PROTOCOL}"),
            ("Drucker (TCP)",tr("Erreichbar" if printer else "Nicht erreichbar")),
            ("BENNING",tester),
            ("Prüfungen / bestandene Tests",f"{exams} / {passed}" if exams is not None else missing),
            ("Gespeicherte Berichte",str(self.total_reports) if self.total_reports is not None else missing),
            ("Streicheleinheiten",str(pets)),
            ("", ""),
            ("", ""),
        )
        for i,(label,value) in enumerate(values):
            self.ui.text(f"tD{i}",f"{tr(label)}: {value}" if label else "",62)

    def count_all(self, endpoint):
        try:
            uri=Path(self.reports).absolute().as_uri()+"?mode=ro"
            with closing(sqlite3.connect(uri,uri=True,timeout=.3)) as conn:
                total=conn.execute("SELECT count(*) FROM reports").fetchone()[0]
        except sqlite3.Error:
            total=None
        return total,self.diagnostic(endpoint)

    def finish(self):
        if self.job is None or not self.job[1].done():
            return
        kind,future=self.job
        self.job=None
        try:
            value=future.result()
        except Exception as exc:
            LOG.warning("Personality %s unavailable (%s)",kind,type(exc).__name__)
            return
        if kind=="stats":
            return
        elif kind=="diagnostic":
            self.total_reports,result=value
            self.draw_diagnostic(result)
        elif kind=="pet-count":
            self.pet_count=value[0]
            self.draw_pet()
        elif kind=="pet":
            self.pet_count=value
            self.pet_reply=random.choice([line for line in PET_REPLIES if line!=self.pet_reply])
            self.draw_pet()

    def tick(self):
        self.finish()
        now=self.clock()
        page=self.ui.settings.page
        # Page announcements can arrive in batches. Resolve all of them
        # before sending local-component updates from the UART tick.
        if page=="home" and self.redraw_home and not self.active():
            self.redraw_home=False
            self.draw_home()
        elif page=="pet" and self.redraw_pet:
            self.redraw_pet=False
            self.draw_pet()
        self.count_pets()
        if self.job is not None:
            return
        if now>=self.next_stats and (self.stats_dirty or self.next_stats==0):
            self.next_stats=now+2
            self.stats_dirty=False
            self.drive("stats",self.stats,True)
        elif page=="engineering" and now>=self.next_metrics:
            self.next_metrics=now+10
            self.drive("diagnostic",self.count_all,self.ui.settings.endpoint(self.ui.settings.cfg()))
        elif page=="pet" and now>=self.next_metrics:
            self.next_metrics=now+10
            self.drive("pet-count",self.store.counts)

    def close(self):
        self.worker.shutdown(wait=False,cancel_futures=True)
