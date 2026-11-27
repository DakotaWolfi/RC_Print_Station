from pathlib import Path
import tempfile
from threading import Event, Thread
from types import SimpleNamespace

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
    core=StationCore(root/"reports.db",receiver=rx,config_path=root/"settings.json",
                     cache=SloganStore(root/"pets.db"),sender=lambda *args:prints.append(args),
                     base_url="http://127.0.0.1:18193")
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
            elif self.path=="/__test/prints":
                self.send_payload(200,{"count":len(prints)})
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
