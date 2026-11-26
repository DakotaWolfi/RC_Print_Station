"""Generate the candidate's native pages and flash-resident artwork.

Run with the build environment, then run nxwright build/check. The original
Editor project in hmi/reference is never an output of this script.
"""
from pathlib import Path
import json
import tomli_w
from PIL import Image, ImageDraw, ImageFont
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.truetype import TrueTypeFont

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "hmi/native"
DESIGN = ROOT / "hmi/design"
BG, PANEL, EDGE = "#101923", "#1d2c3a", "#344858"
WHITE, MUTED, ORANGE, CYAN = "#f5f6f7", "#afc2d0", "#ff941f", "#42d9dd"
WARN = "#ffd08a"
PAGES = ["home", "entry", "keyboard", "report", "qrpage", "history", "settings",
         "wifi", "wjoin", "printer", "receipt", "system", "power", "tester"]
FLAT = set(PAGES[6:]) | {"entry","report"}

# Swiss letter order, direct umlauts, plus two symbol banks. A touchscreen
# shift intentionally provides uppercase umlauts directly (Ä/Ö/Ü).
LOWER = [list("1234567890'^"), list("qwertzuiopüè"), list("asdfghjklöäé"),
         list("yxcvbnm,.-")]
UPPER = [list('+"*ç%&/()=?`'), list("QWERTZUIOPÜÈ"), list("ASDFGHJKLÖÄÉ"),
         list("YXCVBNM;:_")]
SYMBOL1 = [list("1234567890+-"), list("@#%&*()[]{}="),
           list("/\\|<>_~^`'\"+"), list(".,:;!?€$£§")]
SYMBOL2 = [list("1234567890+-"), list("äöüÄÖÜéèàçêô"),
           list("ÉÈÀÇÊÔáíóúâû"), list("°²³µ©®«»!? ")[:10]]


def quote(text):
    return '"' + text.replace('\\', '\\\\').replace('"', '\\"') + '"'


def emit(message):
    return [f"prints {quote(message)},0", "printh ff ff ff"]


def event(name, lines):
    return f"on {name}:\n" + "".join("  " + line + "\n" for line in lines) + "\n"


