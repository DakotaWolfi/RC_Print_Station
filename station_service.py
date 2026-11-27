"""Run the shared station, independently of graphics or serial display."""
import argparse
import fcntl
import logging
import os
from pathlib import Path
import signal
from threading import Event
from time import monotonic

from benning_receiver import MODES, Receiver, same_device
from benning_store import Measurements
from nextion_adapter import NextionAdapter, SerialLink
from native_ui import report_base
from report_web import start_server
from station_config import PRINTER_HOST, PRINTER_PORT, load
from station_core import StationCore
from station_ipc import DEFAULT_SOCKET, serving
from station_network import HOTSPOT_PASSWORD, NetworkManager
from web_access import status_path

LOG=logging.getLogger(__name__)
OPTIONS=("auto","nextion","hdmi","both","headless")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,default=Path("reports.sqlite3"))
    p.add_argument("--socket",default=DEFAULT_SOCKET)
    p.add_argument("--mode",choices=OPTIONS,default="hdmi")
    p.add_argument("--port",default="/dev/serial0")
    p.add_argument("--baud",type=int,default=115200)
    p.add_argument("--host",default=PRINTER_HOST)
    p.add_argument("--printer-port",type=int,default=PRINTER_PORT)
    p.add_argument("--report-url",default=os.environ.get("FMI_REPORT_FALLBACK_URL",""))
    p.add_argument("--auto-report-url",action="store_true")
    p.add_argument("--web-port",type=int,default=8080)
    p.add_argument("--wifi-interface",default="wlan0")
    p.add_argument("--hotspot-fallback",action="store_true",default=os.environ.get("FMI_HOTSPOT_FALLBACK")=="1")
    p.add_argument("--hotspot-password-file",type=Path,default=os.environ.get("FMI_HOTSPOT_PASSWORD_FILE",HOTSPOT_PASSWORD))
    p.add_argument("--enable-local-power",action="store_true")
    p.add_argument("--tester-mode",choices=MODES,default=os.environ.get("FMI_TESTER_MODE","auto"))
    p.add_argument("--tester-device",default=os.environ.get("FMI_TESTER_DEVICE"))
    p.add_argument("--tester-rs232-device",default=os.environ.get("FMI_TESTER_RS232_DEVICE"))
    p.add_argument("--tester-encoding",default=os.environ.get("FMI_TESTER_ENCODING","auto"))
    p.add_argument("--tester-gpio",action="store_true",default=os.environ.get("FMI_TESTER_GPIO_RX")=="1")
    p.add_argument("--tester-idle",type=float,default=os.environ.get("FMI_TESTER_IDLE","1.8"))
    a=p.parse_args()
    if a.report_url:
        try:
            a.report_url=report_base(a.report_url)
        except ValueError as exc:
            p.error(str(exc))
    use_serial=a.mode in ("nextion","both")
    if use_serial and any(port and same_device(port,a.port) for port in (a.tester_device,a.tester_rs232_device)):
        p.error("BENNING and Nextion require separate serial devices")
    a.db=a.db.resolve()
    logging.basicConfig(level=logging.INFO)
    stop=Event()
    for sig in (signal.SIGINT,signal.SIGTERM):
        signal.signal(sig,lambda *_:stop.set())
    # Two station services must not race to acquire the same BENNING database.
    with a.db.with_suffix(".station.lock").open("a") as lease:
        fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
        receiver=Receiver(Measurements(a.db),a.tester_mode,a.tester_device,a.tester_rs232_device,
                          a.tester_encoding,a.tester_idle,a.port,gpio=a.tester_gpio)
        receiver.set_mode(load().get("tester_mode",a.tester_mode))
        core=StationCore(a.db,receiver=receiver,host=a.host,printer_port=a.printer_port,
                         base_url=a.report_url,auto_port=a.web_port if a.auto_report_url else None,
                         network=NetworkManager(a.wifi_interface,protected_hotspot=a.hotspot_password_file,require_protected=True),
                         allow_power=a.enable_local_power,hotspot_fallback=a.hotspot_fallback,web_status=status_path(a.socket))
        serial=SerialLink(a.port,a.baud) if use_serial else None
        adapter=None
        web=None
        next_report_start=0
        core.downloads_online=False
        core.update_download_base()
        try:
            with serving(a.socket,core):
                core.start()
                if serial:
                    serial.start()
                LOG.info("Station core ready (%s)",a.mode)
                while not stop.wait(.075):
                    if (a.report_url or a.auto_report_url) and web is None and monotonic()>=next_report_start:
                        try:
                            web=start_server(a.db,a.web_port)
                        except OSError as error:
                            LOG.warning("PDF listener could not bind port %s (%s). Local workflow remains available.",
                                        a.web_port,error.errno)
                            next_report_start=monotonic()+10
                        else:
                            with core.lock:
                                core.downloads_online=True
                                core.update_download_base()
                    core.tick()
                    if serial and serial.ready.is_set():
                        with core.lock:
                            try:
                                if adapter is None:
                                    adapter=NextionAdapter(core,serial)
                                while not serial.rx.empty():
                                    frame=serial.rx.get_nowait()
                                    if frame is None:
                                        adapter.connect_panel()
                                    else:
                                        adapter.feed(frame)
                                adapter.sync()
                            except Exception as exc:
                                LOG.warning("Nextion adapter reset (%s)",type(exc).__name__)
                                serial.reset.set()
                                if adapter:
                                    adapter.close()
                                    adapter=None
                    elif adapter:
                        with core.lock:
                            adapter.close()
                            adapter=None
        finally:
            if serial:
                serial.close()
            if adapter:
                adapter.close()
            core.close()
            if web:
                web.shutdown()
                web.server_close()


if __name__=="__main__":
    main()
