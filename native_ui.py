"""Backend for the v0.7.1 native Nextion display.

The panel renders and edits locally. The host handles reports, printing,
LAN downloads and operator-requested settings. It never flashes the display.
"""
import argparse
import os
from pathlib import Path
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
from benning_output import (RESULTS, date_format, measurement_summary, protection_class,
                            report_checks, report_timestamp, result_kind, tester_date,
                            verdict_text, visible_measurements, voltage_text)
from benning_workflow import WorkflowPanel
from operator_panel import Picker
from personality import PROTOCOL, VERSION, Personality
from slogan_store import CACHE
from panel_text import fit, paginate, quote
from benning_panel import TesterPanel
from benning_receiver import MODES, Receiver
from benning_store import Measurements, SOURCES
from station_panel_settings import PanelSettings
from station_network import NetworkManager
from i18n import tr
from station_config import PRINTER_HOST, PRINTER_PORT, save

END = b"\xff\xff\xff"
ENCODING = "iso-8859-15"
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


def panel_colour(colour):
    rgb=int(colour[1:],16)
    return ((rgb>>19)<<11)|(((rgb>>10)&63)<<5)|((rgb>>3)&31)


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
    def __init__(self, ser, host, db, printer_port=PRINTER_PORT, base_url="", *,
                 sender=send, publisher=None, config_path=None, network=None,
                 enable_power=False, tester_mode="auto", tester_device=None, tester_rs232=None,
                 tester_encoding="auto", tester_idle=1.8, tester_receiver=None,
                 hmi_port=None, personality_cache=None, **settings_hooks):
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
        self.language = self.settings.cfg()["language"]
        self.workflow=WorkflowPanel(self)
        self.picker=Picker(self)
        self.detail_page=0
        self.measurement_offset=0
        self.measurement_preview_pending=False
        self.language_route=None
        self.language_ack=None
        self.personality=Personality(self,db,personality_cache or Path(db).with_suffix(".slogans.sqlite3"),
                                     eggs=os.environ.get("FMI_EASTER_EGGS","1")!="0")

    def cmd(self, command):
        # Commands and text come from our fixed schema, never raw HMI input.
        data = command.encode(ENCODING, "strict")
        if END in data:
            raise ValueError("A command contains the serial terminator")
        self.ser.write(data + END)

    def text(self, component, value, limit):
        self.cmd(f"{component}.txt={quote(fit(self.settings.page,component,value,limit))}")

    def tr(self, message, **values):
        return tr(self.language,message,**values)

    def say(self, component, message, limit, **values):
        self.text(component,self.tr(message,**values),limit)

    def expect_language_ack(self, kind, expected):
        self.language_ack=(kind,expected,time.monotonic()+3)

    def handle_language(self, frame):
        station=frame==b"RC70:LANG"
        kind="station" if station else "report"
        expected="home" if station else "entry"
        if self.settings.page!=expected:
            LOG.warning("Language event %s needs page resync (tracked=%s, expected=%s)",
                        kind,self.settings.page,expected)
            self.language_route=(frame,expected,time.monotonic()+2)
            self.cmd("sendme")
            return
        LOG.info("Language event %s received on %s",kind,expected)
        if not station:
            self.workflow.switch_report_language()
            expected_label=self.tr("Bericht: {language}",language=self.workflow.report_language.upper())
            self.expect_language_ack(kind,expected_label)
            self.cmd("get bReportLang.txt")
            LOG.info("Report language selected: %s",self.workflow.report_language)
            return

        target="de" if self.language=="en" else "en"
        try:
            save({"language":target},self.settings.path)
        except (OSError,ValueError) as exc:
            LOG.warning("Station language persistence failed (%s)",type(exc).__name__)
            self.say("home.tHint","Stationssprache konnte nicht gespeichert werden.",64)
            return
        self.language=target
        self.expect_language_ack(kind,target)
        self.cmd(f"home.lang.val={int(target=='en')}")
        # The home firmware refreshes its own component IDs. Navigating
        # during the write does not send a click to a different page.
        self.home_hint()
        self.heartbeat(force=True)
        LOG.info("Station language persisted: %s",target)

    def acknowledge_language(self, kind, value):
        if self.language_ack is None or self.language_ack[0]!=kind:
            return
        _,expected,_=self.language_ack
        self.language_ack=None
        if expected==value:
            LOG.info("Panel confirmed %s language render",kind)
        else:
            LOG.warning("Panel %s language render differs from saved selection",kind)

    def check_language_timeouts(self):
        now=time.monotonic()
        if self.language_route and now>=self.language_route[2]:
            self.language_route=None
            LOG.warning("Language request dropped because panel page was unconfirmed")
        if self.language_ack and now>=self.language_ack[2]:
            kind=self.language_ack[0]
            self.language_ack=None
            LOG.warning("Panel did not acknowledge %s language render",kind)

    def home_hint(self):
        self.say("home.tHint","Simulation aktiv." if self.tester.mode=="simulation"
                 else "BENNING: Messung speichern und Export auslösen.",64)

    def report_details(self,report):
        return paginate("report.tDetails",(f"{self.tr(key)}: {value}"
                        for key,value in report_checks(report,self.language)))

    def initialise(self):
        self.cmd("bkcmd=3")
        self.cmd("sendxy=0")
        self.cmd(f"home.lang.val={int(self.language=='en')}")
        LOG.info("Printstation v%s, native HMI protocol %s, saved station language %s",VERSION,PROTOCOL,self.language)
        self.workflow.reset()
        self.picker.reset()
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
            self.say("entry.tTester","BENNING-Datenbank gerade nicht verfügbar.",92)
        self.cmd("report.printing.val=0")
        self.cmd("home.pending.val=0")
        self.cmd("history.pending.val=0")
        # A restarted host must not offer printing for an HMI-only old report.
        self.cmd("report.ready.val=0")
        self.cmd("qrpage.qReady.val=2")
        self.say("qrpage.tNote","Bitte Bericht erneut im Verlauf öffnen.",100)
        self.say("entry.tStatus","Host verbunden. Eingaben bleiben erhalten.",80)
        self.say("report.tStatus","Host verbunden. Bericht bitte im Verlauf öffnen.",80)
        self.say("home.tHint","Simulation aktiv." if self.tester.mode=="simulation" else "BENNING: Messung speichern und Export auslösen.",64)
        self.heartbeat(force=True)
        self.ser.flush()

    def heartbeat(self, force=False):
        now = time.monotonic()
        if force or now - self.last_heartbeat >= 2:
            self.cmd("home.age.val=0")
            self.cmd("home.online.val=1")
            self.say("home.tLink","Host verbunden",32)
            stamp = datetime.now(ZoneInfo("Europe/Zurich")).strftime(date_format(self.language)+"  %H:%M")
            if force or stamp != self.last_clock:
                self.text("home.tClock", stamp, 24)
                self.last_clock = stamp
            self.last_heartbeat = now

    def draw_measurements(self,report):
        self.cmd(f"vis tDetails,{int(bool(self.detail_page))}")
        for i in range(3):
            self.cmd(f"vis tValue{i},{int(not self.detail_page)}")
        if self.detail_page:
            pages=self.report_details(report)
            self.text("tDetails",pages[self.detail_page-1],255)
            self.say("bInfo","Messwerte",14)
            self.say("bValues","Weitere Angaben",18)
            self.cmd(f"vMore.val={int(len(pages)>1)}")
            self.cmd(f"vis bValues,{int(len(pages)>1)}")
            return
        self.say("bInfo","Prüfdetails",14)
        self.say("bValues","Weitere Werte",18)
        rows=visible_measurements(report)
        csv_source=report.get("import_source") in ("usb","file-csv")
        for i in range(3):
            component=f"tValue{i}"
            label,colour="",RESULTS["unknown"][1]
            index=self.measurement_offset+i
            if index<len(rows):
                name,value,limit,state,kind=measurement_summary(rows[index],csv_source=csv_source,language=self.language)
                label="  ·  ".join(filter(None,(name,value,state,self.tr("Grenze {limit}",limit=limit) if limit else "")))
                colour=RESULTS[kind][1]
            self.text(component,label,94)
            self.cmd(f"{component}.pco={panel_colour(colour)}")
        self.cmd(f"vMore.val={int(len(rows)>3)}")
        self.cmd(f"vis bValues,{int(len(rows)>3)}")

    def load_report(self, ident, report):
        if not isinstance(report,dict) or report.get("source") not in ("SIMULATOR","BENNING","EXAMINATION"):
            raise ValueError("Ungültiger gespeicherter Bericht.")
        source=report["source"]
        record=report.get("record") or {}
        if source=="BENNING" and not isinstance(report.get("record"),dict):
            raise ValueError("Ungültiges gespeichertes Prüfergebnis.")
        if source=="SIMULATOR" and report.get("verdict")!="NOT TESTED":
            raise ValueError("Ungültiges gespeichertes Prüfergebnis.")
        if not isinstance(report.get("ticket"),str) or not isinstance(report.get("device"),str):
            raise ValueError("Ungültiger gespeicherter Bericht.")
        status=result_kind(report)
        label,colour,_,_=RESULTS[status]
        self.cmd("report.ready.val=0")
        self.text("report.tTicket",report["ticket"],32)
        self.text("report.tDevice",report["device"],64)
        self.say("report.tResult",label,40)
        self.cmd(f"report.tResult.pco={panel_colour(colour)}")
        meta=" / ".join(filter(None,(f'Slot {record["slot"]}' if record.get("slot") else "",
                                  self.tr(report.get("phase","")),protection_class(record.get("protection_class"),self.language))))
        self.text("report.tMeta",meta,69)
        date=" · ".join(filter(None,(tester_date(record,self.language),voltage_text(record.get("voltage"))))) if record else report_timestamp(report,self.language)
        if source=="BENNING":
            origin=self.tr("Tester-Original: {verdict}",verdict=verdict_text(record.get("verdict"),self.language) or self.tr("Unbekannt"))
            note="Messwerte und Prüfergebnis vom BENNING ST 725 übernommen."
            protocol=dict(report_checks(report,self.language))["Protokoll"]
            if protocol!=self.tr("Dokumentiert"):
                note=self.tr("Protokoll offen: {reasons}",reasons=protocol.partition(": ")[2])
            qr="BENNING-Import / Originalergebnis"
        elif source=="EXAMINATION":
            origin="Kein Testergebnis übernommen"
            note="Protokoll offen: BENNING-Messung fehlt."
            qr="UNVOLLSTÄNDIGE PRÜFUNG"
        else:
            origin="KEINE ELEKTRISCHE PRÜFUNG"
            note="Keine Messwerte. Kein Sicherheitsnachweis."
            qr="SIMULATION / keine elektrische Prüfung"
        self.say("report.tOrigin",origin,55)
        self.say("report.tStatus",note,90)
        self.text("report.tDate",date,42)
        self.say("qrpage.tKind",qr,56)
        self.measurement_offset=0
        self.detail_page=0
        self.cmd("report.printing.val=0")
        self.report,self.report_id=report,ident
        self.cmd("report.ready.val=1")

    def create(self, payload):
        fields = payload.split(b"\x00")
        if len(fields) != 3 or len(fields[1]) > 32 or len(fields[2]) > 64:
            raise ValueError("Ungültige Eingabe; bitte erneut eingeben.")
        ticket, device = (s.decode(ENCODING) for s in fields[1:])
        if not ticket.strip() or not device.strip() or any(not c.isprintable() for c in ticket + device):
            raise ValueError("Bitte beide Felder ausfüllen.")
        report = simulate(ticket, device,language=self.workflow.report_language)
        with database(self.db) as db:
            ident = db.execute("INSERT INTO reports(data) VALUES (?)", (json.dumps(report),)).lastrowid
        self.finish_draft(ident, report)

    def finish_draft(self, ident, report):
        self.cmd("entry.inProgress.val=0")
        self.personality.stats_dirty=True
        self.workflow.guide=None
        self.load_report(ident,report)

    def refresh_history(self):
        with database(self.db) as db:
            self.history = db.execute("SELECT id,data FROM reports ORDER BY id DESC LIMIT 5").fetchall()
        for i in range(5):
            label = self.tr("Keine weiteren Protokolle")
            if i < len(self.history):
                ident, data = self.history[i]
                r = json.loads(data)
                if not isinstance(r,dict):
                    raise ValueError("Ungültiger gespeicherter Bericht.")
                label = f"#{ident}  {r.get('ticket', '?')}"
            self.text(f"history.bRow{i}", label, 40)
        self.say("history.tStatus","Gespeicherte BENNING-Berichte und Simulationen",80)

    def last_report(self):
        with database(self.db) as db:
            row = db.execute("SELECT id,data FROM reports ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            self.say("home.tHint","Noch keine Protokolle gespeichert.",64)
            self.cmd("home.pending.val=0")
            return
        self.load_report(row[0], json.loads(row[1]))

    def open_report(self, index):
        if index >= len(self.history):
            self.say("history.tStatus","Dieser Eintrag ist leer.",80)
            self.cmd("history.pending.val=0")
            return
        ident, data = self.history[index]
        self.load_report(ident, json.loads(data))

    def print_report(self):
        if self.print_job is not None:
            self.say("report.tStatus","Ein Druckauftrag läuft bereits.",80)
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
        self.queue_receipt(simulate(self.tr("DRUCKTEST"),self.tr("Epson / ESC-POS Verbindungstest"),language=self.language),"test")

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
            self.say("report.tStatus", status, 80)
            self.cmd("report.printing.val=0")
        else:
            self.say("home.tHint", status, 64)

    def show_qr(self):
        if not self.base_url:
            self.say("qrpage.tNote","PDF aus: Host mit --report-url und erreichbarer LAN-Adresse starten.",100)
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
        self.say("qrpage.tNote","Mit dem Handy scannen. Handy und Station müssen im selben Netz sein.",100)
        self.cmd("qrpage.qReady.val=1")

    def error(self, message):
        # Release all pending native transitions; inputs are not erased.
        for field, limit in (("entry.tStatus",80),("report.tStatus",80),
                             ("history.tStatus",80),("home.tHint",64),("qrpage.tNote",100)):
            self.say(field, message, limit)
        for field in ("entry.busy", "home.pending", "history.pending"):
            self.cmd(field + ".val=0")
        if self.print_job is None:
            self.cmd("report.printing.val=0")
        self.cmd("qrpage.qReady.val=2")

    def handle(self, frame):
        if len(frame)==2 and frame[0]==0x66:
            self.settings.enter(frame[1])
            self.tester.enter()
            self.workflow.enter()
            self.picker.enter()
            self.personality.enter()
            self.measurement_preview_pending=self.settings.page=="report"
            if self.language_route:
                pending,page,deadline=self.language_route
                self.language_route=None
                if self.settings.page==page and time.monotonic()<deadline:
                    self.handle_language(pending)
                else:
                    LOG.warning("Language request rejected after page resync (%s)",self.settings.page)
            return
        if frame in (b"RC70:LANG",b"RC70:REPORTLANG"):
            self.handle_language(frame)
            return
        if frame in (b"RC71:LOCALE:DE",b"RC71:LOCALE:EN"):
            self.acknowledge_language("station",frame[-2:].decode().lower())
            self.personality.redraw_home=True
            return
        if frame.startswith(b"\x70") and self.language_ack and self.language_ack[0]=="report":
            self.acknowledge_language("report",frame[1:].decode(ENCODING))
            return
        if frame in (b"RC71:LOGO",b"RC71:ENGINEER",b"RC71:PET"):
            self.personality.event(frame)
            return
        if frame==b"RC61:DETAILS" and self.settings.page=="report" and self.report:
            self.detail_page=0 if self.detail_page else 1
            self.measurement_preview_pending=True
            return
        if frame.startswith(b"RC61:"):
            self.picker.handle(frame)
            return
        if frame==b"RC6:VALUES" and self.settings.page=="report" and self.report:
            if self.detail_page:
                pages=self.report_details(self.report)
                self.detail_page=self.detail_page%len(pages)+1
            else:
                self.measurement_offset+=3
                if self.measurement_offset>=len(visible_measurements(self.report)):
                    self.measurement_offset=0
            self.measurement_preview_pending=True
            return
        if frame.startswith(b"RC6:"):
            self.workflow.handle(frame)
            return
        if frame.startswith(b"RC5:"):
            self.tester.handle(frame)
            return
        if frame.startswith(b"RC4:"):
            self.settings.handle(frame)
            return
        if not frame.startswith(b"RC3:"):
            if len(frame) == 1 and frame[0] not in (0x00,0x01,0x86,0x87,0x88):
                if self.language_ack:
                    LOG.warning("Nextion response 0x%02x during %s language render (page=%s)",
                                frame[0],self.language_ack[0],self.settings.page)
                else:
                    LOG.warning("Nextion response: 0x%02x",frame[0])
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
        self.check_language_timeouts()
        self.heartbeat()
        self.settings.poll()
        self.tester.poll()
        self.workflow.poll()
        self.personality.tick()
        if self.measurement_preview_pending and self.settings.page=="report" and self.report:
            self.measurement_preview_pending=False
            self.draw_measurements(self.report)
        self.ser.flush()

    def close(self):
        # Never cancel/retry a receipt whose bytes may already have arrived.
        self.executor.shutdown(wait=True)
        self.settings.close()
        self.personality.close()
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
    parser.add_argument("--host", default=PRINTER_HOST)
    parser.add_argument("--printer-port", type=int, default=PRINTER_PORT)
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
                      personality_cache=CACHE,
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