class Page:
    def __init__(self, name, title, subtitle):
        self.name = name
        self.doc = {"page": {"name": name, "type": "page", "x": 0, "y": 0,
                             "w": 480, "h": 800, "bco": BG}, "component": []}
        self.code = ""
        self.art = Image.new("RGB", (960, 1600), BG)
        self.draw = ImageDraw.Draw(self.art)
        banner = Image.open(DESIGN / "brand.png").convert("RGB")
        self.art.paste(banner.resize((960, 320), Image.Resampling.LANCZOS), (0, 0))
        self.draw.line((48, 326, 912, 326), fill=EDGE, width=2)
        self.label(24, 183, title, 30, WHITE)
        self.label(24, 228, subtitle, 17, MUTED)
        self.label(24, 777, "FMI  /  REPAIR CAFÉ RIEHEN", 12, MUTED)
        self.label(390, 777, "v0.5 RC", 12, MUTED)
        self.shapes = []
        self.add("pBg", "picture", x=0, y=0, w=480, h=800, pic=name)

    def label(self, x, y, text, size=20, color=WHITE):
        font = ImageFont.truetype(str(DESIGN / "typeface/NotoSans-Regular.ttf"), size * 2)
        self.draw.text((x * 2, y * 2), text, font=font, fill=color, anchor="lt")

    def box(self, x, y, w, h, color=PANEL, radius=12, outline=None):
        rect = (x * 2, y * 2, (x + w) * 2 - 1, (y + h) * 2 - 1)
        self.draw.rounded_rectangle(rect, radius=radius * 2, fill=color,
                                    outline=outline, width=2)

    def add(self, name, kind, **attrs):
        self.doc["component"].append(dict(name=name, type=kind, **attrs))

    def var(self, name, value=0, global_=True):
        self.add(name, "variable", val=value, vscope=int(global_))

    def text(self, name, x, y, w, h, value="", size=24, color=WHITE,
             bg=PANEL, limit=64, global_=False, align=0, **attrs):
        self.add(name, "text", x=x, y=y, w=w, h=h, txt=value, txt_maxl=limit,
                 font=f"UI{size}", pco=color, bco=bg, borderw=0,
                 xcen=align, ycen=1, vscope=int(global_), **attrs)

    def button(self, name, x, y, w, h, label, lines, primary=False, size=24):
        color = ORANGE if primary else PANEL
        self.box(x, y, w, h, color)
        if self.name in FLAT:
            self.add(name,"button",x=x,y=y,w=w,h=h,sta=1,style=0,borderw=0,
                     font=f"UI{size}",bco=color,bco2="#ffc071" if primary else "#365164",
                     pco=BG if primary else WHITE,pco2=BG if primary else WHITE,
                     txt=label,txt_maxl=max(len(label),1),isbr=0)
            self.code += event(name+".up",lines)
            return
        self.shapes.append((x, y, w, h, primary))
        self.add(name, "button", x=x, y=y, w=w, h=h, sta=0,
                 picc=self.name, picc2=self.name + "_press", style=0, borderw=0,
                 font=f"UI{size}", pco=BG if primary else WHITE,
                 pco2=BG if primary else WHITE, txt=label,
                 txt_maxl=max(len(label), 1), isbr=0)
        self.code += event(name + ".up", lines)

    def on(self, name, lines):
        self.code += event(name, lines)

    def watchdog(self):
        self.add("tmLink", "timer", tim=1000, en=1)
        self.on("tmLink.timer", ["home.age.val++", "if(home.age.val>6)", "{",
                                "home.online.val=0", 'home.tLink.txt="Host nicht verbunden"', "}"])

    def flow(self, conditions):
        self.add("tmFlow", "timer", tim=200, en=1)
        self.on("tmFlow.timer", conditions)

    def save(self):
        self.watchdog()
        load = f"on {self.name}.loadend:\n"
        if load in self.code:
            self.code = self.code.replace(load,load+"  sendme\n",1)
        else:
            self.on(self.name+".loadend",["sendme"])
        (APP / f"pages/{self.name}.page.toml").write_text(tomli_w.dumps(self.doc), encoding="utf-8")
        (APP / f"pages/{self.name}.nx").write_text(self.code.rstrip()+"\n", encoding="utf-8")
        self.art.resize((480, 800), Image.Resampling.LANCZOS).save(APP / f"pictures/{self.name}.png")
        if self.name in FLAT:
            return
        pressed = self.art.copy()
        draw = ImageDraw.Draw(pressed)
        for x, y, w, h, primary in self.shapes:
            draw.rounded_rectangle((x*2, y*2, (x+w)*2-1, (y+h)*2-1), radius=24,
                                   fill="#ffc071" if primary else "#365164")
        pressed.resize((480, 800), Image.Resampling.LANCZOS).save(APP / f"pictures/{self.name}_press.png")


def make_home():
    p = Page("home", "Reparieren. Weitergeben.", "Ein zweites Leben beginnt mit einer Reparatur.")
    p.var("proto", 5)
    for name in ("online", "age", "pending"):
        p.var(name)
    p.box(24, 273, 432, 115)
    p.label(40, 289, "PRÜFPROTOKOLLE", 14, ORANGE)
    p.label(40, 315, "BENNING ST 725 / Repair Café", 18, WARN)
    p.text("tLink", 40, 348, 400, 27, "Host nicht verbunden", size=20,
           color=MUTED, global_=True, limit=32)
    p.button("bNew", 24, 412, 432, 82, "Neues Protokoll", [
        'entry.tTicket.txt=""', 'entry.tDevice.txt=""', 'entry.tStatus.txt=""',
        'entry.tSlot.txt=""',"entry.phase.val=0","entry.useLast.val=1",
        "entry.busy.val=0",*emit("RC5:NEW"),"page entry"],True,28)
    p.button("bHistory", 24, 510, 210, 72, "Verlauf", ["page history"])
    p.button("bSettings", 246, 510, 210, 72, "Station", ["page settings"])
    p.button("bLast", 24, 598, 432, 68, "Letztes Protokoll öffnen", [
        "if(home.online.val==1)", "{", "report.ready.val=0", "pending.val=1",
        *emit("RC3:LAST"), "}else", "{", 'tHint.txt="Bitte Host-Verbindung prüfen."', "}"])
    p.text("tHint", 24, 680, 432, 40, "", size=20, color=WARN, bg=BG,
           global_=True, limit=64)
    p.text("tClock", 24, 733, 432, 28, "", size=20, color=MUTED, bg=BG,
           global_=True, limit=24)
    p.flow(["if(pending.val==1&&report.ready.val==1)", "{", "pending.val=0", "page report", "}",
            "if(pending.val==1&&online.val==0)", "{", "pending.val=0",
            'tHint.txt="Host nicht verbunden. Bitte erneut versuchen."', "}"])
    p.save()


