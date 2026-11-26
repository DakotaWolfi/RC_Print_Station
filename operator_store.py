"""Persistent examiner directory and appliance history for the station."""
from contextlib import closing
import json
from unicodedata import normalize

from i18n import tr

APPLIANCES=("Kaffeemaschine","Wasserkocher","Leuchte","Bügeleisen","Haartrockner",
            "Ventilator","Küchengerät","Heizgerät")
SCHEMA="""
CREATE TABLE IF NOT EXISTS examiners(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), last_used TEXT
);
CREATE TABLE IF NOT EXISTS recent_appliances(
    name_key TEXT PRIMARY KEY, description TEXT NOT NULL, last_used TEXT NOT NULL
);
"""


def name_key(text):
    return normalize("NFC"," ".join(text.split())).casefold()


class Operators:
    def __init__(self,db):
        self.db=db

    def examiners(self, *, include_inactive=False):
        with closing(self.db()) as conn:
            rows=conn.execute("""SELECT id,name,active,last_used FROM examiners
                WHERE active=1 OR ? ORDER BY active DESC,last_used DESC,name_key,id""",
                (int(include_inactive),)).fetchall()
        return [dict(row) for row in rows]

    def rename(self, name, ident=None):
        if not name.strip() or len(name)>48 or any(not char.isprintable() for char in name):
            raise ValueError("Prüfperson mit gültigem Namen eingeben.")
        with closing(self.db()) as conn,conn:
            conn.execute("BEGIN IMMEDIATE")
            lookup=conn.execute("SELECT id,active FROM examiners WHERE name_key=?",(name_key(name),)).fetchone()
            if lookup and lookup["id"]!=ident:
                if ident is None and lookup["active"]:
                    return lookup["id"]
                raise ValueError("Name bereits vorhanden. Inaktive Namen können reaktiviert werden.")
            if ident is None:
                return conn.execute("INSERT INTO examiners(name,name_key) VALUES(?,?)",
                                    (name,name_key(name))).lastrowid
            if not conn.execute("UPDATE examiners SET name=?,name_key=? WHERE id=?",
                                (name,name_key(name),ident)).rowcount:
                raise ValueError("Prüfperson nicht gefunden.")
        return ident

    def set_active(self,ident,active):
        with closing(self.db()) as conn,conn:
            conn.execute("UPDATE examiners SET active=? WHERE id=?",(int(active),ident))

    def active_name(self,ident):
        if ident is None:
            return ""
        with closing(self.db()) as conn:
            row=conn.execute("SELECT name FROM examiners WHERE id=? AND active=1",(ident,)).fetchone()
        if row is None:
            raise ValueError("Prüfperson ist nicht mehr aktiv. Bitte neu wählen.")
        return row["name"]

    def appliances(self,language="de"):
        with closing(self.db()) as conn:
            recent=[row["description"] for row in conn.execute("""SELECT description
                FROM recent_appliances ORDER BY last_used DESC,name_key LIMIT 8""")]
            # Pre-v0.6.1 installations have versioned reports but no history table.
            # Seed the visible list from those reports without mutating them.
            if len(recent)<8:
                keys={name_key(value) for value in recent}
                for row in conn.execute("SELECT data FROM reports ORDER BY id DESC LIMIT 120"):
                    try:
                        record=json.loads(row["data"])
                    except (TypeError,json.JSONDecodeError):
                        continue
                    if not isinstance(record,dict):
                        continue
                    description=record.get("device")
                    if record.get("source")=="SIMULATOR" or not isinstance(description,str) or not description.strip():
                        continue
                    key=name_key(description)
                    if key not in keys:
                        recent.append(description)
                        keys.add(key)
                        if len(recent)==8:
                            break
        keys={name_key(value) for value in recent}
        templates=[tr(language,label) for label in APPLIANCES]
        return [(label,True) for label in recent]+[(label,False) for label in templates if name_key(label) not in keys]


def record_use(conn,description,examiner_id,timestamp):
    conn.execute("""INSERT INTO recent_appliances(name_key,description,last_used) VALUES(?,?,?)
        ON CONFLICT(name_key) DO UPDATE SET description=excluded.description,last_used=excluded.last_used""",
        (name_key(description),description,timestamp))
    if examiner_id is not None:
        conn.execute("UPDATE examiners SET last_used=? WHERE id=?",(timestamp,examiner_id))
