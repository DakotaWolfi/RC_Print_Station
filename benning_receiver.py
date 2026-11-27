"""Independent receive-only serial worker and bounded idle-gap framing."""
from dataclasses import dataclass, replace
import os
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
import time

from benning_csv import ImportErrorDetail, MAX_BYTES, validate_encoding
from benning_serial import ONBOARD, PrintReceiver, onboard_reserved

USB_PATH = "/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0"
MODES = ("auto","usb","rs232","file","simulation")


def same_device(left,right):
    if os.path.realpath(left)==os.path.realpath(right):
        return True
    try:
        return os.path.samefile(left,right)
    except OSError:
        return False


def choose_port(mode,usb=None,rs232=None,*,hmi=None,gpio=False,exists=os.path.exists,list_ports=None,reserved=onboard_reserved):
    """Auto mode only uses the known bridge identity or explicitly named ports."""
    if mode not in ("auto","usb","rs232"):
        return None
    if not usb and mode in ("auto","usb"):
        usb=USB_PATH if exists(USB_PATH) else None
        if not usb:
            if list_ports is None:
                from serial.tools.list_ports import comports
                list_ports=comports
            matches=[p.device for p in list_ports() if
                     (p.vid,p.pid,p.serial_number)==(0x10c4,0xea60,"0001")]
            if len(matches)>1:
                raise ImportErrorDetail("Mehrere BENNING-USB-Kandidaten. Gerät explizit wählen.")
            usb=matches[0] if matches else None
    pairs=[(kind,path) for kind,path in (("usb",usb),("rs232",rs232))
           if path and (mode in ("auto",kind))]
    active=[]
    for kind,path in pairs:
        real=os.path.realpath(path)
        if (hmi and same_device(path,hmi)) or real in ("/dev/serial0","/dev/serial1"):
            raise ImportErrorDetail("BENNING benötigt einen separaten Seriell-Port.")
        onboard=ONBOARD.fullmatch(Path(real).name) and Path(real).parent==Path("/dev")
        if onboard and (kind!="rs232" or not gpio or path!=real):
            raise ImportErrorDetail("GPIO-Empfang erfordert einen expliziten Hardware-UART für RS232-PRINT.")
        if exists(path):
            if onboard and reserved(real):
                raise ImportErrorDetail("BENNING-Port ist für Linux-Konsole oder Getty reserviert.")
            active.append((kind,path))
    if len(active)>1:
        raise ImportErrorDetail("USB und RS232 sind verbunden. Eingangsquelle explizit wählen.")
    return active[0] if active else None


class Capture:
    """A long gap closes a candidate; it cannot prove the final slot was sent."""
    def __init__(self):
        self.data=bytearray()
        self.oversize=False
        self.last=None

    def feed(self,chunk,at):
        self.last=at
        if self.oversize:
            return
        if len(self.data)+len(chunk)>MAX_BYTES:
            self.data.clear()
            self.oversize=True
            return
        self.data.extend(chunk)

    def take(self):
        if self.oversize:
            raise ImportErrorDetail("Serieller Transfer ist zu gross.")
        return bytes(self.data)


@dataclass(frozen=True)
class ReceiverStatus:
    state: str
    source: str | None = None
    received: int = 0
    detail: str = ""
    batch: int | None = None
    transport: str | None = None


