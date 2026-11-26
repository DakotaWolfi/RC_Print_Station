"""Backend for the v0.5 native Nextion candidate; legacy nextion_ui is unchanged.

The panel renders and edits locally. The host handles reports, printing,
LAN downloads and operator-requested settings. It never flashes the display.
"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import json
import logging
import sqlite3
import signal
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from station import database, receipt, send, simulate
from benning_csv import outcome
from benning_panel import TesterPanel
from benning_receiver import MODES, Receiver
from benning_store import Measurements, SOURCES
from station_panel_settings import PanelSettings
from station_network import NetworkManager

END = b"\xff\xff\xff"
ENCODING = "iso-8859-15"
PROTOCOL = 5
LOG = logging.getLogger(__name__)


class FrameDecoder:
    """Reassemble arbitrary UART chunks without growing forever on noise."""
    def __init__(self, limit=2048):
        self.buffer = bytearray()
        self.limit = limit

    def feed(self, chunk):
        self.buffer.extend(chunk)
        frames = []
        while END in self.buffer:
            frame, _, tail = self.buffer.partition(END)
            self.buffer = bytearray(tail)
            if len(frame) <= self.limit:
                frames.append(bytes(frame))
            else:
                LOG.warning("Discarded oversized serial frame")
        if len(self.buffer) > self.limit:
            self.buffer.clear()
            LOG.warning("Discarded unterminated serial noise")
        return frames


def display_text(value, limit):
    """Bounded single-line text; preserve quotes and backslashes as data.

    U+00FF is excluded because its wire byte is the packet delimiter. The
    native keyboard does not offer it. Stored originals remain untouched.
    """
    value = "".join(c if c.isprintable() and c != "ÿ" else " " for c in str(value))
    return value.encode(ENCODING, "replace")[:limit].decode(ENCODING)


def quoted(value, limit):
    value = display_text(value, limit)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def report_base(value):
    value = value.rstrip("/")
    parts = urlsplit(value)
    if (parts.scheme not in ("http", "https") or not parts.hostname or
            parts.username or parts.password or parts.query or parts.fragment or parts.path or
            any(ord(c) < 33 or c in '\\"' for c in value)):
        raise ValueError("--report-url must be an HTTP(S) LAN URL without credentials, query or fragment")
    try:
        value.encode("ascii")
        parts.port
    except (UnicodeError, ValueError) as exc:
        raise ValueError("--report-url must use an ASCII hostname and a valid port") from exc
    # A larger QR buffer exceeds the Basic panel's 3584-byte RAM budget.
    # publish() appends /r/ and a 24-character token; the buffer is 78.
    if len(value) + 27 > 78:
        raise ValueError("--report-url is too long for the display's QR buffer")
    return value


def verify_panel(ser, timeout=3):
    """Read-only identity/protocol handshake before updating any UI variables."""
    decoder = FrameDecoder()

    def query(command, accept):
        ser.write(command + END)
        ser.flush()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in decoder.feed(ser.read(ser.in_waiting or 1)):
                if accept(frame):
                    return frame
                if frame[:1] == b"\x1a":
                    raise RuntimeError("The panel is running a different HMI. Keep the legacy backend for it.")
        raise RuntimeError("No matching Nextion response. Check UART baud, wiring and the flashed HMI.")

    ser.reset_input_buffer()
    ser.write(END)
    identity = query(b"connect", lambda f: b"comok" in f)
    if b"NX8048T070_011R" not in identity:
        raise RuntimeError("Expected Nextion Basic NX8048T070_011R; received a different model.")
    response = query(b"get home.proto.val", lambda f: len(f) == 5 and f[0] == 0x71)
    if int.from_bytes(response[1:], "little") != PROTOCOL:
        raise RuntimeError("Native HMI protocol mismatch; candidate backend was not started.")


class NativeUI:
    def __init__(self, ser, host, db, printer_port=9100, base_url="", *,
                 sender=send, publisher=None, config_path=None, network=None,
                 enable_power=False, tester_mode="auto", tester_device=None, tester_rs232=None,
                 tester_encoding="auto", tester_idle=1.8, tester_receiver=None,
                 hmi_port=None, **settings_hooks):
        self.ser, self.host, self.db = ser, host, db
        self.printer_port = printer_port
        self.base_url = report_base(base_url) if base_url else ""
        self.sender = sender
        if publisher is None:
            from report_web import publish
            publisher = publish
        self.publisher = publisher
        self.decoder = FrameDecoder()
        self.report = None
        self.report_id = None
        self.history = []
        self.urls = {}
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="receipt")
        self.print_job = None
        self.last_heartbeat = float("-inf")
        self.last_clock = ""
        self.stop_requested = False
        self.auto_port = None
        self.measurements=Measurements(db)
        self.receiver=tester_receiver or Receiver(self.measurements,tester_mode,tester_device,
                                                 tester_rs232,tester_encoding,tester_idle,hmi_port)
        self.tester=TesterPanel(self,self.measurements,self.receiver)
        self.settings = PanelSettings(self,network,config_path,enable_power,**settings_hooks)

    def cmd(self, command):
        # Commands and text come from our fixed schema, never raw HMI input.
        data = command.encode(ENCODING, "strict")
        if END in data:
            raise ValueError("A command contains the serial terminator")
        self.ser.write(data + END)

    def text(self, component, value, limit):
        self.cmd(f"{component}.txt={quoted(value, limit)}")

    def initialise(self):
        self.cmd("bkcmd=3")
        self.cmd("sendxy=0")
        self.settings.page = None
        self.settings.selected = None
        self.settings.joined = False
        self.settings.armed_until = 0
        self.settings.apply_display(force=True)
        self.cmd("sendme")
        self.cmd("entry.busy.val=0")
        self.cmd(f"entry.sim.val={int(self.tester.mode=='simulation')}")
        try:
            self.tester.start_draft()
        except sqlite3.Error:
            self.text("entry.tTester","BENNING-Datenbank gerade nicht verfügbar.",92)
        self.cmd("report.printing.val=0")
        self.cmd("home.pending.val=0")
        self.cmd("history.pending.val=0")
        # A restarted host must not offer printing for an HMI-only old report.
        self.cmd("report.ready.val=0")
        self.cmd("qrpage.qReady.val=2")
        self.text("qrpage.tNote", "Bitte Bericht erneut im Verlauf öffnen.", 100)
        self.text("entry.tStatus", "Host verbunden. Eingaben bleiben erhalten.", 80)
        self.text("report.tStatus", "Host verbunden. Bericht bitte im Verlauf öffnen.", 80)
        self.text("home.tHint", "Simulation aktiv." if self.tester.mode=="simulation" else "BENNING: Messung speichern und Export auslösen.", 64)
        self.heartbeat(force=True)
        self.ser.flush()

    def heartbeat(self, force=False):
        now = time.monotonic()
        if force or now - self.last_heartbeat >= 2:
            self.cmd("home.age.val=0")
            self.cmd("home.online.val=1")
            self.text("home.tLink", "Host verbunden", 32)
            stamp = datetime.now(ZoneInfo("Europe/Zurich")).strftime("%d.%m.%Y  %H:%M")
            if force or stamp != self.last_clock:
                self.text("home.tClock", stamp, 24)
                self.last_clock = stamp
            self.last_heartbeat = now

    def load_report(self, ident, report):
        if not isinstance(report,dict) or report.get("source") not in ("SIMULATOR","BENNING"):
            raise ValueError("Ungültiger gespeicherter Bericht.")
        simulated = report["source"]=="SIMULATOR"
        record = report.get("record")
        if (simulated and report.get("verdict")!="NOT TESTED") or (
                not simulated and (not isinstance(record,dict) or outcome(record.get("verdict","")) is None)):
            raise ValueError("Ungültiges gespeichertes Prüfergebnis.")
        if not isinstance(report.get("ticket"), str) or not isinstance(report.get("device"), str):
            raise ValueError("Ungültiger gespeicherter Bericht.")
        self.cmd("report.ready.val=0")
        self.text("report.tTicket", report["ticket"], 32)
        self.text("report.tDevice", report["device"], 64)
        try:
            stamp = datetime.fromisoformat(report["created"]).astimezone(ZoneInfo("Europe/Zurich"))
            date = stamp.strftime("%d.%m.%Y  %H:%M")
        except (KeyError, ValueError, TypeError):
            date = "Datum unbekannt"
        if simulated:
            self.text("report.tOrigin","SIMULATION / KEINE ELEKTRISCHE PRÜFUNG",45)
            self.text("report.tResult","NICHT GEPRÜFT",40)
            self.text("report.tMeta","",64)
            self.text("qrpage.tKind","SIMULATION / keine elektrische Prüfung",56)
            self.text("report.tStatus","Keine Messwerte. Kein Sicherheitsnachweis.",80)
        else:
            date=record["tester_date"]
            origin=SOURCES[report["import_source"]]
            self.text("report.tOrigin",origin,45)
            self.text("report.tResult",f'Tester: {record["verdict"]}',40)
            self.text("report.tMeta",f'Slot {record["slot"]} / {report["phase"]} / {record["protection_class"] or "-"}',64)
            self.text("qrpage.tKind","BENNING-Import / Originalergebnis",56)
            self.text("report.tStatus","Testergebnis übernommen. Keine Freigabe durch FMI.",80)
        self.text("report.tDate", date, 24)
        self.cmd("report.printing.val=0")
        self.report, self.report_id = report, ident
        # The native page's timer changes page only after the complete data.
        self.cmd("report.ready.val=1")

    def create(self, payload):
        fields = payload.split(b"\x00")
        if len(fields) != 3 or len(fields[1]) > 32 or len(fields[2]) > 64:
            raise ValueError("Ungültige Eingabe; bitte erneut eingeben.")
        ticket, device = (s.decode(ENCODING).strip() for s in fields[1:])
        if not ticket or not device or any(not c.isprintable() for c in ticket + device):
            raise ValueError("Bitte beide Felder ausfüllen.")
        report = simulate(ticket, device)
        with database(self.db) as db:
            ident = db.execute("INSERT INTO reports(data) VALUES (?)", (json.dumps(report),)).lastrowid
        self.load_report(ident, report)

    def refresh_history(self):
        with database(self.db) as db:
            self.history = db.execute("SELECT id,data FROM reports ORDER BY id DESC LIMIT 5").fetchall()
        for i in range(5):
            label = "Keine weiteren Protokolle"
            if i < len(self.history):
                ident, data = self.history[i]
                r = json.loads(data)
                if not isinstance(r,dict):
                    raise ValueError("Ungültiger gespeicherter Bericht.")
                label = f"#{ident}  {r.get('ticket', '?')}"
            self.text(f"history.bRow{i}", label, 40)
        self.text("history.tStatus", "Gespeicherte BENNING-Berichte und Simulationen", 80)

    def last_report(self):
        with database(self.db) as db:
            row = db.execute("SELECT id,data FROM reports ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            self.text("home.tHint", "Noch keine Protokolle gespeichert.", 64)
            self.cmd("home.pending.val=0")
            return
        self.load_report(row[0], json.loads(row[1]))

    def open_report(self, index):
        if index >= len(self.history):
            self.text("history.tStatus", "Dieser Eintrag ist leer.", 80)
            self.cmd("history.pending.val=0")
            return
        ident, data = self.history[index]
        self.load_report(ident, json.loads(data))

    def print_report(self):
        if self.print_job is not None:
            self.text("report.tStatus", "Ein Druckauftrag läuft bereits.", 80)
            return
        if self.report is None:
            raise ValueError("Bitte zuerst einen Bericht öffnen.")
        self.queue_receipt(self.report,self.report_id)

    def queue_receipt(self, report, ident):
        settings = self.settings.cfg()
        data = receipt(report,settings)
        future = self.executor.submit(self.sender,*self.settings.endpoint(settings),data)
        self.print_job = (future,ident)

    def queue_print_test(self):
        if self.print_job is not None:
            self.settings.printer_note="Ein Druckauftrag läuft bereits."
            return
        self.settings.printer_note="Testbeleg wird gesendet ..."
        self.queue_receipt(simulate("DRUCKTEST","Epson / ESC-POS Verbindungstest"),"test")

    def finish_print(self):
        if self.print_job is None or not self.print_job[0].done():
            return
        future, ident = self.print_job
        self.print_job = None
        try:
            future.result()
            status = "Druckdaten gesendet. Bitte Beleg prüfen."
        except OSError:
            LOG.exception("Printer submission failed")
            status = "Druckfehler. Beleg prüfen, dann ggf. erneut drucken."
        if ident == "test":
            self.settings.printer_note=status
            self.settings.draw()
        elif ident == self.report_id:
            self.text("report.tStatus", status, 80)
            self.cmd("report.printing.val=0")
        else:
            self.text("home.tHint", status, 64)

    def show_qr(self):
        if not self.base_url:
            self.text("qrpage.tNote", "PDF aus: Host mit --report-url und erreichbarer LAN-Adresse starten.", 100)
            self.cmd("qrpage.qReady.val=2")
            return
        if self.report is None:
            raise ValueError("Bitte zuerst einen Bericht öffnen.")
        if self.report_id not in self.urls:
            self.urls[self.report_id] = self.publisher(self.db, self.report, self.base_url)
        url = self.urls[self.report_id]
        if len(url.encode(ENCODING)) > 78:
            raise ValueError("PDF-Link ist zu lang für den QR-Code.")
        self.text("qrpage.qrReport", url, 78)
        self.text("qrpage.tNote", "Mit dem Handy scannen. Handy und Station müssen im selben Netz sein.", 100)
        self.cmd("qrpage.qReady.val=1")

    def error(self, message):
        # Release all pending native transitions; inputs are not erased.
        for field, limit in (("entry.tStatus",80),("report.tStatus",80),
                             ("history.tStatus",80),("home.tHint",64),("qrpage.tNote",100)):
            self.text(field, message, limit)
        for field in ("entry.busy", "home.pending", "history.pending"):
            self.cmd(field + ".val=0")
        if self.print_job is None:
            self.cmd("report.printing.val=0")
        self.cmd("qrpage.qReady.val=2")

    def handle(self, frame):
        if len(frame)==2 and frame[0]==0x66:
            self.settings.enter(frame[1])
            self.tester.enter()
            return
        if frame.startswith(b"RC5:"):
            self.tester.handle(frame)
            return
        if frame.startswith(b"RC4:"):
            self.settings.handle(frame)
            return
        if not frame.startswith(b"RC3:"):
            if len(frame) == 1 and frame[0] not in (0x00,0x01,0x86,0x87,0x88):
                LOG.warning("Nextion response: 0x%02x", frame[0])
            return
        try:
            if frame == b"RC3:BOOT":
                self.initialise()
            elif frame.startswith(b"RC3:CREATE\x00"):
                if self.tester.mode!="simulation":
                    raise ValueError("Simulation muss explizit aktiviert sein.")
                self.create(frame)
            elif frame == b"RC3:HISTORY":
                self.refresh_history()
            elif frame == b"RC3:LAST":
                self.last_report()
            elif frame.startswith(b"RC3:OPEN:") and frame[9:] in [bytes([i]) for i in range(48,53)]:
                self.open_report(int(frame[9:]))
            elif frame == b"RC3:PRINT":
                self.print_report()
            elif frame == b"RC3:QR":
                self.show_qr()
            else:
                LOG.warning("Ignored unknown native event")
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error) as exc:
            LOG.exception("Native action failed")
            self.error(str(exc) if isinstance(exc,ValueError) else "Aktion fehlgeschlagen. Host-Protokoll prüfen.")

    def feed(self, chunk):
        for frame in self.decoder.feed(chunk):
            self.handle(frame)

    def tick(self):
        self.finish_print()
        self.heartbeat()
        self.settings.poll()
        self.tester.poll()
        self.ser.flush()

    def close(self):
        # Never cancel/retry a receipt whose bytes may already have arrived.
        self.executor.shutdown(wait=True)
        self.settings.close()
        self.receiver.close()

    def run(self):
        self.initialise()
        self.receiver.start()
        try:
            while not self.stop_requested:
                self.feed(self.ser.read(self.ser.in_waiting or 1))
                self.tick()
        finally:
            self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="/dev/serial0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--host", default="169.254.223.252")
    parser.add_argument("--printer-port", type=int, default=9100)
    parser.add_argument("--db", default="reports.sqlite3")
    parser.add_argument("--report-url", default="", help="Reachable LAN origin, e.g. http://192.168.1.42:8080")
    parser.add_argument("--web-port", type=int, default=8080)
    parser.add_argument("--auto-report-url", action="store_true", help="Use wlan0 IPv4 for QR URLs")
    parser.add_argument("--wifi-interface", default="wlan0")
    parser.add_argument("--enable-local-power", action="store_true", help="Allow confirmed panel reboot/shutdown via logind")
    parser.add_argument("--tester-mode",choices=MODES,default=os.environ.get("FMI_TESTER_MODE","auto"))
    parser.add_argument("--tester-device",default=os.environ.get("FMI_TESTER_DEVICE"))
    parser.add_argument("--tester-rs232-device",default=os.environ.get("FMI_TESTER_RS232_DEVICE"))
    parser.add_argument("--tester-encoding",default=os.environ.get("FMI_TESTER_ENCODING","auto"))
    parser.add_argument("--tester-idle",type=float,default=os.environ.get("FMI_TESTER_IDLE","1.8"))
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO)
    if args.report_url:
        try:
            args.report_url = report_base(args.report_url)
        except ValueError as exc:
            parser.error(str(exc))
    import serial
    with serial.Serial(args.port, args.baud, timeout=.1, write_timeout=3, exclusive=True) as ser:
        verify_panel(ser)
        server = None
        if args.report_url or args.auto_report_url:
            from report_web import start_server
            server = start_server(args.db, args.web_port)
        ui = NativeUI(ser,args.host,args.db,args.printer_port,args.report_url,
                      network=NetworkManager(args.wifi_interface),enable_power=args.enable_local_power,
                      tester_mode=args.tester_mode,tester_device=args.tester_device,
                      tester_rs232=args.tester_rs232_device,tester_encoding=args.tester_encoding,
                      tester_idle=args.tester_idle,hmi_port=args.port)
        if args.auto_report_url:
            ui.auto_port = args.web_port
        signal.signal(signal.SIGTERM,lambda *_: setattr(ui,"stop_requested",True))
        try:
            ui.run()
        except KeyboardInterrupt:
            LOG.info("Native backend stopped")
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
