"""Portrait Nextion runtime UI. Requires a blank page and font 0 (24 px)."""
import argparse
import json
import time
import serial
from report_web import publish, start_server
from station import simulate, receipt, send, database

END = b"\xff\xff\xff"
BG, PANEL, GREEN, WHITE, MUTED, AMBER = 4324, 8583, 11243, 65535, 48631, 64800

class UI:
    def __init__(self, ser, host, db):
        self.ser, self.host, self.db = ser, host, db
        self.page = "home"
        self.ticket = ""
        self.device = ""
        self.field = "ticket"
        self.shift = False
        self.caps = False
        self.symbols = False
        self.original = ""
        self.report = None
        self.status = ""
        self.native = False
        self.base_url = ""
        self.buttons = []
    def cmd(self, s):
        print("TX:", s, flush=True)
        self.ser.write(s.encode("latin-1", "replace") + END)
        self.ser.flush()
        time.sleep(.025)
    def text(self, x, y, w, h, value, color=WHITE, align=0):
        value = str(value).replace('"', "'").replace("\\", "/")
        value = "".join(c for c in value if c.isprintable())[:max(1,w//14)]
        self.cmd(f'xstr {x},{y},{w},{h},0,{color},{BG},{align},1,1,"{value}"')
    def button(self, x, y, w, h, label, action, color=PANEL):
        self.cmd(f"fill {x},{y},{w},{h},{color}")
        self.text(x,y,w,h,label,align=1)
        self.buttons.append((x,y,w,h,action))
    def go(self, page):
        self.page = page
        self.status = ""
        self.draw()
    def draw(self):
        self.buttons = []
        self.cmd(f"cls {BG}")
        self.text(20,20,440,44,"Repair Cafe Riehen",align=1)
        self.text(20,70,440,30,"FMI | PRUEFSTATION",MUTED,1)
        self.cmd(f"line 20,112,460,112,{MUTED}")
        p = self.page
        if p == "home":
            self.text(24,140,432,40,"Pruefgeraet: Simulator",AMBER)
            self.text(24,185,432,40,"Drucker: TCP / 9100")
            self.button(24,260,432,100,"Neues Protokoll",lambda:self.go("entry"),GREEN)
            self.button(24,380,432,80,"Verlauf",lambda:self.go("history"))
            self.button(24,480,432,80,"Einstellungen",lambda:self.go("settings"))
            self.button(24,580,432,80,"Testbeleg",lambda:self.go("test"))
        elif p == "entry":
            self.text(24,135,432,40,"Reparaturnummer")
            self.button(24,180,432,65,self.ticket or "Eingeben",lambda:self.keyboard("ticket"))
            self.text(24,265,432,40,"Geraet")
            self.button(24,310,432,65,self.device or "Eingeben",lambda:self.keyboard("device"))
            self.button(24,440,432,80,"Demo-Bericht erstellen",self.create,GREEN)
        elif p == "keyboard":
            self.text(24,125,432,55,getattr(self,self.field) or "_")
            rows = ("1234567890","!@#$%&*()+",".,:;/?=_","-[]{}") if self.symbols else ("1234567890","qwertzuiop","asdfghjkl","yxcvbnm")
            for row,keys in enumerate(rows):
                for i,k in enumerate(keys):
                    if not self.symbols and (self.shift != self.caps): k=k.upper()
                    self.button(15+i*45,200+row*62,42,56,k,lambda k=k:self.key(k))
            for i,k in enumerate("äöüß"):
                if self.shift != self.caps: k=k.upper()
                self.button(15+i*60,452,56,50,k,lambda k=k:self.key(k))
            self.button(260,452,95,50,"Shift",self.toggle_shift,GREEN if self.shift else PANEL)
            self.button(360,452,105,50,"Caps",self.toggle_caps,GREEN if self.caps else PANEL)
            self.button(15,515,105,60,"123/ABC",self.toggle_symbols)
            self.button(125,515,205,60,"Leer",lambda:self.key(" "))
            self.button(335,515,130,60,"Zurueck",lambda:self.key(None))
            self.button(15,590,215,60,"Abbruch",self.cancel_keyboard)
            self.button(240,590,225,60,"OK",lambda:self.go("entry"),GREEN)
        elif p in ("report","test"):
            self.text(24,140,432,45,"SIMULATION - KEINE PRUEFUNG",AMBER)
            if p == "report" and self.report:
                self.text(24,205,432,40,"Nr: "+self.report["ticket"])
                self.text(24,255,432,40,"Geraet: "+self.report["device"])
            self.text(24,330,432,40,"Ergebnis: NICHT GEPRUEFT")
            self.button(24,440,432,90,"Testbeleg drucken",self.print_report,GREEN)
            if p == "report" and self.base_url:
                self.button(24,550,432,85,"Digitales Protokoll",self.show_qr)
        elif p == "history":
            with database(self.db) as db:
                rows=db.execute("SELECT id,data FROM reports ORDER BY id DESC LIMIT 5").fetchall()
            if not rows:self.text(24,150,432,50,"Keine Berichte")
            for i,(ident,data) in enumerate(rows):
                r=json.loads(data)
                self.button(24,150+i*85,432,70,f'{ident}: {r["ticket"]}',lambda r=r:self.open_report(r))
        elif p == "settings":
            self.text(24,150,432,40,"Drucker: "+self.host)
            self.text(24,200,432,40,"Port: 9100")
            self.text(24,250,432,40,"Treiber: Simulator")
            self.text(24,300,432,40,"UART: "+str(self.ser.baudrate))
        if self.status:self.text(20,665,440,45,self.status,AMBER)
        if p!="home":self.button(24,725,432,55,"Hauptmenue",lambda:self.go("home"))
        else:self.text(24,735,432,40,"v0.1 | OFFLINE",MUTED,1)
    def show_qr(self):
        url=publish(self.db,self.report,self.base_url)
        self.page="qr"
        self.buttons=[]
        self.cmd("page qrpage")
        self.cmd(f'qrReport.txt="{url}"')
    def keyboard(self,field):
        self.field=field
        self.original=getattr(self,field)
        if self.native:
            self.page="native_keyboard"
            self.buttons=[]
            self.cmd("page page0")
            value=self.original.replace(chr(34),chr(39)).replace(chr(92),"/")
            self.cmd(f'tInput.txt="{value}"')
            self.cmd("click tInput,1")
            self.cmd("click tInput,0")
            return
        self.shift=False
        self.caps=False
        self.symbols=False
        self.go("keyboard")
    def toggle_shift(self):
        self.shift=not self.shift
        self.draw()
    def toggle_caps(self):
        self.caps=not self.caps
        self.draw()
    def toggle_symbols(self):
        self.symbols=not self.symbols
        self.draw()
    def cancel_keyboard(self):
        setattr(self,self.field,self.original)
        self.go("entry")
    def key(self,k):
        v=getattr(self,self.field)
        setattr(self,self.field,v[:-1] if k is None else (v+k)[:30])
        self.cmd(f"fill 24,125,432,55,{BG}")
        self.text(24,125,432,55,getattr(self,self.field) or "_")
        if self.shift and k is not None:
            self.shift=False
            self.draw()
    def create(self):
        if not self.ticket.strip() or not self.device.strip():
            self.status="Bitte beide Felder ausfuellen"
            self.draw()
            return
        self.report=simulate(self.ticket,self.device)
        with database(self.db) as db:
            db.execute("INSERT INTO reports(data) VALUES (?)",(json.dumps(self.report),))
        self.go("report")
    def open_report(self,r):
        self.report=r
        self.go("report")
    def print_report(self):
        try:
            r=self.report if self.page=="report" else simulate("TEST","Druckertest")
            send(self.host,9100,receipt(r))
            self.status="Druckdaten gesendet"
        except OSError as exc:
            print("Printer error:", exc, flush=True)
            self.status="Drucker nicht erreichbar"
        self.draw()
    def run(self):
        self.ser.reset_input_buffer()
        self.ser.write(END)
        self.cmd("bkcmd=3")
        self.cmd("sleep=0")
        self.cmd("dim=100")
        self.cmd("page page0")
        self.cmd("sendxy=1")
        self.draw()
        print("Initial drawing sent; listening for responses and touch.", flush=True)
        buf=bytearray()
        while True:
            chunk=self.ser.read(self.ser.in_waiting or 1)
            buf.extend(chunk)
            while END in buf:
                frame,_,rest=buf.partition(END)
                buf=bytearray(rest)
                print("RX:", frame.hex(" "), flush=True)
                if frame==b"RCBACK" and self.page=="qr":
                    self.cmd("page page0")
                    self.go("report")
                elif frame==b"RCKEY" and self.page=="native_keyboard":
                    self.cmd("get tInput.txt")
                elif frame[:1]==b"\x70" and self.page=="native_keyboard":
                    setattr(self,self.field,bytes(frame[1:]).decode("latin-1")[:64])
                    self.go("entry")
                elif len(frame)==6 and frame[0]==0x67 and frame[5]==0:
                    x=int.from_bytes(frame[1:3],"big")
                    y=int.from_bytes(frame[3:5],"big")
                    for bx,by,w,h,action in self.buttons:
                        if bx<=x<bx+w and by<=y<by+h:
                            action()
                            break
            if len(buf)>4096:buf.clear()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--port",default="/dev/serial0")
    p.add_argument("--baud",type=int,default=9600)
    p.add_argument("--host",default="169.254.223.252")
    p.add_argument("--db",default="reports.sqlite3")
    p.add_argument("--native-keyboard",action="store_true")
    p.add_argument("--report-url",help="Reachable LAN URL, e.g. http://192.168.200.241:8080")
    p.add_argument("--web-port",type=int,default=8080)
    p.add_argument("--fast",action="store_true",help="Switch display from specified baud to 115200 for this session")
    a=p.parse_args()
    with serial.Serial(a.port,a.baud,timeout=.2,write_timeout=3) as ser:
        if a.fast and a.baud != 115200:
            ser.write(b"baud=115200"+END)
            ser.flush()
            time.sleep(.3)
            ser.baudrate=115200
            ser.reset_input_buffer()
            ser.write(b"connect"+END)
            ser.flush()
            time.sleep(.3)
            response=ser.read(256)
            if b"comok" not in response:
                raise SystemExit("Fast baud handshake failed; power-cycle Nextion and retry without --fast")
        ui=UI(ser,a.host,a.db)
        ui.native=a.native_keyboard
        if a.report_url:
            ui.base_url=a.report_url.rstrip("/")
            start_server(a.db,a.web_port)
        ui.run()
if __name__=="__main__":main()
