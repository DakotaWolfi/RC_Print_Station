from pathlib import Path
import tempfile
from threading import Event, Thread
from types import SimpleNamespace
from urllib.request import urlopen

from benning_hardware import USB_COMPLETE
from benning_receiver import ReceiverStatus
from report_web import start_server
from slogan_store import SloganStore
from station_core import StationCore
from test_benning import RS232
from web_hmi import Gateway, Handler, Server, digest

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    rx=SimpleNamespace(mode="rs232",status=ReceiverStatus("waiting","rs232"),close=lambda:None)
    pdf=start_server(root/"reports.db",18193)
    prints=[]
    pdf_downloads=[]
    OriginalPDF=pdf.RequestHandlerClass
    class FixturePDF(OriginalPDF):
        def do_GET(self):
            if self.path.endswith("?download=1"):
                pdf_downloads.append(self.path)
            super().do_GET()
    pdf.RequestHandlerClass=FixturePDF
    core=StationCore(root/"reports.db",receiver=rx,config_path=root/"settings.json",
                     cache=SloganStore(root/"pets.db"),sender=lambda *args:prints.append(args),
                     base_url="http://127.0.0.1:18191")
    core.operators.rename("Bench Operator")
    stop=Event()
    def update():
        while not stop.wait(.04):
            core.tick()
    Thread(target=update,daemon=True).start()
    def transport(_,packet):
        packet=packet.copy()
        return core.command(packet,packet.pop("client"))
    class FixtureHandler(Handler):
        def do_GET(self):
            if self.path=="/__test/import":
                result=core.store.import_bytes(RS232,"rs232")
                rx.status=ReceiverStatus("imported","rs232",batch=result.batch)
                self.send_payload(200,{"slot":result.batch})
            elif self.path=="/__test/import-usb":
                result=core.store.import_bytes(USB_COMPLETE,"usb")
                rx.mode="usb"
                rx.status=ReceiverStatus("imported","usb",batch=result.batch)
                self.send_payload(200,{"count":result.count})
            elif self.path=="/__test/downloads":
                self.send_payload(200,{"count":len(pdf_downloads)})
            elif self.path=="/__test/prints":
                self.send_payload(200,{"count":len(prints)})
            elif self.path.startswith("/r/"):
                # Serve the real PDF response through the fixture origin so
                # the test shell can inspect the attachment under CSP.
                with urlopen("http://127.0.0.1:18193"+self.path,timeout=5) as pdf_response:
                    self.send_response(pdf_response.status)
                    for name in ("Content-Type","Content-Disposition","Content-Length"):
                        self.send_header(name,pdf_response.headers[name])
                    self.end_headers()
                    self.wfile.write(pdf_response.read())
            else:
                super().do_GET()
    salt=b"browser-test-only"
    gateway=Gateway((salt,digest("local-admin-fixture",salt)),
                    ["http://127.0.0.1:18191"],transport=transport)
    server=Server(("127.0.0.1",18191),gateway)
    server.RequestHandlerClass=FixtureHandler
    try:
        server.serve_forever()
    finally:
        stop.set()
        core.close()
        pdf.shutdown()
