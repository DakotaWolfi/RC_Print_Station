"""Repair Cafe development CLI; no system configuration changes."""
import argparse
import json
import pathlib
import socket
import sqlite3
import subprocess
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import textwrap

def simulate(ticket, device):
    return {"ticket": ticket, "device": device, "source": "SIMULATOR",
            "created": datetime.now(timezone.utc).isoformat(),
            "measurements": [], "verdict": "NOT TESTED"}

def receipt(report):
    """80 mm ESC/POS demo receipt, 42 columns, PC850."""
    def clean(value):
        return "".join(c if c.isprintable() else " " for c in str(value))
    def line(value=""):
        return (clean(value)+"\n").encode("cp850","replace")
    def field(label,value):
        return b"".join(line(s) for s in textwrap.wrap(label+": "+clean(value),42) or [""])
    try:
        date=datetime.fromisoformat(report["created"]).astimezone(ZoneInfo("Europe/Zurich"))
        stamp=date.strftime("%d.%m.%Y  %H:%M")
    except (ValueError,KeyError):
        stamp=clean(report.get("created","Unbekannt"))
    center=b"\x1ba\x01"
    left=b"\x1ba\x00"
    bold=b"\x1bE\x01"
    normal=b"\x1bE\x00"
    rule=line("-"*42)
    return (b"\x1b@\x1bt\x02"+center+bold+b"\x1d!\x11"+
            line("REPAIR CAFÉ")+b"\x1d!\x00"+line("RIEHEN")+normal+
            line("Elektrisches Prüfprotokoll")+rule+bold+
            line("DEMO / SIMULATION ONLY")+line("KEINE ELEKTRISCHE PRÜFUNG")+normal+
            rule+left+field("Datum",stamp)+field("Ticket",report["ticket"])+
            field("Gerät",report["device"])+rule+bold+line("Prüfergebnis")+
            line("NICHT GEPRÜFT / NOT TESTED")+normal+
            line("Keine Messwerte vorhanden.")+rule+center+
            line("Reparieren statt wegwerfen.")+bold+line("FMI Printstation")+normal+
            left+b"\x1b\x4a\xf0\x1dV\x00")

def send(host, port, data):
    with socket.create_connection((host, port), timeout=5) as conn:
        conn.sendall(data)

def database(path):
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE IF NOT EXISTS reports (id INTEGER PRIMARY KEY, data TEXT NOT NULL)")
    return db

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--db", default="reports.sqlite3")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("diagnose")
    sim = sub.add_parser("simulate")
    sim.add_argument("--ticket", required=True)
    sim.add_argument("--device", required=True)
    sub.add_parser("history")
    pr = sub.add_parser("printer-test")
    pr.add_argument("--host", required=True)
    pr.add_argument("--port", type=int, default=9100)
    display = sub.add_parser("display-test")
    display.add_argument("--port", required=True)
    display.add_argument("--baud", type=int, default=9600)
    a = p.parse_args()
    if a.command == "diagnose":
        for cmd in (["uname", "-a"], ["ip", "-br", "addr"], ["ip", "route"],
                    ["lsusb"], ["systemctl", "--no-pager", "--type=service", "--state=running"]):
            print("$", " ".join(cmd), flush=True)
            try:
                subprocess.run(cmd, check=False, timeout=10)
            except (OSError, subprocess.TimeoutExpired) as exc:
                print(exc)
        print("Serial candidates:", *sorted(str(x) for pattern in ("ttyUSB*", "ttyACM*", "ttyAMA*", "serial*") for x in pathlib.Path("/dev").glob(pattern)))
    elif a.command == "simulate":
        report = simulate(a.ticket, a.device)
        with database(a.db) as db:
            db.execute("INSERT INTO reports(data) VALUES (?)", (json.dumps(report),))
        print(json.dumps(report, indent=2))
    elif a.command == "history":
        with database(a.db) as db:
            for row in db.execute("SELECT id, data FROM reports ORDER BY id DESC"):
                print(row[0], row[1])
    elif a.command == "printer-test":
        send(a.host, a.port, receipt(simulate("DEV-001", "Printer connection test")))
        print("Bytes sent; verify physical receipt.")
    elif a.command == "display-test":
        import serial
        with serial.Serial(a.port, a.baud, timeout=2, write_timeout=2) as ser:
            ser.reset_input_buffer()
            ser.write(b"connect\xff\xff\xff")
            response = ser.read_until(b"\xff\xff\xff", size=512)
            print(repr(response))
            if b"comok" not in response:
                raise SystemExit("No Nextion identification received; check baud and wiring.")
if __name__ == "__main__":
    main()
