"""Versioned measurements and report snapshots in the station SQLite database."""
from contextlib import closing
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
import sqlite3

from benning_csv import ImportErrorDetail, parse_csv
from benning_rs232 import parse_printout

PHASES=("Eingangsprüfung","Zwischenprüfung","Ausgangsprüfung")
SOURCES={"usb":"BENNING USB", "rs232":"BENNING RS232",
         "file-csv":"BENNING CSV-Datei", "file-txt":"BENNING TXT-Datei"}
SCHEMA="""
CREATE TABLE IF NOT EXISTS benning_records(
    id TEXT PRIMARY KEY, slot TEXT NOT NULL, original TEXT NOT NULL,
    first_source TEXT NOT NULL, first_imported TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benning_imports(
    id INTEGER PRIMARY KEY, source TEXT NOT NULL, encoding TEXT NOT NULL,
    imported TEXT NOT NULL, records INTEGER NOT NULL, newest TEXT, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS benning_import_rows(
    batch INTEGER NOT NULL REFERENCES benning_imports(id), slot TEXT NOT NULL,
    record_id TEXT NOT NULL REFERENCES benning_records(id), PRIMARY KEY(batch,slot)
);
CREATE TABLE IF NOT EXISTS benning_slots(
    source TEXT NOT NULL, slot TEXT NOT NULL,
    record_id TEXT NOT NULL REFERENCES benning_records(id),
    batch INTEGER NOT NULL REFERENCES benning_imports(id), PRIMARY KEY(source,slot)
);
CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, data TEXT NOT NULL);
"""


def now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


@dataclass(frozen=True)
class ImportResult:
    batch: int
    source: str
    count: int
    encoding: str
    imported: str
    suggested: str
    reason: str
    added: tuple[str,...]
    modified: tuple[str,...]