def make_entry():
    p = Page("entry", "Prüfung erfassen", "01  Angaben   /   02  Messung   /   03  Ausgabe")
    for name,initial in (("field",0),("busy",0),("phase",0),("useLast",1),("sim",0)):
        p.var(name,initial)
    for field,(name,label,y,w,limit) in enumerate((
            ("tTicket","PRÜFNUMMER",258,432,32),
            ("tDevice","GERÄTEBESCHREIBUNG",345,432,64),
            ("tSlot","PRÜFSPEICHERNUMMER",440,140,3))):
        p.label(24,y,label,14,CYAN)
        p.box(24,y+22,w,52,outline=EDGE)
        p.text(name,34,y+24,w-20,48,global_=True,limit=limit,isbr=1,size=20)
        p.add(f"hEdit{field}","hotspot",x=24,y=y+22,w=w,h=52)
        condition="busy.val==0" if field<2 else "busy.val==0&&useLast.val==0&&sim.val==0"
        p.on(f"hEdit{field}.up",[f"if({condition})","{",f"field.val={field if field<2 else 5}",
                                  "page keyboard","}"])
    p.add("cLast","checkbox",x=185,y=467,w=34,h=34,bco=PANEL,pco=ORANGE,borderc=EDGE,val=1)
    p.label(228,475,"Letzten Speicherplatz verwenden",14)
    p.on("cLast.up",["useLast.val=cLast.val","if(useLast.val==1)","{",*emit("RC5:AUTOON"),
                     "}else","{",*emit("RC5:AUTOOFF"),"}"])
    p.button("bPhase",24,523,432,50,"Eingangsprüfung",[
        "phase.val++","if(phase.val>2)","{","phase.val=0","}","click hPhase,0"],size=20)
    p.doc["component"][-1]["txt_maxl"]=20
    p.add("hPhase","hotspot",x=0,y=0,w=2,h=2)
    p.on("hPhase.up",["if(phase.val==0)","{",'bPhase.txt="Eingangsprüfung"',
                       "}else if(phase.val==1)","{",'bPhase.txt="Zwischenprüfung"',
                       "}else","{",'bPhase.txt="Ausgangsprüfung"',"}"])
    p.on("entry.loadend",["cLast.val=useLast.val","click hPhase,0","if(sim.val==1)","{",
                           'bCreate.txt="Simulation erstellen"',"}"])
    p.text("tTester",24,580,432,37,"Warte auf BENNING-Host.",size=20,
           color=MUTED,bg=BG,global_=True,limit=92,isbr=1)
    p.text("tStatus",24,620,432,42,"",size=20,color=WARN,bg=BG,global_=True,limit=80,isbr=1)
    p.add("vArg","variable",sta=1,txt="",txt_maxl=2)
    p.button("bCreate",24,667,270,49,"Messung prüfen",[
        "if(busy.val==0)", "{", 'if(tTicket.txt==""||tDevice.txt=="")', "{",
        'tStatus.txt="Bitte beide Felder ausfüllen."', "}else if(home.online.val==0)", "{",
        'tStatus.txt="Host nicht verbunden. Eingaben bleiben erhalten."', "}else", "{",
        "report.ready.val=0","if(sim.val==1)","{","busy.val=1",'prints "RC3:CREATE",0',
        "}else","{",'prints "RC5:REVIEW",0',"}",
        "printh 00","prints tTicket.txt,0","printh 00","prints tDevice.txt,0",
        "if(sim.val==0)","{","printh 00","prints tSlot.txt,0","printh 00",
        "covx phase.val,vArg.txt,0,0","prints vArg.txt,0","printh 00",
        "covx useLast.val,vArg.txt,0,0","prints vArg.txt,0","}",
        "printh ff ff ff","if(sim.val==0)","{","page tester","}","}","}"],True,20)
    p.doc["component"][-1]["txt_maxl"]=24
    p.button("bTester",304,667,152,49,"Speicher",[*emit("RC5:BROWSE"),"page tester"],size=20)
    p.button("bBack",24,725,432,41,"Zurück",["if(busy.val==0)","{","page home","}"],size=20)
    p.flow(["if(busy.val==1&&report.ready.val==1)","{","busy.val=0","page report","}",
            "if(busy.val==1&&home.online.val==0)","{","busy.val=0",
            'tStatus.txt="Host-Verbindung verloren. Bitte erneut versuchen."',"}"])
    p.save()


