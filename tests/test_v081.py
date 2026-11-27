import fcntl
import os
import pty
import termios
from http.client import HTTPConnection
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from uuid import uuid4

from benning_csv import ImportErrorDetail
from benning_receiver import Receiver, ReceiverStatus, choose_port
from benning_rs232 import parse_printout
from benning_serial import PrintReceiver, onboard_reserved
from report_web import start_server
from slogan_store import SloganStore
from station import simulate
from station_core import StationCore
from station_network import hotspot_password, NetworkError
from touch_calibration import apply, fit, rotation, TARGETS, rule
from web_hmi import Gateway, Server, load_auth, set_password
from test_benning import RS232


class TouchCalibrationTests(TestCase):
    def test_all_rotations_corner_mapping_and_fit(self):
        corners=((0,0),(1,0),(1,1),(0,1))
        for turns in range(4):
            matrix=rotation(turns*90)
            self.assertEqual([apply(matrix,point) for point in corners],
                             [corners[(i+turns)%4] for i in range(4)])
            inverted=rotation(-turns*90%360)
            raw=[apply(inverted,point) for point in TARGETS]
            for a,b in zip(matrix,fit(raw)):
                self.assertAlmostEqual(a,b)
            for a,b in zip(rotation(),fit(raw,compositor_rotation=turns*90)):
                self.assertAlmostEqual(a,b)
        self.assertEqual(apply(rotation(swap=True,invert_x=True),(.29,.63)),(.37,.29))
        self.assertIn('ID_PATH}=="usb-1:1.0"',rule(rotation(),device_path="usb-1:1.0"))
        with self.assertRaises(ValueError):
            fit([(.1,.1)]*5)
        with self.assertRaises(ValueError):
            rule(rotation(),device_path='bad"')


class SerialTests(TestCase):
    def test_explicit_gpio_and_alias_rejection(self):
        args=dict(exists=lambda p:True,reserved=lambda p:False)
        uart="/dev/ttyAMA3"
        self.assertEqual(choose_port("rs232",rs232=uart,gpio=True,**args),("rs232",uart))
        for kw in ({"gpio":False},{"gpio":True,"hmi":uart},{"gpio":True,"rs232":"/dev/serial0"},
                   {"gpio":True,"reserved":lambda p:True}):
            with self.assertRaises(ImportErrorDetail):
                choose_port("rs232",**{**args,"rs232":uart,**kw})
        with self.assertRaises(ImportErrorDetail):
            choose_port("auto",usb="/dev/ttyUSB1",rs232=uart,gpio=True,**args)

    def test_kernel_console_and_enabled_getty(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"cmdline").write_text("console=ttyAMA3,115200 console=tty1")
            runner=Mock(return_value=SimpleNamespace(stdout="inactive"))
            self.assertTrue(onboard_reserved("/dev/ttyAMA3",proc=root,sys=root,run=runner))
            runner.assert_not_called()
            runner.side_effect=[SimpleNamespace(stdout="inactive"),SimpleNamespace(stdout="enabled")]
            self.assertTrue(onboard_reserved("/dev/ttyAMA4",proc=root,sys=root,run=runner))

    def test_linux_pty_is_read_only_9600_8n1(self):
        master,slave=pty.openpty()
        self.addCleanup(os.close,master)
        self.addCleanup(os.close,slave)
        with PrintReceiver(os.ttyname(slave)) as port:
            self.assertEqual(fcntl.fcntl(port.fd,fcntl.F_GETFL)&os.O_ACCMODE,os.O_RDONLY)
            attrs=termios.tcgetattr(port.fd)
            self.assertEqual(attrs[:6],[0,0,termios.B9600|termios.CLOCAL|termios.CREAD|termios.CS8,
                                        0,termios.B9600,termios.B9600])
            with self.assertRaises(OSError):
                os.write(port.fd,b"forbidden")
            os.write(master,b"part-one")
            self.assertEqual(port.read(50),b"part-one")

    def test_u_iso_raw_and_fragmented_read_only_print_capture(self):
        data=RS232.replace(b"VISO:",b"UISO:")
        _,records=parse_printout(data,wire=True)
        self.assertEqual(records[0].voltage,"500V")
        with self.assertRaises(ImportErrorDetail):
            parse_printout(b"\r\n",wire=True)
        with self.assertRaises(ImportErrorDetail):
            parse_printout(data[:-4],wire=True)
        store=Mock()
        store.import_bytes.return_value=SimpleNamespace(batch=3)
        captures=[]
        rx=Receiver(store,mode="rs232",raw_capture=captures.append)
        serial=Mock(in_waiting=10)
        serial.read.side_effect=[data[:12],data[12:90],data[90:],b"",OSError()]
        with patch("benning_receiver.time.monotonic",side_effect=[0,.1,.2,.3,2.4]):
            with self.assertRaises(OSError):
                rx._receive(serial,"rs232")
        self.assertEqual(captures,[data])
        serial.write.assert_not_called()
        self.assertEqual(rx.status.batch,3)

    def test_password_file_is_private_and_mandatory(self):
        with TemporaryDirectory() as directory:
            path=Path(directory)/"hotspot.psk"
            path.write_text("local-setup-passphrase\n")
            path.chmod(0o644)
            with self.assertRaises(NetworkError):
                hotspot_password(path)
            path.chmod(0o600)
            self.assertEqual(hotspot_password(path),"local-setup-passphrase")
            with self.assertRaises(NetworkError):
                hotspot_password(None)