class Measurements:
    def __init__(self,path):
        self.path=path

    def db(self):
        conn=sqlite3.connect(self.path,timeout=2)
        conn.row_factory=sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(SCHEMA)
        except Exception:
            conn.close()
            raise
        return conn

    def import_bytes(self,data,source,encoding="auto",*,accept_reset=False):
        if source not in SOURCES:
            raise ValueError("Unbekannte BENNING-Quelle.")
        is_csv=source in ("usb","file-csv")
        if is_csv:
            code,records=parse_csv(data,encoding,wire=source=="usb")
        else:
            code,records=parse_printout(data,"cp437" if encoding=="auto" else encoding,
                                        wire=source=="rs232")
        new={}
        for record in records:
            original=asdict(record)
            # Canonical payload identity ignores framing / equivalent decodings.
            canonical={k:v for k,v in original.items() if k not in ("raw","raw_b64")}
            identity=sha256(json.dumps(canonical,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            new[record.slot]=(record,identity,original)
        timestamp=now()
        with closing(self.db()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            prev={row["slot"]:row["record_id"] for row in conn.execute(
                "SELECT slot,record_id FROM benning_slots WHERE source=?",(source,))}
            removed=prev.keys()-new.keys()
            if is_csv and source=="usb" and removed and not accept_reset:
                raise ImportErrorDetail("USB-Export enthält weniger Slots. RECALL wiederholen oder Reset prüfen.")
            added=tuple(sorted(new.keys()-prev.keys()))
            modified=tuple(sorted(slot for slot in new.keys() & prev.keys() if new[slot][1]!=prev[slot]))
            changes=added+modified
            suggested=max(changes or new.keys(), key=lambda slot:(new[slot][0].iso_date,slot))
            if not prev or removed and is_csv:
                reason="baseline"
            elif not changes:
                reason="unchanged"
            elif source=="usb" and len(changes)==1:
                reason="single-change"
            elif source=="rs232":
                reason="printout"
            else:
                reason="ambiguous"
            batch=conn.execute(
                "INSERT INTO benning_imports(source,encoding,imported,records,newest,reason) VALUES(?,?,?,?,?,?)",
                (source,code,timestamp,len(records),suggested,reason)).lastrowid
            # Full snapshots replace the current slot map. All earlier versions stay immutable.
            if is_csv:
                conn.execute("DELETE FROM benning_slots WHERE source=?",(source,))
            for slot,(_,identity,original) in new.items():
                conn.execute("INSERT OR IGNORE INTO benning_records VALUES(?,?,?,?,?)",
                             (identity,slot,json.dumps(original,ensure_ascii=False),source,timestamp))
                conn.execute("INSERT INTO benning_import_rows VALUES(?,?,?)",(batch,slot,identity))
                conn.execute("INSERT OR REPLACE INTO benning_slots VALUES(?,?,?,?)",(source,slot,identity,batch))
        return ImportResult(batch,source,len(records),code,timestamp,suggested,reason,added,modified)

    def latest(self, sources):
        with closing(self.db()) as conn:
            row=conn.execute(
                f"SELECT * FROM benning_imports WHERE source IN ({','.join('?' for _ in sources)}) ORDER BY id DESC LIMIT 1",
                tuple(sources)).fetchone()
        return dict(row) if row else None

    def slots(self,source):
        with closing(self.db()) as conn:
            rows=conn.execute("""SELECT s.slot, s.record_id, s.batch, i.imported, r.original
                FROM benning_slots s JOIN benning_records r ON r.id=s.record_id
                JOIN benning_imports i ON i.id=s.batch WHERE s.source=? ORDER BY s.slot DESC""",
                              (source,)).fetchall()
        return [dict(row,source=source,original=json.loads(row["original"])) for row in rows]

    def snapshot(self, sources):
        """Remember accepted imports and exact current slot identities per source."""
        with closing(self.db()) as conn,conn:
            conn.execute("BEGIN")
            imports={row["source"]:row["batch"] for row in conn.execute(
                "SELECT source,max(id) AS batch FROM benning_imports GROUP BY source")
                if row["source"] in sources}
            slots={source:{} for source in imports}
            for row in conn.execute("SELECT source,slot,record_id FROM benning_slots"):
                if row["source"] in slots:
                    slots[row["source"]][row["slot"]]=row["record_id"]
        return {source:(batch,slots[source]) for source,batch in imports.items()}

    @staticmethod
    def repair_fields(ticket,device,phase):
        if not isinstance(ticket,str) or not isinstance(device,str):
            raise ValueError("Prüfnummer und Gerätebeschreibung erforderlich.")
        ticket,device=ticket.strip(),device.strip()
        if not ticket or not device or len(ticket)>32 or len(device)>64 or not all(
                c.isprintable() for c in ticket+device):
            raise ValueError("Prüfnummer und Gerätebeschreibung prüfen.")
        if phase not in PHASES:
            raise ValueError("Ungültige Prüfart.")
        return ticket,device,phase

    def create_incomplete(self,ticket,device,phase,examination):
        ticket,device,phase=self.repair_fields(ticket,device,phase)
        report={"ticket":ticket,"device":device,"source":"EXAMINATION","phase":phase,
                "created":now(),"verdict":None,"measurements":[],
                "examination":dict(examination,status="Unvollständig")}
        with closing(self.db()) as conn,conn:
            ident=conn.execute("INSERT INTO reports(data) VALUES(?)",(json.dumps(report),)).lastrowid
        return ident,report

    def create_report(self,ticket,device,phase,selection,*,require_current=False,examination=None):
        ticket,device,phase=self.repair_fields(ticket,device,phase)
        # Resolve from the immutable batch, not from mutable slot metadata or UI fields.
        with closing(self.db()) as conn,conn:
            conn.execute("BEGIN IMMEDIATE")
            row=conn.execute("""SELECT r.original, i.source, i.imported, r.id
                FROM benning_import_rows b JOIN benning_records r ON b.record_id=r.id
                JOIN benning_imports i ON b.batch=i.id
                WHERE b.batch=? AND b.slot=? AND b.record_id=?""",
                (selection["batch"],selection["slot"],selection["record_id"])).fetchone()
            if row is None:
                raise ValueError("Messung ist nicht verfügbar.")
            if require_current and not conn.execute(
                    """SELECT 1 FROM benning_slots
                       WHERE source=? AND slot=? AND batch=? AND record_id=?""",
                    (row["source"],selection["slot"],selection["batch"],row["id"])).fetchone():
                raise ValueError("Import geändert. Speicherplatz erneut auswählen.")
            record=json.loads(row["original"])
            report={"ticket":ticket,"device":device,"source":"BENNING","phase":phase,
                    "created":now(),"verdict":record["verdict"],"measurements":record["measurements"],
                    "record":record,"record_id":row["id"],"imported":row["imported"],
                    "import_source":row["source"]}
            if examination:
                report["examination"]=examination
            ident=conn.execute("INSERT INTO reports(data) VALUES(?)",(json.dumps(report),)).lastrowid
        return ident,report
