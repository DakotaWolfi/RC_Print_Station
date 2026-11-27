from ipaddress import IPv4Interface
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest import TestCase

from benning_receiver import Receiver, ReceiverStatus
from slogan_store import SloganStore
from station_core import StationCore
from test_benning import RS232
from web_access import LocalAccess, read_status


class Reliability(TestCase):
    def test_dhcp_subnet_and_hotspot_retire_old_hosts_and_reject_wan(self):
        access=LocalAccess(("wlan0",),8090,"fmi-printstation.local")
        for old,new in (("192.168.200.241/23","192.168.9.221/23"),
                        ("192.168.9.221/23","10.42.0.1/24")):
            access.addresses=(IPv4Interface(old),)
            self.assertTrue(access.accepts(old.split("/")[0],old.rsplit(".",1)[0]+".99"))
            self.assertFalse(access.accepts(old.split("/")[0],"8.8.8.8"))
            access.addresses=(IPv4Interface(new),)
            self.assertFalse(access.accepts(old.split("/")[0],old.rsplit(".",1)[0]+".99"))
            self.assertEqual(access.dynamic_hosts(old.split("/")[0]),())
            self.assertEqual(access.discover()["urls"],[f"http://{new.split('/')[0]}:8090"])
        access.addresses=()
        self.assertEqual(access.discover()["status"],"no-address")

    def test_resume_preserves_draft_without_reusing_measurement_decision(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            rx=SimpleNamespace(mode="file",status=ReceiverStatus("file"),close=lambda:None)
            opts=dict(receiver=rx,config_path=root/"config.json",cache=SloganStore(root/"pets.db"))
            core=StationCore(root/"reports.db",**opts)
            def run(op,args):
                result=core.command(dict(op=op,args=args))
                self.assertTrue(result["ok"],result)
                return result["data"]
            run("draft.new",{"mode":"guided"})
            d=core.draft
            run("draft.edit",{"draft":d["id"],"changes":{"ticket":"724","device":"Bench appliance"},
                              "previous":{"ticket":"","device":""}})
            run("exam.start",dict(draft=d["id"],version=d["version"]))
            run("guide.choose",dict(draft=d["id"],version=d["version"],choice=0,step="visual"))
            core.close()
            restored=StationCore(root/"reports.db",**opts)
            try:
                self.assertEqual((restored.phase,restored.draft["ticket"]),("entry","724"))
                self.assertNotEqual(restored.draft["id"],d["id"])
                self.assertTrue(restored.recovery_note)
                self.assertIsNone(restored.guide)
                self.assertFalse(restored.command({"op":"guide.choose","epoch":core.epoch})["ok"])
            finally:
                restored.close()

    def test_truncated_frame_rejects_then_same_receiver_imports_good_record(self):
        with tempfile.TemporaryDirectory() as temp:
            from benning_store import Measurements
            store=Measurements(Path(temp)/"reports.db")
            rx=Receiver(store,mode="rs232",idle=.5)
            events=[]
            setter=rx._set
            def record(state,**fields):
                events.append(state)
                setter(state,**fields)
            rx._set=record
            def gap():
                time.sleep(.52)
                return b""
            fragments=iter((b"bad",gap,RS232[:38],RS232[38:],gap))
            def read(_):
                item=next(fragments,None)
                if item is None:
                    rx._stop.set()
                    return b""
                return item() if callable(item) else item
            rx._receive(SimpleNamespace(read=read,in_waiting=0),"rs232")
            self.assertIn("error",events)
            self.assertEqual(events[-1],"imported")
            [slot]=store.slots("rs232")
            self.assertEqual(slot["slot"],"012")
            self.assertIsNone(slot["original"]["protection_class"])

    def test_health_metadata_expires(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"web.json"
            path.write_text(json.dumps({"timestamp":50.,"status":"reachable","urls":["http://10.42.0.1:8090"]}))
            self.assertEqual(read_status(path,lambda:55)["status"],"reachable")
            self.assertEqual(read_status(path,lambda:59)["status"],"unavailable")
