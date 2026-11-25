"""Portrait Nextion runtime UI. Requires a blank page and font 0 (24 px)."""
import argparse
import json
import time
import serial
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
        self.report = None
        self.status = ""
        self.buttons = []
    def cmd(self, s):
        self.ser.write(s.encode("latin-1", "replace") + END)
        self.ser.flush()
        time.sleep(.025)
    def text(self, x, y, w, h, value, color=WHITE, align=0):
        value = str(value).replace('"', "'").replace("\\", "/")
        value = "".join(c for c in value if c.isprintable())[:max(1,w//14)]
        self.cmd(f'xstr {x},{y},{w},{h},0,{color},{BG},{align},1,3,"{value}"')
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
            for row,keys in enumerate(("1234567890","QWERTZUIOP","ASDFGHJKL","YXCVBNM-")):
                for i,k in enumerate(keys):
                    self.button(15+i*45,205+row*65,42,58,k,lambda k=k:self.key(k))
            self.button(15,475,140,65,"Leer",lambda:self.key(" "))
            self.button(165,475,140,65,"Loeschen",lambda:self.key(None))
            self.button(315,475,150,65,"OK",lambda:self.go("entry"),GREEN)
        elif p in ("report","test"):
            self.text(24,140,432,45,"SIMULATION - KEINE PRUEFUNG",AMBER)
            if p == "report" and self.report:
                self.text(24,205,432,40,"Nr: "+self.report["ticket"])
                self.text(24,255,432,40,"Geraet: "+self.report["device"])
            self.text(24,330,432,40,"Ergebnis: NICHT GEPRUEFT")
            self.button(24,440,432,90,"Testbeleg drucken",self.print_report,GREEN)
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
    def keyboard(self,field):
        self.field=field
        self.go("keyboard")
    def key(self,k):
        v=getattr(self,self.field)
        setattr(self,self.field,v[:-1] if k is None else (v+k)[:30])
        self.cmd(f"fill 24,125,432,55,{BG}")
        self.text(24,125,432,55,getattr(self,self.field) or "_")
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
        except OSError:
            self.status="Drucker nicht erreichbar"
        self.draw()
    def run(self):
        self.cmd("bkcmd=0")
        self.cmd("sendxy=1")
        self.draw()
        buf=bytearray()
        while True:
            chunk=self.ser.read(self.ser.in_waiting or 1)
            buf.extend(chunk)
            while END in buf:
                frame,_,rest=buf.partition(END)
                buf=bytearray(rest)
                if len(frame)==6 and frame[0]==0x67 and frame[5]==0:
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
    a=p.parse_args()
    with serial.Serial(a.port,a.baud,timeout=.2,write_timeout=3) as ser:
        UI(ser,a.host,a.db).run()
if __name__=="__main__":main()