class WebTests(TestCase):
    def setUp(self):
        temp=TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root=Path(temp.name)
        rx=SimpleNamespace(mode="file",status=ReceiverStatus("file"),close=lambda:None)
        self.core=StationCore(root/"station.db",receiver=rx,config_path=root/"station.json",
                              cache=SloganStore(root/"slogans.db"))
        self.addCleanup(self.core.close)
        def transport(path,packet):
            return self.core.command({key:value for key,value in packet.items() if key!="client"},packet["client"])
        credential=root/"auth.json"
        set_password(credential,"correct-horse-station")
        origin="http://localhost:8090"
        self.gateway=Gateway(load_auth(credential),[origin],transport=transport)
        self.server=Server(("127.0.0.1",0),self.gateway)
        self.thread=Thread(target=self.server.serve_forever,kwargs={"poll_interval":.04},daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server,self.server)
        self.origin=origin
        self.cookie=self.csrf=None
        self.tab=uuid4().hex

    @staticmethod
    def stop_server(server):
        server.shutdown()
        server.server_close()

    def http(self,path,body=None,*,origin=True,csrf=True,cookie=True,host="localhost:8090"):
        headers={"Host":host}
        if origin:
            headers["Origin"]=self.origin
        if csrf and self.csrf:
            headers["X-CSRF-Token"]=self.csrf
        if cookie and self.cookie:
            headers["Cookie"]=self.cookie
        conn=HTTPConnection("127.0.0.1",self.server.server_port,timeout=3)
        try:
            if body is not None:
                headers["Content-Type"]="application/json"
            conn.request("GET" if body is None else "POST",path,
                         None if body is None else json.dumps(body),headers)
            response=conn.getresponse()
            payload=response.read()
            return response.status,response.headers,payload
        finally:
            conn.close()

    def login(self):
        code,headers,payload=self.http("/api/login",{"password":"correct-horse-station"})
        self.assertEqual(code,200)
        cookie=headers["Set-Cookie"]
        self.assertIn("HttpOnly",cookie)
        self.assertIn("SameSite=Strict",cookie)
        self.cookie=cookie.split(";")[0]
        self.csrf=json.loads(payload)["csrf"]

    def command(self,op,args=None,key=None,tab=None,code=200):
        packet=dict(op=op,args=args or {},id=key or uuid4().hex,epoch=self.core.epoch,tab=tab or self.tab)
        status,_,data=self.http("/api/command",packet)
        self.assertEqual(status,code,data)
        return json.loads(data)

    def test_auth_origin_csrf_and_tokenized_pdf_isolation(self):
        self.assertEqual(self.http("/api/command",{})[0],401)
        self.assertEqual(self.http("/api/login",{"password":"wrong"},origin=False)[0],403)
        self.assertEqual(self.http("/",host="evil.test")[0],400)
        self.login()
        self.assertEqual(self.http("/api/command",{},csrf=False)[0],403)
        self.assertEqual(self.http("/api/command",{},origin=False)[0],403)
        self.command("shell",code=403)
        self.command("settings.save",{"values":{"api_key":"no"}},code=403)
        self.assertEqual(self.http("/r/token")[0],404)
        pdf=start_server(self.core.db,0)
        self.addCleanup(self.stop_server,pdf)
        self.core.base_url=f"http://127.0.0.1:{pdf.server_port}"
        ident=self.core.store_report(simulate("SIM-081","Calibration lamp"))
        metadata=self.command("report.view",{"report":ident})["data"]
        self.assertEqual(metadata["kind"],"simulation")
        qr=self.command("report.qr",{"report":ident})["data"]
        self.assertTrue(qr["modules"])
        from urllib.request import urlopen
        with urlopen(qr["url"],timeout=2) as response:
            self.assertTrue(response.read().startswith(b"%PDF"))
        with self.assertRaises(OSError):
            urlopen(self.core.base_url+"/api/session",timeout=2)
        self.assertEqual(self.http("/api/logout",{})[0],200)
        self.assertEqual(self.http("/api/session")[0],401)

    def test_tab_field_lease_conflict_expiry_recovery_and_replay(self):
        self.login()
        key,other=uuid4().hex,uuid4().hex
        self.command("draft.new",{"mode":"direct"},key=key)
        d=self.core.draft
        self.command("draft.new",{"mode":"direct"},key=key)
        self.assertIs(self.core.draft,d)
        self.command("draft.editor",{"draft":d["id"],"active":True,"field":"ticket"})
        entry={"draft":d["id"],"previous":{"ticket":""},"changes":{"ticket":"081"}}
        self.command("draft.edit",entry,tab=other,code=409)
        self.assertTrue(self.core.command({"op":"draft.edit","args":{"draft":d["id"],
            "changes":{"device":"Bench lamp"},"previous":{"device":""}}},"nextion")["ok"])
        self.command("settings.save",{"values":{"language":"en"}},tab=other)
        self.assertEqual(d["device"],"Bench lamp")
        with patch("station_core.monotonic",return_value=10**12):
            self.command("draft.edit",entry,tab=other)
        self.command("language.report",{"draft":d["id"],"version":d["version"],"language":"de"},tab=other)
        result=self.command("state",tab=other)["data"]
        self.assertEqual((result["language"],result["report_language"]),("en","de"))
        self.assertEqual(result["draft"]["ticket"],"081")

    def test_core_disconnect_preserves_session_and_does_not_replay(self):
        self.login()
        self.command("draft.new",{"mode":"direct"})
        state=self.command("state")["data"]
        transport=self.gateway.transport
        lost=Mock(side_effect=TimeoutError)
        self.gateway.transport=lost
        self.command("draft.discard",{"draft":state["draft"]["id"],
                     "version":state["draft"]["version"],"confirmed":True},code=503)
        lost.assert_called_once()
        self.gateway.transport=transport
        self.assertEqual(self.http("/api/session")[0],200)
        self.assertEqual(self.command("state")["data"]["draft"],state["draft"])

    def test_professional_treats_are_disabled(self):
        self.login()
        self.command("personality.treat")
        self.assertEqual(self.core.achievements_pending["treats"],1)
        self.command("settings.save",{"values":{"professional":True}})
        self.command("personality.treat",code=409)
        self.command("novelty.print",{"kind":"awoo","confirmed":True},code=409)
        self.assertEqual(self.core.achievements_pending,{})