def make_keyboard():
    p = Page("keyboard", "Texteingabe", "Schweiz · QWERTZ   /   direkt auf dem Display")
    for name in ("mode", "shift", "caps", "count", "limit"):
        p.var(name, global_=False)
    p.add("secret","variable",sta=1,txt="",txt_maxl=64)
    p.add("vKey","variable",sta=1,txt="",txt_maxl=1)
    p.add("hAdd","hotspot",x=4,y=0,w=2,h=2)
    p.on("hAdd.up",["strlen input.txt,count.val","if(count.val<limit.val)","{",
                    "if(entry.field.val==2)","{","secret.txt+=vKey.txt",'input.txt+="*"',
                    "}else","{","input.txt+=vKey.txt","}","}",'vKey.txt=""',"click hCount,0"])
    p.text("tField",16,271,448,28,"Eingabe",size=20,color=CYAN,bg=BG,limit=24)
    p.box(16, 303, 448, 83, outline=EDGE)
    p.text("input", 28, 310, 424, 67, size=20, limit=64, isbr=1)
    p.text("tHint", 16, 389, 448, 27, "", size=20, color=MUTED, bg=BG, limit=56)
    coords = []
    for row in range(4):
        for col in range(12):
            if row == 3 and col in (0,11):
                continue
            coords.append((row,col))
    keys = []
    for index, (row,col) in enumerate(coords):
        name = f"k{index}"
        keys.append(name)
        char = LOWER[row][col if row != 3 else col - 1]
        p.add(name, "button", x=8+39*col, y=431+56*row, w=36, h=50,
              style=0, borderw=0, font="UI24", bco=PANEL, bco2=ORANGE,
              pco=WHITE, pco2=BG, txt=char, txt_maxl=1)
        p.on(name+".up", [f"vKey.txt={name}.txt","click hAdd,0","if(shift.val==1)","{",
                          "shift.val=0","click hLayout,0","}"])
    p.add("hLayout", "hotspot", x=0, y=0, w=2, h=2)
    layout = []
    for mode, bank in enumerate((LOWER, SYMBOL1, SYMBOL2)):
        layout += [f"if(mode.val=={mode})", "{"]
        for index, (row,col) in enumerate(coords):
            char = bank[row][col if row != 3 else col-1]
            if mode == 0:
                upper = UPPER[row][col if row != 3 else col-1]
                condition = "shift.val!=caps.val" if char.isalpha() else "shift.val==1"
                layout += [f"if({condition})", "{", f"k{index}.txt={quote(upper)}",
                           "}else", "{", f"k{index}.txt={quote(char)}", "}"]
            else:
                layout += [f"k{index}.txt={quote(char)}"]
        layout += ["}"]
    layout += ["if(shift.val==1)", "{", f"bShift.bco={rgb565(ORANGE)}",f"bShift.pco={rgb565(BG)}", "}else", "{",
               f"bShift.bco={rgb565(PANEL)}",f"bShift.pco={rgb565(WHITE)}", "}", "if(caps.val==1)", "{",
               f"bCaps.bco={rgb565(ORANGE)}",f"bCaps.pco={rgb565(BG)}", "}else", "{",
               f"bCaps.bco={rgb565(PANEL)}",f"bCaps.pco={rgb565(WHITE)}", "}",
               "if(mode.val==0)", "{", 'bMode.txt="123"', "}else if(mode.val==1)", "{",
               'bMode.txt="é / §"', "}else", "{", 'bMode.txt="ABC"', "}"]
    p.on("hLayout.up", layout)
    p.add("hCount", "hotspot", x=2, y=0, w=2, h=2)
    p.on("hCount.up", ["strlen input.txt,count.val", "covx count.val,tHint.txt,0,0",
                         'tHint.txt+=" Zeichen  /  max. "', "covx limit.val,tLimit.txt,0,0",
                         "tHint.txt+=tLimit.txt"])
    p.add("tLimit", "variable", sta=1, txt="", txt_maxl=2)
    # Control keys are native buttons too. Their fills do not need a bitmap.
    controls = [
        ("bShift",8,599,36,50,"Aa",["shift.val=1-shift.val", "mode.val=0", "click hLayout,0"],20),
        ("bDel",437,599,36,50,"<",['input.txt-=1','secret.txt-=1',"click hCount,0"],24),
        ("bMode",8,660,74,50,"123",["mode.val++","if(mode.val>2)","{","mode.val=0","}","click hLayout,0"],20),
        ("bCaps",88,660,74,50,"Caps",["caps.val=1-caps.val","shift.val=0","mode.val=0","click hLayout,0"],20),
        ("bSpace",168,660,204,50,"Leerzeichen",['vKey.txt=" "',"click hAdd,0"],20),
        ("bClear",378,660,94,50,"Leeren",['input.txt=""','secret.txt=""',"click hCount,0"],20)]
    for name,x,y,w,h,label,lines,size in controls:
        p.add(name,"button",x=x,y=y,w=w,h=h,style=0,borderw=0,font=f"UI{size}",
              bco=PANEL,bco2=ORANGE,pco=WHITE,pco2=BG,txt=label,txt_maxl=max(len(label),5))
        p.on(name+".up", lines)
    p.button("bCancel",16,725,212,44,"Abbrechen",['secret.txt=""','input.txt=""',
        "if(entry.field.val==2)","{","page wjoin","}else if(entry.field.val>2&&entry.field.val<5)","{","page printer",
        "}else","{","page entry","}"],size=20)
    p.button("bOK",240,725,224,44,"Übernehmen",[
        "if(entry.field.val==2)","{","if(home.online.val==1)","{",
        'prints "RC4:PASS",0',"printh 00","prints secret.txt,0","printh ff ff ff","}",
        'secret.txt=""','input.txt=""',"page wjoin","}else if(entry.field.val>2&&entry.field.val<5)","{",
        "if(home.online.val==1)","{","if(entry.field.val==3)","{",'prints "RC4:IP",0',"}else","{",
        'prints "RC4:PORT",0',"}","printh 00","prints input.txt,0","printh ff ff ff","}",
        'input.txt=""',"page printer","}else","{","if(entry.field.val==0)","{",
        "entry.tTicket.txt=input.txt","}else if(entry.field.val==1)","{",
        "entry.tDevice.txt=input.txt","}else","{","entry.tSlot.txt=input.txt","}",
        'entry.tStatus.txt=""',"page entry","}"],True,20)
    p.on("keyboard.unload",['secret.txt=""','vKey.txt=""','input.txt=""'])
    p.on("keyboard.loadend", ["mode.val=0","shift.val=0","caps.val=0",'secret.txt=""',
        "if(entry.field.val==0)","{",
        "input.txt=entry.tTicket.txt",'tField.txt="Prüfnummer"',"limit.val=32","}else if(entry.field.val==1)","{",
        "input.txt=entry.tDevice.txt",'tField.txt="Gerätebeschreibung"',"limit.val=64",
        "}else if(entry.field.val==2)","{",'input.txt=""','tField.txt="WLAN-Passwort"',"limit.val=64",
        "}else if(entry.field.val==3)","{","input.txt=settings.editText.txt",
        'tField.txt="Drucker-IPv4-Adresse"',"limit.val=15","}else if(entry.field.val==4)","{",
        "input.txt=settings.editText.txt",'tField.txt="Drucker-TCP-Port"',"limit.val=5",
        "}else","{","input.txt=entry.tSlot.txt",'tField.txt="Prüfspeichernummer"',"limit.val=3","}",'settings.editText.txt=""',
        "click hLayout,0","click hCount,0"])
    p.save()


