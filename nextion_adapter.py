"""Protocol 71 transport and native projection for StationCore."""
from contextlib import suppress
import logging
from queue import Empty, Full, Queue
from threading import Event, Thread
from time import monotonic

from benning_panel import TesterPanel
from native_ui import ENCODING, END, NativeUI, PROTOCOL, verify_panel
from panel_text import printable
from station_core import CYCLE
from station_panel_settings import PAGES, PanelSettings


LOG = logging.getLogger(__name__)
PAGE_FOR_STAGE = {"entry":"entry","guide":"guide","waiting":"importer","review":"tester","report":"report"}
SETTINGS_PAGES = ("settings","wifi","wjoin","printer","receipt","system","power")


class SerialLink:
    """The serial thread owns opening, probing, reading and writing the port."""
    def __init__(self, device, baud=115200, opener=None, handshaker=verify_panel):
        self.device,self.baud,self.opener,self.handshaker=device,baud,opener,handshaker
        self.rx=Queue(64)
        self.tx=Queue(256)
        self.ready=Event()
        self.reset=Event()
        self.stop=Event()
        self.thread=Thread(target=self.run,daemon=True,name="nextion-serial")

    def write(self,data):
        if self.ready.is_set():
            try:
                self.tx.put_nowait(data)
            except Full:
                self.reset.set()
        return len(data)

    def flush(self):
        pass

    @staticmethod
    def drain(queue):
        with suppress(Empty):
            while True:
                queue.get_nowait()

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)

    def run(self):
        if self.opener is None:
            from serial import Serial
            self.opener=Serial
        delay=1
        while not self.stop.is_set():
            try:
                with self.opener(self.device,self.baud,timeout=.04,write_timeout=.25,exclusive=True) as ser:
                    self.handshaker(ser,timeout=.85)
                    self.drain(self.tx)
                    self.drain(self.rx)
                    self.reset.clear()
                    self.rx.put_nowait(None)
                    self.ready.set()
                    delay=1
                    while not self.stop.is_set() and not self.reset.is_set():
                        pending=bytearray()
                        for _ in range(24):
                            try:
                                pending.extend(self.tx.get_nowait())
                            except Empty:
                                break
                        if pending:
                            ser.write(pending)
                        data=ser.read(min(2048,ser.in_waiting or 1))
                        if data:
                            self.rx.put_nowait(data)
            except (OSError,RuntimeError,ValueError,Full) as error:
                if self.ready.is_set():
                    LOG.info("Nextion disconnected (%s)",type(error).__name__)
            finally:
                self.ready.clear()
            if self.stop.wait(delay):
                return
            delay=min(15,delay*2)


class ProjectionSettings(PanelSettings):
    """Only the existing settings renderer is used under the shared core."""
    def cfg(self):
        return self.ui.core.config

    def endpoint(self,settings):
        return self.ui.core.endpoint()

    def choices(self):
        from station_network import Network
        core=self.ui.core
        rows=list(core.access_points.values())
        if core.ssid=="FMI-RC-Printstation" and core.ip:
            return [Network("hotspot-stop",b"Hotspot beenden",0,"AP","")]
        return rows+[Network("hotspot-start",b"FMI Hotspot starten",0,"AP","")]


