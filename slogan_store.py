"""Persistent personality counters using the existing database and meta table."""
from contextlib import closing, contextmanager
import os
from pathlib import Path
import sqlite3

CACHE = Path(os.environ.get("FMI_SLOGAN_DB", Path.home()/".local/state/rc-printstation/slogans.sqlite3"))
LIMIT = 90
SCHEMA = "CREATE TABLE IF NOT EXISTS slogan_meta(key TEXT PRIMARY KEY, value INTEGER NOT NULL)"


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

    @staticmethod
    def value(conn, key, default=0):
        row = conn.execute("SELECT value FROM slogan_meta WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    @staticmethod
    def set_value(conn, key, value):
        conn.execute("INSERT INTO slogan_meta VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                     (key,value))

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

    def achievements(self, updates=None):
        names=("prints","switches","seconds","engineering","treats")
        with self.db() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for name in names:
                if updates and updates.get(name):
                    self.set_value(conn,"achievement_"+name,self.value(conn,"achievement_"+name)+updates[name])
            stats={name:self.value(conn,"achievement_"+name) for name in names}
            stats["pets"]=self.value(conn,"pets")
            stats["exams"]=self.value(conn,"exams_highwater")
            return stats

    def counts(self):
        with self.db() as conn:
            # Frozen Nextion diagnostics retain the former response shape.
            return self.value(conn,"pets"),(0,0,0)