def rgb565(color):
    n = int(color[1:],16)
    return ((n>>19)<<11)|(((n>>10)&63)<<5)|((n>>3)&31)


def make_report():
    p = Page("report", "Prüfprotokoll", "02  Bericht   /   Vorschau vor der Ausgabe")
    p.var("ready")
    p.var("printing")
    p.box(24,273,432,78,"#3a2c20")
    p.text("tOrigin",40,283,402,30,"",size=20,color=WARN,bg="#3a2c20",global_=True,limit=45)
    p.text("tResult",40,317,402,28,"",size=24,color=WHITE,bg="#3a2c20",global_=True,limit=40)
    p.label(24,366,"PRÜFNUMMER",14,CYAN)
    p.text("tTicket",24,384,432,38,"",global_=True,limit=32,bg=BG,size=20,isbr=1)
    p.label(24,428,"GERÄT",14,CYAN)
    p.text("tDevice",24,445,432,65,"",global_=True,limit=64,bg=BG,isbr=1,size=20)
    p.text("tMeta",24,512,432,38,"",size=20,color=CYAN,bg=BG,global_=True,limit=64,isbr=1)
    p.text("tDate",24,550,432,28,"",size=20,color=MUTED,bg=BG,global_=True,limit=24)
    p.text("tStatus",24,581,432,46,"Keine Messwerte vorhanden.",size=20,color=WARN,
           bg=BG,global_=True,limit=80,isbr=1)
    p.button("bPrint",24,641,210,64,"Beleg drucken",[
        "if(home.online.val==1&&ready.val==1&&printing.val==0)","{","printing.val=1",
        'tStatus.txt="Druckdaten werden gesendet ..."',*emit("RC3:PRINT"),"}else if(home.online.val==0)","{",
        'tStatus.txt="Host nicht verbunden. Druck nicht gesendet."',"}else if(ready.val==0)","{",
        'tStatus.txt="Bitte Bericht erneut im Verlauf öffnen."',"}"] ,True,20)
    p.button("bQR",246,641,210,64,"PDF / QR-Code",[
        "if(ready.val==1)","{","qrpage.qReady.val=0","page qrpage","}"],size=20)
    p.button("bHome",24,719,432,42,"Hauptmenü",["page home"],size=20)
    p.flow(["if(printing.val==1&&home.online.val==0)","{","printing.val=0",
        'tStatus.txt="Verbindung verloren. Beleg vor erneutem Druck prüfen."',"}"])
    p.save()