class NextionAdapter(NativeUI):
    def __init__(self, core, ser):
        super().__init__(ser,core.host,core.db,core.printer_port,
                         tester_receiver=core.receiver,config_path=core.config_path,
                         enable_power=core.allow_power,personality_cache=core.cache.path)
        self.core=core
        self.settings.close()
        self.settings=ProjectionSettings(self,core.network,core.config_path,core.allow_power)
        self.next_sync=0
        self.rendered=None
        self.presented={}
        self.entry_seen={}
        self.page_seen=None
        self.guide_wait=False
        self.m_pending=None
        self.logo_taps=[]
        self.last_stage=None
        self.follow_on_connect=True
        self.settings_view=None
        self.last_status=None
        self.print_seen=None
        self.watchdog_time=0
        self.entry_phase=None
        self.entry_active=None
        self.mode_pending=False
        self.entry_conflict=None
        self.keyboard_draft=False

    def action(self,op,args=None):
        result=self.core.command({"op":op,"args":args or {}},"nextion")
        if not result["ok"]:
            message=result["error"]
            field={"guide":"gError","tester":"mNote","entry":"entry.tStatus","report":"report.tStatus",
                   "wifi":"wStatus","wjoin":"jStatus","printer":"pStatus","power":"xStatus",
                   "picker":"pNote","importer":"iMessage"}.get(self.settings.page,"home.tHint")
            self.say(field,message,100)
            if self.settings.page=="entry":
                self.cmd("entry.busy.val=0")
            elif self.settings.page=="guide":
                self.cmd("gBusy.val=0")
            elif self.settings.page=="tester":
                self.cmd("mSaving.val=0")
        return result

    def reference(self):
        draft=self.presented
        return {"draft":draft.get("id"),"version":draft.get("version")}

    def connect_panel(self):
        self.decoder.buffer.clear()
        self.follow_on_connect=True
        self.last_stage=None
        self.settings.page=None
        self.presented={}
        self.entry_seen={}
        self.entry_active=None
        self.last_status=None
        self.rendered=None
        self.print_seen=None
        self.guide_wait=False
        self.mode_pending=False
        self.entry_conflict=None
        self.core.lease("nextion",False,None)
        self.cmd("bkcmd=2")
        self.cmd("sendxy=0")
        self.language=self.core.language
        self.cmd(f"home.lang.val={int(self.language=='en')}")
        self.cmd(f"entry.sim.val={int(self.core.receiver.mode=='simulation')}")
        self.cmd("entry.busy.val=0")
        self.cmd("home.pending.val=0")
        self.cmd("history.pending.val=0")
        self.cmd("report.ready.val=0")
        self.cmd("report.printing.val=0")
        self.settings.apply_display(force=True)
        self.heartbeat(force=True)
        self.cmd("sendme")

    def entry_merge(self,values):
        draft=self.core.draft
        if not draft or draft["stage"]!="entry" or self.entry_seen.get("id")!=draft["id"]:
            return not values
        if "phase" in values and values["phase"]==self.entry_phase:
            values.pop("phase")
        seen=self.entry_seen
        changes={key:value for key,value in values.items() if (
            value!=seen.get(key+"_wire",seen.get(key)))}
        if not changes:
            return True
        result=self.action("draft.edit",{"draft":seen["id"],"changes":changes,
                    "previous":{key:seen[key] for key in changes}})
        return result["ok"]

    def set_entry(self):
        d=self.core.draft
        editable=bool(d and d["stage"]!="report")
        if editable!=self.entry_active:
            self.cmd(f"entry.inProgress.val={int(editable)}")
            if self.settings.page=="home":
                self.cmd(f"vis bResume,{int(editable)}")
            self.entry_active=editable
        if not editable:
            return
        if self.entry_seen and self.entry_seen.get("id")==d["id"] and self.settings.page=="keyboard":
            return
        needs_write={key:d[key] for key in ("ticket","device","phase","slot","autofill","id")}
        if self.entry_seen and all(self.entry_seen.get(k)==v for k,v in needs_write.items()):
            return
        for key,widget,limit in (("ticket","tTicket",32),("device","tDevice",64),("slot","tSlot",3)):
            shown=printable(d[key])
            self.text("entry."+widget,shown,limit)
            needs_write[key+"_wire"]=shown
            if self.settings.page=="entry" and key!="slot":
                self.text(widget+"View",shown,limit+2)
        self.cmd(f"entry.guided.val={int(d['mode']=='guided')}")
        self.cmd(f"entry.phase.val={d['phase']}")
        self.cmd(f"entry.useLast.val={int(d['autofill'])}")
        if self.settings.page=="entry":
            self.cmd("click hPhase,0")
            self.cmd(f"cLast.val={int(d['autofill'])}")
        self.entry_phase=d["phase"]
        self.entry_seen=needs_write

    def settings_event(self,frame):
        action,_,data=frame.partition(b"\0")
        c=self.core.config
        if action in (b"RC4:IP",b"RC4:PORT") and self.settings.page=="keyboard":
            field="printer_host" if action==b"RC4:IP" else "printer_port"
            self.action("settings.save",{"values":{field:data.decode("ascii") if field=="printer_host" else int(data)}})
        elif action==b"RC4:PROBE" and self.settings.page=="printer":
            self.action("printer.probe")
        elif action==b"RC4:TEST" and self.settings.page=="printer":
            self.action("printer.test",{"confirmed":True})
        elif self.settings.page=="receipt" and action in (b"RC4:GRAPH",b"RC4:FEED+",b"RC4:FEED-",b"RC4:DENSITY"):
            densities=("default","light","dark")
            values={b"RC4:GRAPH":{"graphic":not c["graphic"]},
                    b"RC4:FEED+":{"feed_mm":min(100,c["feed_mm"]+5)},
                    b"RC4:FEED-":{"feed_mm":max(0,c["feed_mm"]-5)},
                    b"RC4:DENSITY":{"density":densities[(densities.index(c["density"])+1)%3]}}
            self.action("settings.save",{"values":values[action]})
        elif self.settings.page=="system" and action in (b"RC4:BR+",b"RC4:BR-",b"RC4:STANDBY"):
            if action==b"RC4:STANDBY":
                values={"standby":next((n for n in (30,60,120,300,600) if n>c["standby"]),0)}
            else:
                values={"brightness":max(10,min(100,c["brightness"]+(10 if action.endswith(b"+") else -10)))}
            self.action("settings.save",{"values":values})
        elif action in (b"RC4:HALT",b"RC4:REBOOT") and self.settings.page=="power":
            if monotonic()<self.settings.armed_until:
                self.settings.armed_until=0
                self.action("power.halt" if action.endswith(b"HALT") else "power.reboot",{"confirmed":True})
        elif self.settings.page=="wifi" and action==b"RC4:SCAN":
            self.action("wifi.scan")
        elif self.settings.page=="wifi" and action.startswith(b"RC4:SEL:"):
            index=self.settings.offset+int(action[-1:])
            choices=self.settings.choices()
            if 0<=index<len(choices):
                self.settings.selected=choices[index]
                self.settings.joined=False
        elif self.settings.page=="wifi" and action in (b"RC4:NEXT",b"RC4:PREV"):
            self.settings.offset=max(0,min(self.settings.offset+(4 if action.endswith(b"NEXT") else -4),
                                          (len(self.settings.choices())-1)//4*4))
        elif (self.settings.page,action) in (("wjoin",b"RC4:JOIN"),("keyboard",b"RC4:PASS")):
            net=self.settings.selected
            if net and net.path.startswith("hotspot-"):
                self.action("wifi.stop" if net.path.endswith("stop") else "wifi.hotspot",{"confirmed":True})
            elif net:
                key=next((i for i,n in self.core.access_points.items() if n==net),None)
                self.action("wifi.connect",{"network":key,"password":data.decode(ENCODING)})
        self.settings_view=None

    def handle(self,frame):
        page=self.settings.page
        if len(frame)==2 and frame[0]==0x66:
            self.page_seen=PAGES[frame[1]] if frame[1]<len(PAGES) else None
            self.settings.page=self.page_seen
            if self.page_seen=="keyboard":
                self.keyboard_draft=page in ("entry","guide") and self.core.draft is not None
            elif page=="keyboard":
                self.core.lease("nextion",False,None)
            self.rendered=None
            if page=="tester" and self.page_seen=="entry" and self.core.phase=="review":
                self.action("review.back",self.reference())
            if self.page_seen=="power":
                self.settings.armed_until=monotonic()+20
            if self.page_seen=="history":
                self.refresh_history()
            # RC61:DRAFT follows the entry page announcement in the same native event.
            return
        if frame==b"RC3:BOOT":
            self.connect_panel()
            return
        if frame.startswith(b"\x70") and self.m_pending:
            kind,expected=self.m_pending
            self.m_pending=None
            if frame[1:].decode(ENCODING)==expected:
                LOG.info("Nextion %s text confirmed",kind)
            else:
                LOG.warning("Nextion %s confirmation differs",kind)
            return
        if frame in (b"RC71:LOCALE:DE",b"RC71:LOCALE:EN"):
            LOG.debug("Nextion rendered locale %s",frame[-2:].decode())
            return
        if len(frame)==5 and frame[0]==0x71:
            if self.mode_pending:
                self.mode_pending=False
                if not self.core.draft or self.core.phase=="report":
                    mode="guided" if int.from_bytes(frame[1:],"little")==1 else "direct"
                    self.action("draft.new",{"mode":mode})
                self.entry_seen={}
                self.rendered=None
            elif self.guide_wait:
                self.guide_wait=False
            return
        try:
            self.translate(frame,page)
        except (ValueError,UnicodeError,IndexError):
            LOG.warning("Invalid Nextion action on %s",page)
            self.rendered=None

    def translate(self,frame,page):
        core=self.core
        cmd,_,payload=frame.partition(b"\0")
        ref=self.reference()
        if cmd==b"RC70:LANG" and page=="home":
            target="de" if core.language=="en" else "en"
            LOG.info("Nextion station language event: %s",target)
            self.action("settings.save",{"values":{"language":target}})
        elif cmd==b"RC70:REPORTLANG" and page=="entry":
            target="de" if core.report_language()=="en" else "en"
            LOG.info("Nextion report language event: %s",target)
            self.action("language.report",dict(ref,language=target))
        elif cmd==b"RC6:NEW" and page=="home":
            # The same wire event is sent by both home buttons. Read its mode
            # from the firmware's first start action; the draft is still shared.
            self.mode_pending=True
            self.entry_seen={}
            self.entry_active=True
            self.entry_conflict=None
            self.cmd("get entry.guided.val")
            self.follow_on_connect=True
        elif cmd==b"RC61:DRAFT" and page=="entry":
            values=payload.decode(ENCODING).split("\0")
            if len(values)==2 and self.entry_seen and not self.mode_pending:
                if not self.entry_merge(dict(zip(("ticket","device"),values))):
                    # Keep the local keyboard value visible and block submission
                    # until the operator cancels/reopens or explicitly edits it.
                    self.entry_conflict=dict(zip(("ticket","device"),values))
                    return
            self.entry_conflict=None
        elif page=="entry" and cmd in (b"RC6:GUIDE",b"RC6:IMPORT",b"RC6:EXISTING",b"RC3:CREATE"):
            fields=payload.decode(ENCODING).split("\0")
            values=dict(zip(("ticket","device"),fields[:2]))
            if len(fields)==5:
                values.update(phase=int(fields[3]),autofill=fields[4]=="1")
                if fields[2] and not values["autofill"]:
                    values["slot"]=fields[2]
            if not core.draft or core.phase!="entry" or self.entry_conflict or not self.entry_merge(values):
                self.cmd("entry.busy.val=0")
                return
            op="review.find" if cmd==b"RC6:EXISTING" else "exam.start"
            self.action(op,dict(draft=core.draft["id"],version=core.draft["version"]))
            self.rendered=None
        elif cmd in (b"RC5:AUTOON",b"RC5:AUTOOFF") and page=="entry":
            self.entry_merge({"autofill":cmd.endswith(b"ON")})
        elif page=="guide" and core.phase=="guide" and not self.guide_wait:
            if cmd.startswith(b"RC6:STEP:"):
                self.action("guide.choose",dict(ref,step=self.presented.get("step"),choice=int(cmd[9:])))
            elif cmd in (b"RC6:BACK",b"RC6:CANCEL"):
                self.action("guide.back" if cmd.endswith(b"BACK") else "guide.cancel",dict(ref,confirmed=True))
            elif cmd==b"RC6:HELP":
                self.workflow.help=not self.workflow.help
            elif cmd==b"RC6:FUNCTION":
                value=CYCLE[(CYCLE.index(core.guide.functional)+1)%len(CYCLE)]
                self.action("exam.function",dict(ref,value=value))
            elif cmd==b"RC6:EXAM":
                remarks=payload.decode(ENCODING)
                previous=self.presented.get("remarks","")
                if remarks!=printable(previous):
                    if not self.action("draft.edit",dict(ref,previous={"remarks":previous},changes={"remarks":remarks}))["ok"]:
                        return
                    ref["version"]=core.draft["version"]
                self.action("exam.submit",ref)
            elif cmd==b"RC61:PEOPLE":
                self.picker.open("people",core.draft["examiner"])
            self.rendered=None
        elif cmd==b"RC61:APPLIANCES" and page=="entry":
            self.picker.open("appliance")
        elif page=="picker" or (page=="keyboard" and cmd==b"RC61:NAME"):
            self.picker_event(frame)
        elif page=="importer" and core.phase=="waiting":
            if cmd==b"RC6:MANUAL":
                self.action("review.manual",ref)
            elif cmd==b"RC6:BACK":
                self.action("review.back",ref)
            elif cmd==b"RC6:HELP":
                self.workflow.help=not self.workflow.help
            self.rendered=None
        elif page=="tester" and core.phase=="review":
            if cmd.startswith(b"RC5:SEL:"):
                index=self.tester.offset+int(cmd[-1:])
                if index<len(self.presented.get("slots",())):
                    self.action("review.select",dict(ref,record=self.presented["slots"][index]))
            elif cmd==b"RC5:USE":
                self.action("review.confirm",dict(ref,record=self.presented.get("record")))
            elif cmd in (b"RC5:NEXT",b"RC5:PREV"):
                self.tester.offset=max(0,min(self.tester.offset+(4 if cmd.endswith(b"NEXT") else -4),
                                             max(0,(len(core.slots)-1)//4*4)))
            self.rendered=None
        elif cmd.startswith(b"RC4:"):
            self.settings_event(frame)
        elif cmd==b"RC3:PRINT" and page=="report":
            self.action("report.print",{"report":self.report_id,"confirmed":True})
            self.cmd("report.printing.val=0")
        elif cmd==b"RC3:QR" and page=="qrpage":
            result=self.action("report.link",{"report":self.report_id})
            if result["ok"] and len(result["data"])<=78:
                self.text("qrpage.qrReport",result["data"],78)
                self.say("qrpage.tNote","Mit dem Handy scannen. Handy und Station müssen im selben Netz sein.",100)
                self.cmd("qrpage.qReady.val=1")
            else:
                self.cmd("qrpage.qReady.val=2")
        elif cmd.startswith(b"RC3:OPEN:") and page=="history":
            index=int(cmd[-1:])
            if index<len(self.history):
                self.show_history(self.history[index][0])
        elif cmd==b"RC3:LAST" and page=="home":
            rows=core.history()
            if rows:
                self.show_history(rows[0]["id"])
            else:
                self.cmd("home.pending.val=0")
        elif cmd in (b"RC61:DETAILS",b"RC6:VALUES") and page=="report" and self.report:
            if cmd==b"RC61:DETAILS":
                self.detail_page=int(not self.detail_page)
            elif self.detail_page:
                self.detail_page=self.detail_page%len(self.report_details(self.report))+1
            else:
                self.measurement_offset=(self.measurement_offset+3)%max(3,((len(self.report.get("measurements",[]))+2)//3)*3)
            self.draw_measurements(self.report)
        elif cmd==b"RC71:ENGINEER" and page=="home" and core.phase not in ("guide","waiting","review"):
            self.action("personality.engineering")
            self.cmd("page engineering")
        elif cmd==b"RC71:LOGO" and page=="home" and not core.config["professional"] and core.phase not in ("guide","waiting","review"):
            now=monotonic()
            self.logo_taps=[n for n in self.logo_taps if now-n<3]+[now]
            if len(self.logo_taps)>=5:
                self.logo_taps=[]
                self.cmd("page pet")
        elif cmd==b"RC71:PET" and page=="pet":
            self.action("personality.pet")
        elif len(frame)==1 and frame[0] not in (0,1,0x86,0x87,0x88):
            LOG.debug("Nextion return 0x%02x on %s",frame[0],page)

    def show_history(self,ident):
        result=self.action("report.get",{"report":ident})
        if result["ok"]:
            self.load_report(ident,result["data"])
        else:
            self.cmd("history.pending.val=0")
            self.cmd("home.pending.val=0")

    def refresh_history(self):
        history=self.core.history()[:5]
        self.history=[(row["id"],None) for row in history]
        for i in range(5):
            label=f"#{history[i]['id']} {history[i]['ticket']}" if i<len(history) else self.tr("Keine weiteren Protokolle")
            self.text(f"history.bRow{i}",label,40)

    def picker_event(self,frame):
        cmd,_,data=frame.partition(b"\0")
        p=self.picker
        if cmd.startswith(b"RC61:ROW:") and int(cmd[-1:])<len(p.rows):
            row=p.rows[int(cmd[-1:])]
            if p.mode=="appliance":
                old=self.entry_seen
                if self.action("draft.edit",{"draft":old.get("id"),"changes":{"device":row[0]},
                               "previous":{"device":old.get("device")}})["ok"]:
                    self.set_entry()
                    self.cmd("pRoute.val=2")
            else:
                p.selected=row["id"]
        elif cmd==b"RC61:USE" and p.selected:
            if self.action("person.pick",dict(self.reference(),examiner=p.selected))["ok"]:
                self.cmd("pRoute.val=3")
        elif cmd==b"RC61:STATE" and p.selected:
            chosen=next((r for r in p.rows if r["id"]==p.selected),None)
            if chosen and p.confirm==p.selected:
                self.action("person.active",{"examiner":p.selected,"active":not chosen["active"],"confirmed":True})
                p.confirm=None
            else:
                p.confirm=p.selected
        elif cmd==b"RC61:NAME" and p.edit is not None:
            result=self.action("person.save",{"examiner":p.edit or None,"name":data.decode(ENCODING)})
            if result["ok"]:
                p.selected=result["data"]
                p.edit=None
        elif cmd in (b"RC61:ADD",b"RC61:EDIT"):
            chosen=next((r for r in p.rows if r["id"]==p.selected),None)
            if cmd==b"RC61:ADD" or chosen:
                p.edit=0 if cmd==b"RC61:ADD" else chosen["id"]
                self.text("picker.pEdit",chosen["name"] if p.edit else "",48)
                self.cmd("pRoute.val=1")
        elif cmd in (b"RC61:PREV",b"RC61:NEXT"):
            p.offset=max(0,p.offset+(6 if cmd.endswith(b"NEXT") else -6))
        elif cmd==b"RC61:TOGGLE":
            p.include_inactive=not p.include_inactive
            p.offset=0
        self.rendered=None

    def draw_settings(self):
        s,c=self.settings,self.core
        s.ssid,s.ip=c.ssid,c.ip
        network_job=c.jobs.get("network")
        s.job=network_job if network_job and network_job[0]!="poll" else None
        s.power_job=c.jobs.get("power")
        s.status=c.network_note or "Netzwerke suchen, um WLAN einzurichten."
        s.power_note=c.power_note
        s.printer_note=c.probe_note or c.print_note
        s.apply_display()
        s.draw()

    def sync(self):
        c=self.core
        now=monotonic()
        if now<self.next_sync:
            return
        self.next_sync=now+.12
        page=self.settings.page
        if not page or self.mode_pending:
            return
        if page=="keyboard" and getattr(self,"keyboard_draft",False) and c.draft:
            c.lease("nextion",True,c.draft["id"])
        if self.language!=c.language:
            self.language=c.language
            self.cmd(f"home.lang.val={int(self.language=='en')}")
            self.rendered=None
            if page not in ("home","keyboard"):
                self.cmd("click hLocale,0")
        self.heartbeat()
        draft=c.draft or {}
        stage=c.phase
        required=PAGE_FOR_STAGE.get(stage,"home")
        if page=="home" and not self.entry_conflict:
            self.set_entry()
        if stage=="report" and c.report_id!=self.report_id and page not in ("history","qrpage","report","keyboard",*SETTINGS_PAGES):
            self.load_report(c.report_id,c.report)
        follow=self.follow_on_connect or (self.last_stage!=stage and page in ("entry","guide","importer","tester"))
        follow=follow or (self.last_stage!=stage and page=="home" and stage in ("entry","guide","waiting","review"))
        # A keyboard return must catch up if the other screen advanced while it was open.
        follow=follow or (page in ("entry","guide","importer") and stage in ("guide","waiting","review","report")
                          and self.page_seen==page and self.rendered is None)
        self.follow_on_connect=False
        if follow and required!=page and page!="keyboard" and (draft or required=="home"):
            self.last_stage=stage
            if required=="entry":
                self.set_entry()
            elif required=="report":
                self.load_report(c.report_id,c.report)
            elif required=="guide":
                self.text("guide.eRemarks",draft["remarks"],64)
            self.cmd("page "+required)
            return
        if page!="keyboard":
            self.last_stage=stage
        signature=(page,c.sequence,c.receiver.status,c.language,c.slogan,c.pet_count,c.print_note,
                   c.probe_note,c.network_note,c.ssid,c.ip,c.power_note,tuple(c.access_points),tuple(c.jobs),
                   c.config["professional"],c.milestone,c.metric_generation)
        if page=="engineering":
            self.action("system.info")
        if signature==self.rendered:
            return
        self.rendered=signature
        ref=dict(draft)
        if page=="entry" and stage=="entry":
            if not getattr(self,"entry_conflict",None):
                self.set_entry()
            self.text("entry.tTester",self.tester.status_line(),92)
            self.say("bReportLang","Bericht: {language}",22,language=c.report_language().upper())
            self.m_pending=("report language",self.tr("Bericht: {language}",language=c.report_language().upper()))
            self.cmd("get bReportLang.txt")
            self.presented=ref
        elif page=="guide" and c.guide:
            ref["step"]=c.guide.step
            self.presented=ref
            self.workflow.guide=c.guide
            self.workflow.examiner_id=draft["examiner"]
            self.workflow.draw_guide()
            self.guide_wait=True
            self.cmd("get gCount.val")
        elif page=="importer" and stage=="waiting":
            view=c.snapshot()
            self.presented=ref
            self.text("iStatus",self.tester.status_line(),105)
            body=self.tr(view["import_body"])
            if self.workflow.help:
                body+=self.tr(" Alte Daten nur über «Vorhandene Messung» wählen.")
            self.text("iBody",body,220)
            self.say("iMessage",c.wait_note or "Warte auf eine neue Messung.",105)
            self.cmd(f"iAvailable.val={int(bool(c.slots))}")
            from benning_workflow import ART
            self.cmd(f"iArt.val={ART.index(view['import_art'])}")
            self.cmd("click hArt,0")
        elif page=="tester" and stage=="review":
            t=self.tester
            t.batch,t.slots,t.selected=c.batch,c.slots,c.selected
            t.pending,t.note,t.start_batch=True,c.wait_note,0
            if self.presented.get("record")!= (list(c.identity(c.selected)) if c.selected else None) and c.selected:
                t.offset=c.slots.index(c.selected)//4*4
            ref.update(record=list(c.identity(c.selected)) if c.selected else None,
                       slots=[list(c.identity(row)) for row in c.slots])
            self.presented=ref
            t.draw()
        elif page=="picker":
            self.picker.draw()
        elif page in SETTINGS_PAGES:
            self.draw_settings()
        elif page=="report" and self.report:
            self.draw_measurements(self.report)
            if c.print_note and c.print_note!=self.print_seen:
                self.say("report.tStatus",c.print_note,90)
                self.print_seen=c.print_note
        elif page=="home":
            self.home_hint()
            slogan="" if c.config["professional"] else c.slogan[self.language=="en"]
            if c.milestone and not c.config["professional"] and c.phase not in ("guide","waiting","review"):
                slogan=self.tr("{count} Prüfungen dokumentiert. Danke, Werkstattteam!",count=c.milestone)
            self.text("tSlogan",slogan,90)
        elif page=="pet":
            if c.config["professional"]:
                self.cmd("page home")
            elif c.pet_count is not None:
                self.say("tPets","Streicheleinheiten: {count}",46,count=c.pet_count)
                self.say("tPetReply",c.pet_reply,90)
        elif page=="engineering":
            self.action("system.info")
            info=c.engineering
            if info:
                temps,load,ram,disk,uptime,printer=info["system"]
                exams,passed=info["reports"]
                pets,(requests,tokens,reserved)=info["personality"]
                for i,(label,value) in enumerate((
                    ("CPU-Temperatur",f"{temps} °C"),("CPU-Last (1 min)",load),
                    ("RAM / Datenträger",f"{ram} % / {disk} %"),("Betriebszeit",f"{uptime} s"),
                    ("Backend / HMI-Protokoll",f"v{info['version']} / {PROTOCOL}"),
                    ("Drucker (TCP)",self.tr("Erreichbar" if printer else "Nicht erreichbar")),
                    ("BENNING",self.tester.status_line()),("Prüfungen / bestandene Tests",f"{exams} / {passed}"),
                    ("Gespeicherte Berichte",info["total"]),("Streicheleinheiten",pets),
                    ("OpenAI heute (UTC)",f"{requests} / ~{tokens}"),("Offene Token-Reserve",reserved))):
                    self.text(f"tD{i}",f"{self.tr(label)}: {value}",62)

    def close(self):
        self.core.lease("nextion",False,None)
        self.executor.shutdown(wait=False,cancel_futures=True)
        self.settings.close()
        self.personality.close()
