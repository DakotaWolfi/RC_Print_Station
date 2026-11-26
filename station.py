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
import base64
import zlib
from station_config import load as receipt_settings, DENSITIES
from benning_output import measurement_state, selected_fields, show_value
from benning_store import SOURCES

def simulate(ticket, device):
    return {"ticket": ticket, "device": device, "source": "SIMULATOR",
            "created": datetime.now(timezone.utc).isoformat(),
            "measurements": [], "verdict": "NOT TESTED"}

# Generated monochrome receipt artwork, 504 x 168, packed MSB-first.
HEADER_DATA = "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"

def graphic_header():
    data = zlib.decompress(base64.b64decode(HEADER_DATA))
    if len(data) != 63 * 168:
        raise ValueError("Invalid receipt header")
    return b"\x1d\x76\x30\x00\x3f\x00\xa8\x00" + data + b"\n"

def receipt(report, settings=None):
    """80 mm ESC/POS demo receipt, 42 columns, PC850."""
    def clean(value):
        # PC850 has no euro glyph; keep the new native keyboard's € legible.
        value = str(value).replace("€", "EUR").replace("≤","<=").replace("≥",">=")
        return "".join(c if c.isprintable() else " " for c in value)
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
    heavy=line("="*42)
    # Epson 203 dpi: 120 dots ~= 15 mm. Keep the proven 240-dot feed.
    settings=receipt_settings() if settings is None else settings
    m=DENSITIES[settings.get("density","default")]
    density=b"" if m is None else b"\x1d(K\x02\x001"+bytes([m])
    dots=round(settings["feed_mm"]*8)
    chunks=[]
    while dots:
        step=min(240,dots)
        chunks.append(b"\x1bJ"+bytes([step]))
        dots-=step
    feed_and_cut=b"".join(chunks)+b"\x1dV\x00"
    header=graphic_header() if settings["graphic"] else bold+b"\x1d!\x11"+line("REPAIR CAFÉ")+b"\x1d!\x00"+line("RIEHEN")+normal
    prefix=b"\x1b@"+density+b"\x1bt\x02"+center+header+normal
    if report.get("source")=="BENNING":
        data=[prefix,bold,line("BENNING ST 725"),normal,line(SOURCES[report["import_source"]]),heavy,left]
        data.extend(field(key,value) for key,value in selected_fields(report))
        data.extend((rule,bold,field("Originales Testergebnis",report["record"]["verdict"]),normal,rule))
        for item in report["measurements"]:
            state,_=measurement_state(item)
            label=item["name"]+(" / "+item["test"] if item.get("test") else "")
            value=show_value(item.get("value"),item.get("unit")).replace("Ω","Ohm")
            limit=show_value(item.get("limit"),item.get("limit_unit")).replace("Ω","Ohm")
            data.extend((field(label,value),field(" Grenzwert",limit),field(" Tester",state)))
        data.extend((heavy,field("Hinweis","Importiertes Testergebnis. Keine Sicherheitsfreigabe durch FMI."),
                     center,bold,line("FMI Printstation"),normal,left,feed_and_cut))
        return b"".join(data)
    return (prefix+
            line("Reparieren statt wegwerfen.")+heavy+
            bold+line("ELEKTRISCHES PRÜFPROTOKOLL")+normal+line()+bold+
            line("DEMO / SIMULATION ONLY")+line("KEINE ELEKTRISCHE PRÜFUNG")+normal+
            rule+left+field("Datum",stamp)+line()+bold+line("REPARATURDATEN")+normal+
            field("Ticket",report["ticket"])+field("Gerät",report["device"])+line()+rule+
            bold+line("PRÜFERGEBNIS")+
            line("NICHT GEPRÜFT / NOT TESTED")+normal+
            line("Keine Messwerte vorhanden.")+line()+heavy+center+
            bold+line("FMI Printstation")+normal+line("Repair Café Riehen | Entwicklung")+left+feed_and_cut)

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