def make_qr():
    p = Page("qrpage", "Protokoll mitnehmen", "03  Digitales PDF   /   im lokalen Netzwerk")
    p.var("qReady")
    p.var("shown",global_=False)
    p.box(60,270,360,360,"#ffffff")
    p.add("qrReport","qr-code",x=90,y=300,w=300,h=300,txt="",txt_maxl=78,
          vscope=1,bco="#ffffff",pco="#000000")
    p.text("tNote",24,634,432,64,"PDF-Link wird vorbereitet ...",size=20,color=WHITE,
           bg=BG,global_=True,limit=100,isbr=1,align=1)
    p.text("tKind",24,697,432,29,"",size=20,color=WARN,bg=BG,global_=True,limit=56)
    p.button("bBack",24,733,432,34,"Zurück zum Bericht",["page report"],size=20)
    p.on("qrpage.loadend",["shown.val=0","vis qrReport,0",*emit("RC3:QR")])
    p.flow(["if(qReady.val==1&&shown.val==0)","{","vis qrReport,1","shown.val=1","}",
            "if(qReady.val!=1&&shown.val==1)","{","vis qrReport,0","shown.val=0","}",
            "if(home.online.val==0)","{","qReady.val=2",
            'tNote.txt="Host nicht verbunden. Bitte Verbindung prüfen."',"}"])
    p.save()


def make_history():
    p = Page("history", "Protokollverlauf", "Die fünf zuletzt gespeicherten Protokolle.")
    p.var("pending")
    for i in range(5):
        p.button(f"bRow{i}",24,275+i*72,432,60,"Laden ...",[
            "if(home.online.val==1&&pending.val==0)","{","pending.val=1","report.ready.val=0",
            *emit(f"RC3:OPEN:{i}"),"}"],size=20)
        p.doc["component"][-1]["vscope"]=1
        p.doc["component"][-1]["txt_maxl"]=40
    p.text("tStatus",24,643,432,48,"",size=20,color=WARN,bg=BG,global_=True,limit=80,isbr=1)
    p.button("bBack",24,715,432,52,"Hauptmenü",["page home"],size=20)
    p.on("history.loadend",["pending.val=0",*emit("RC3:HISTORY")])
    p.flow(["if(pending.val==1&&report.ready.val==1)","{","pending.val=0","page report","}",
            "if(pending.val==1&&home.online.val==0)","{","pending.val=0",
            'tStatus.txt="Host nicht verbunden. Bitte erneut versuchen."',"}"])
    p.save()


def active_action(action):
    return ["if(home.online.val==1)","{",*emit("RC4:"+action),"}"]


def back(p, target="settings"):
    p.button("bBack",24,715,432,52,"Zurück",["page "+target],size=20)


def note(p,name,y,limit=76,default=""):
    p.text(name,24,y,432,56,default,size=20,color=WARN,bg=BG,limit=limit,isbr=1)


def value(p,name,x,y,w,label="",limit=48):
    p.text(name,x,y,w,48,label,size=20,bg=PANEL,limit=limit,isbr=1,align=1)


def make_settings():
    p=Page("settings","Stationseinstellungen","FMI Printstation / Raspberry Pi 4B")
    p.add("editText","variable",vscope=1,sta=1,txt="",txt_maxl=16)
    for y,target,label in ((279,"wifi","WLAN"),(379,"printer","Drucker"),
                           (479,"receipt","Beleg"),(579,"system","System & Display")):
        p.button("b"+target,24,y,432,78,label,["page "+target],target=="wifi")
    back(p,"home")
    p.save()


