"""Isolated SQLite cache shared by the station and optional slogan worker."""
from contextlib import closing, contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import random
import sqlite3

ROOT = Path(__file__).resolve().parent
CACHE = Path(os.environ.get("FMI_SLOGAN_DB", Path.home()/".local/state/rc-printstation/slogans.sqlite3"))
OFFLINE = tuple(tuple(line.split("\t")) for line in
                (ROOT/"translations/slogans.tsv").read_text(encoding="utf-8").splitlines() if line)
# A fixed shuffle and persistent position avoid repeats across restarts.
ORDER = list(range(len(OFFLINE)))
random.Random(71).shuffle(ORDER)
LIMIT = 90
SCHEMA = """
CREATE TABLE IF NOT EXISTS slogan_meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS generated_slogans(
    id INTEGER PRIMARY KEY, de TEXT NOT NULL UNIQUE, en TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL, shown INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS slogan_usage(
    day TEXT PRIMARY KEY, requests INTEGER NOT NULL DEFAULT 0,
    tokens INTEGER NOT NULL DEFAULT 0, reserved INTEGER NOT NULL DEFAULT 0
);
"""


def utc_day():
    return datetime.now(timezone.utc).date().isoformat()


class SloganStore:
    def __init__(self, path=CACHE):
        self.path = Path(path)

    @contextmanager
    def db(self):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT, 0o600)
        os.close(fd)
        with closing(sqlite3.connect(self.path, timeout=.4)) as conn, conn:
            conn.executescript(SCHEMA)
            yield conn

    def add(self, pairs, provider):
        with self.db() as conn:
            conn.executemany("INSERT OR IGNORE INTO generated_slogans(de,en,source) VALUES(?,?,?)",
                             ((de,en,provider) for de,en in pairs))

    def remaining(self):
        with self.db() as conn:
            return conn.execute("SELECT count(*) FROM generated_slogans WHERE shown=0").fetchone()[0]

    @staticmethod
    def value(conn, key, default=0):
        row = conn.execute("SELECT value FROM slogan_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def set_value(conn, key, value):
        conn.execute("INSERT INTO slogan_meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key,value))

    def next(self):
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT id,de,en FROM generated_slogans WHERE shown=0 ORDER BY id LIMIT 1").fetchone()
            if row:
                conn.execute("UPDATE generated_slogans SET shown=1 WHERE id=?", (row[0],))
                return row[1:]
            pos = self.value(conn,"offline_position")
            self.set_value(conn,"offline_position",(pos+1) % len(ORDER))
            return OFFLINE[ORDER[pos % len(ORDER)]]

    def pet(self, increment=1):
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            count = self.value(conn,"pets")+increment
            self.set_value(conn,"pets",count)
            return count

    def milestones(self, exams):
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            previous = self.value(conn,"exams_highwater",exams)
            self.set_value(conn,"exams_highwater",max(previous,exams))
            return max((n for n in (10,50,100,500) if previous<n<=exams),default=0)

    def schedule(self, provider, interval, now):
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            key = "last_"+provider
            if now-self.value(conn,key)<interval:
                return False
            self.set_value(conn,key,now)
            return True

    def reserve(self, day, requests, tokens, estimate):
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("INSERT OR IGNORE INTO slogan_usage(day) VALUES(?)", (day,))
            count, used, reserved = conn.execute(
                "SELECT requests,tokens,reserved FROM slogan_usage WHERE day=?", (day,)).fetchone()
            if count>=requests or used+reserved+estimate>tokens:
                return False
            conn.execute("UPDATE slogan_usage SET requests=requests+1,reserved=reserved+? WHERE day=?",
                         (estimate,day))
            return True

    def settle(self, day, estimate, billed):
        with self.db() as conn:
            conn.execute("UPDATE slogan_usage SET reserved=reserved-?,tokens=tokens+? WHERE day=?",
                         (estimate,billed,day))

    def counts(self):
        with self.db() as conn:
            today = conn.execute("SELECT requests,tokens,reserved FROM slogan_usage WHERE day=?",
                                 (utc_day(),)).fetchone() or (0,0,0)
            return self.value(conn,"pets"),today