class Receiver:
    def __init__(self,store,mode="auto",usb=None,rs232=None,encoding="auto",idle=1.8,
                 hmi=None,*, serial_factory=None, resolver=None, raw_capture=None,accept_reset=False, gpio=False):
        if mode not in MODES or not .5<=idle<=15:
            raise ValueError("Ungültige Quelle oder Wartezeit (0,5 bis 15 s).")
        self.store=store
        self._mode=mode
        self.has_rs232=bool(rs232)
        self._generation=0
        self.encoding=validate_encoding(encoding)
        self.idle=idle
        self.serial_factory=serial_factory
        self.resolver=resolver or (lambda:choose_port(self.mode,usb,rs232,hmi=hmi,gpio=gpio))
        self.raw_capture=raw_capture
        self.accept_reset=accept_reset
        self._stop=Event()
        self._lock=Lock()
        self._thread=None
        self._status=ReceiverStatus(mode if mode in ("file","simulation") else "searching")

    @property
    def mode(self):
        with self._lock:
            return self._mode

    def set_mode(self, mode):
        if mode not in MODES:
            raise ValueError("Ungültige Eingabe.")
        with self._lock:
            if self._mode!=mode:
                self._mode=mode
                self._generation+=1
                self._status=ReceiverStatus(mode if mode in ("file","simulation") else "searching")

    @property
    def status(self):
        with self._lock:
            return self._status

    def _set(self,state,**fields):
        with self._lock:
            self._status=replace(self._status,state=state,**fields)

    @staticmethod
    def _open(path):
        import serial
        ser=serial.Serial(port=None,baudrate=9600,bytesize=serial.EIGHTBITS,
                          parity=serial.PARITY_NONE,stopbits=serial.STOPBITS_ONE,
                          timeout=.2,xonxoff=False,rtscts=False,dsrdtr=False,exclusive=True)
        ser.dtr=False
        ser.rts=False
        ser.port=path
        ser.open()
        return ser

    def start(self):
        if self._thread is not None:
            return
        self._thread=Thread(target=self._run,name="benning-receive",daemon=True)
        self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=4)

    def _run(self):
        while not self._stop.is_set():
            with self._lock:
                generation,mode=self._generation,self._mode
            if mode not in ("file","simulation"):
                try:
                    selected=self.resolver()
                    if generation!=self._generation:
                        continue
                    if selected is None:
                        self._set("searching",source=None,received=0,detail="",transport=None)
                    else:
                        source,path=selected
                        transport="GPIO UART RX" if ONBOARD.fullmatch(Path(os.path.realpath(path)).name) else (
                            "USB RS232" if source=="rs232" else "USB CSV")
                        factory=self.serial_factory or (PrintReceiver if source=="rs232" else self._open)
                        with factory(path) as ser:
                            if generation!=self._generation:
                                continue
                            self._set("waiting",source=source,received=0,detail="",transport=transport)
                            self._receive(ser,source,generation)
                except ImportErrorDetail as exc:
                    if generation==self._generation:
                        self._set("error",source=None,detail=str(exc),transport=None)
                except (OSError,ImportError):
                    if generation==self._generation:
                        self._set("disconnected",detail="Serieller Port getrennt, belegt oder keine Zugriffsrechte.")
            self._stop.wait(1)

    def _receive(self,ser,source,generation=0):
        frame=Capture()
        next_detection=time.monotonic()+2
        try:
            while not self._stop.is_set() and generation==self._generation:
                chunk=ser.read(max(1,min(4096,ser.in_waiting)))
                at=time.monotonic()
                if generation!=self._generation:
                    return
                if chunk:
                    frame.feed(chunk,at)
                    self._set("receiving",received=len(frame.data),detail="")
                elif frame.last is not None and at-frame.last>=self.idle:
                    self._finish(frame,source)
                    frame=Capture()
                if self.mode=="auto" and frame.last is None and at>=next_detection:
                    selected=self.resolver()
                    if selected!=(source,ser.port):
                        return
                    next_detection=at+2
        except OSError:
            if generation!=self._generation:
                return
            if frame.last is not None:
                self._set("interrupted",detail="Transfer unterbrochen. Am Tester erneut auslösen.")
                self._stop.wait(1)
            else:
                raise

    def _finish(self,frame,source):
        try:
            data=frame.take()
            if self.raw_capture:
                self.raw_capture(data)
            result=self.store.import_bytes(data,source,self.encoding,accept_reset=self.accept_reset)
            self.accept_reset=False
            self._set("imported",received=len(data),batch=result.batch,detail="")
        except (ImportErrorDetail,sqlite3.Error,OSError) as exc:
            message=str(exc) if isinstance(exc,ImportErrorDetail) else "Import konnte nicht gespeichert werden."
            self._set("error",detail=message)