def make_wifi():
    p=Page("wifi","WLAN einrichten","Lokale Einstellungen / kein Internet nötig")
    value(p,"wCurrent",24,263,432,"Nicht verbunden",56)
    for name in ("wBusy","wCount","wNext","wPrev"):
        p.var(name,global_=False)
    p.button("bScan",24,322,432,51,"Netzwerke suchen",[
        "if(wBusy.val==0&&home.online.val==1)","{","wBusy.val=1","wCount.val=0",
        *emit("RC4:SCAN"),"}"],True,20)
    for i in range(4):
        p.button(f"wRow{i}",24,384+i*53,432,46,"-",
                 [f"if(wBusy.val==0&&wCount.val>{i}&&home.online.val==1)","{",
                  *emit(f"RC4:SEL:{i}"),"page wjoin","}"],size=20)
        p.doc["component"][-1].update(txt_maxl=54,isbr=1)
    p.button("bPrev",24,597,132,48,"Zurück",["if(wPrev.val==1)","{",*active_action("PREV"),"}"],size=20)
    value(p,"wIndex",164,597,150,"",16)
    p.button("bNext",322,597,134,48,"Weitere",["if(wNext.val==1)","{",*active_action("NEXT"),"}"],size=20)
    note(p,"wStatus",650,default="Netzwerke suchen, um WLAN einzurichten.")
    back(p)
    p.save()


def make_join():
    p=Page("wjoin","WLAN verbinden","Die Verbindung läuft auf dem Raspberry Pi.")
    p.var("jMode",global_=False)
    value(p,"jName",24,285,432,"Kein Netz ausgewählt",42)
    note(p,"jStatus",362,86)
    p.button("bJoin",24,456,432,76,"Verbinden / Passwort",[
        "if(home.online.val==1)","{","if(jMode.val==1)","{","jMode.val=0",*emit("RC4:JOIN"),
        "}else if(jMode.val==2)","{","entry.field.val=2","page keyboard","}","}"],True,20)
    back(p,"wifi")
    p.save()


def make_printer():
    p=Page("printer","Drucker einrichten","Direktverbindung / Epson ESC-POS über Ethernet")
    for i, (stem,label,limit) in enumerate((("Host","IPv4-ADRESSE",16),("Port","TCP-PORT",5))):
        y=280+i*99
        p.label(24,y,label,14,CYAN)
        value(p,"p"+stem,24,y+24,294,"",limit)
        p.button("b"+stem,330,y+24,126,48,"Ändern",["if(home.online.val==1)","{",
                 "settings.editText.txt=p"+stem+".txt",f"entry.field.val={3+i}","page keyboard","}"],size=20)
    p.button("bProbe",24,499,432,53,"TCP-Verbindung testen",active_action("PROBE"),size=20)
    p.button("bTest",24,565,432,55,"Testbeleg drucken",active_action("TEST"),True,20)
    note(p,"pStatus",643)
    back(p)
    p.save()


def make_receipt():
    p=Page("receipt","Beleg einstellen","Änderungen gelten ab dem nächsten Druck.")
    p.button("rGraphic",24,279,432,61,"Kopf: Grafik",active_action("GRAPH"),size=20)
    p.doc["component"][-1]["txt_maxl"]=28
    p.label(24,369,"PAPIERTRANSPORT VOR SCHNITT",14,CYAN)
    p.button("bFeedDown",24,398,117,58,"- 5 mm",active_action("FEED-"),size=20)
    value(p,"rFeed",151,403,178,"45 mm",16)
    p.button("bFeedUp",339,398,117,58,"+ 5 mm",active_action("FEED+"),size=20)
    p.label(24,489,"DRUCKDICHTE · GS ( K NUR BEI KOMPATIBLEM MODELL",13,CYAN)
    p.button("rDensity",24,516,432,58,"Druckervorgabe",active_action("DENSITY"),size=20)
    p.doc["component"][-1]["txt_maxl"]=30
    note(p,"rStatus",626,68)
    back(p)
    p.save()


def make_system():
    p=Page("system","System & Display","480 × 800 / 270° / UART 115200")
    value(p,"sModel",24,259,432,"Raspberry Pi 4B",50)
    p.label(24,328,"HELLIGKEIT",14,CYAN)
    p.button("bBrightDown",24,353,116,50,"- 10 %",active_action("BR-"),size=20)
    value(p,"sBright",151,354,178,"100 %",16)
    p.button("bBrightUp",340,353,116,50,"+ 10 %",active_action("BR+"),size=20)
    p.label(24,425,"STANDBY NACH LETZTER BERÜHRUNG",14,CYAN)
    value(p,"sStand",24,449,230,"Aus",16)
    p.button("bStand",270,449,186,50,"Ändern",active_action("STANDBY"),size=20)
    p.button("bPower",24,546,432,58,"Neustart / Ausschalten",["page power"],size=20)
    note(p,"sStatus",638,60)
    back(p)
    p.save()


def make_power():
    p=Page("power","Systemaktion bestätigen","Laufende Aufträge zuerst abschliessen.")
    p.var("xEnabled",global_=False)
    note(p,"xStatus",274)
    for y,name,label in ((377,"REBOOT","Jetzt neu starten"),(469,"HALT","Jetzt ausschalten")):
        p.button("b"+name,24,y,432,65,label,["if(xEnabled.val==1&&home.online.val==1)","{",
                 "xEnabled.val=0",*emit("RC4:"+name),"}"],size=20)
    p.button("bCancel",24,610,432,60,"Abbrechen",["page system"],True,20)
    back(p,"system")
    p.save()


def make_tester():
    p=Page("tester","BENNING-Speicher","Messung, Datum und Prüfobjekt abgleichen")
    for name in ("mCount","mPrev","mNext","mReady","mSaving"):
        p.var(name,global_=False)
    p.text("mLink",24,253,432,41,"Warte auf Host",size=20,color=MUTED,bg=BG,limit=92,isbr=1)
    p.text("mImport",24,296,432,31,"Noch kein Import",size=20,color=CYAN,bg=BG,limit=52)
    for i in range(4):
        p.button(f"mRow{i}",24,334+i*47,432,42,"-",[f"if(mCount.val>{i}&&home.online.val==1)","{",
                 *emit(f"RC5:SEL:{i}"),"}"],size=20)
        p.doc["component"][-1]["txt_maxl"]=42
    p.button("bPrev",24,526,209,42,"Vorherige",["if(mPrev.val==1)","{",
             *emit("RC5:PREV"),"}"],size=20)
    p.button("bNext",247,526,209,42,"Weitere",["if(mNext.val==1)","{",
             *emit("RC5:NEXT"),"}"],size=20)
    p.text("mSelected",24,575,432,35,"Keine Messung ausgewählt",size=20,
           color=CYAN,bg=BG,limit=55)
    p.text("mNote",24,612,432,55,"",size=20,color=WARN,bg=BG,limit=86,isbr=1)
    p.button("bUse",24,673,432,49,"Messung bestätigen",["if(mReady.val==1&&home.online.val==1)","{",
             "mReady.val=0","mSaving.val=1",*emit("RC5:USE"),"}"],True,20)
    p.button("bBack",24,730,432,40,"Zurück zur Eingabe",["page entry"],size=20)
    p.flow(["if(mSaving.val==1&&report.ready.val==1)","{","mSaving.val=0","page report","}"])
    p.save()


def main():
    for folder in ("pages","pictures"):
        for path in (APP/folder).glob("*"):
            if path.is_file():
                path.unlink()
    app = {"format":1,"name":"Repair Café Riehen · FMI Printstation v0.5",
           "language":"nextion_do_not_change_manually","screen":"NX8048T070",
           "rotation":270,"encoding":"iso-8859-15","pages":PAGES,
           "pictures":[s for p in PAGES for s in ((p,) if p in FLAT else (p,p+"_press"))],
           "fonts":["UI20","UI24","UI28"]}
    (APP/"app.toml").write_text(tomli_w.dumps(app),encoding="utf-8")
    typeface = TrueTypeFont((DESIGN/"typeface/NotoSans-Regular.ttf").read_bytes())
    for size in (20,24,28):
        (APP/f"fonts/UI{size}.zi").write_bytes(draw_font_block(
            f"UI{size}",typeface,size,"iso-8859-15",270))
    (APP/"program.nx").write_text(
        'int sys0=0,sys1=0,sys2=0\nbaud=115200\ndim=100\nrecmod=0\nsendxy=0\n'
        'printh 00 00 00 ff ff ff 88 ff ff ff\nprints "RC3:BOOT",0\nprinth ff ff ff\npage home\n',
        encoding="utf-8")
    make_home(); make_entry(); make_keyboard(); make_report(); make_qr(); make_history(); make_settings()
    make_wifi(); make_join(); make_printer(); make_receipt(); make_system(); make_power(); make_tester()
    (ROOT/"hmi/design/keyboard-layout.json").write_text(json.dumps(
        dict(lower=LOWER,upper=UPPER,symbols=SYMBOL1,accents=SYMBOL2),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Generated native v0.5 pages; reference HMI left untouched.")


if __name__ == "__main__":
    main()
