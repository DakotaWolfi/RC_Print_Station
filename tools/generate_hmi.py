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
         "wifi", "wjoin", "printer", "receipt", "system", "power", "tester", "guide", "importer"]
FLAT = set(PAGES[6:]) | {"home","entry","report"}

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
        self.label(390, 777, "v0.6 RC", 12, MUTED)
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
        if self.name in FLAT:
            self.add(name,"button",x=x,y=y,w=w,h=h,sta=1,style=0,borderw=0,
                     font=f"UI{size}",bco=color,bco2="#ffc071" if primary else "#365164",
                     pco=BG if primary else WHITE,pco2=BG if primary else WHITE,
                     txt=label,txt_maxl=max(len(label),1),isbr=0)
            self.code += event(name+".up",lines)
            return
        self.box(x, y, w, h, color)
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
    p.var("proto", 6)
    for name in ("online", "age", "pending"):
        p.var(name)
    p.box(24, 273, 432, 115)
    p.label(40, 289, "PRÜFPROTOKOLLE", 14, ORANGE)
    p.label(40, 315, "BENNING ST 725 / Repair Café", 18, WARN)
    p.text("tLink", 40, 348, 400, 27, "Host nicht verbunden", size=20,
           color=MUTED, global_=True, limit=32)
    reset=['entry.tTicket.txt=""','entry.tDevice.txt=""','entry.tStatus.txt=""',
           'entry.tSlot.txt=""','guide.eName.txt=""','guide.eRemarks.txt=""',
           "entry.phase.val=0","entry.useLast.val=1","entry.busy.val=0","entry.route.val=0"]
    p.button("bNew",24,412,313,82,"Geführte Prüfung",
             [*reset,"entry.guided.val=1",*emit("RC6:NEW"),"page entry"],True,24)
    p.button("bDirect",347,412,109,82,"Direkt",
             [*reset,"entry.guided.val=0",*emit("RC6:NEW"),"page entry"],size=20)
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
    for name,initial in (("field",0),("busy",0),("phase",0),("useLast",1),("sim",0),("guided",0),("route",0)):
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
    p.on("entry.loadend",["route.val=0","busy.val=0","cLast.val=useLast.val","click hPhase,0",
                          "if(sim.val==1)","{",'bCreate.txt="Simulation erstellen"',
                          "}else if(guided.val==1)","{",'bCreate.txt="Prüfung beginnen"',"vis bTester,0","}"])
    p.text("tTester",24,575,432,38,"Warte auf BENNING-Host.",size=20,
           color=MUTED,bg=BG,global_=True,limit=92,isbr=1)
    p.text("tStatus",24,615,432,46,"",size=20,color=WARN,bg=BG,global_=True,limit=100,isbr=1)
    p.add("vArg","variable",sta=1,txt="",txt_maxl=2)
    payload=["printh 00","prints tTicket.txt,0","printh 00","prints tDevice.txt,0"]
    fields=["printh 00","prints tSlot.txt,0","printh 00","covx phase.val,vArg.txt,0,0",
            "prints vArg.txt,0","printh 00","covx useLast.val,vArg.txt,0,0","prints vArg.txt,0"]
    online=["if(busy.val==0)","{","if(home.online.val==0)","{",
            'tStatus.txt="Host nicht verbunden. Eingaben bleiben erhalten."',
            '}else if(tTicket.txt==""||tDevice.txt=="")',"{",'tStatus.txt="Prüfnummer und Gerät eingeben."',
            "}else","{","report.ready.val=0","busy.val=1","route.val=0"]
    p.button("bCreate",24,665,228,50,"Messung importieren",[*online,
        "if(sim.val==1)","{",'prints "RC3:CREATE",0',*payload,"}else if(guided.val==1)","{",
        'prints "RC6:GUIDE",0',*payload,*fields,"}else","{",
        'prints "RC6:IMPORT",0',*payload,*fields,"}","printh ff ff ff","}","}"],True,20)
    p.doc["component"][-1]["txt_maxl"]=26
    p.button("bTester",262,665,194,50,"Vorhandene Messung",[*online,
             'prints "RC6:EXISTING",0',*payload,*fields,"printh ff ff ff","}","}"],size=20)
    p.button("bBack",24,725,210,41,"Zurück",["if(busy.val==0)","{","page home","}"],size=20)
    p.button("bHelp",246,725,210,41,"Hilfe",[
         "if(guided.val==1)","{",
         'tStatus.txt="Eingaben bleiben beim Zurückblättern erhalten."',
         "}else","{",
         'tStatus.txt="Neue Messung importieren oder einen gespeicherten Slot wählen."',
         "}"],size=20)
    p.flow(["if(busy.val==1&&report.ready.val==1)","{","busy.val=0","page report","}",
            "if(busy.val==1&&home.online.val==0)","{","busy.val=0",
            'tStatus.txt="Host-Verbindung verloren. Bitte erneut versuchen."',
            "}else if(route.val==1)","{","busy.val=0","route.val=0","page guide",
            "}else if(route.val==2)","{","busy.val=0","route.val=0","page importer",
            "}else if(route.val==3)","{","busy.val=0","route.val=0","page tester","}"])
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
        "}else if(entry.field.val>5)","{","page guide","}else","{","page entry","}"],size=20)
    p.button("bOK",240,725,224,44,"Übernehmen",[
        "if(entry.field.val==2)","{","if(home.online.val==1)","{",
        'prints "RC4:PASS",0',"printh 00","prints secret.txt,0","printh ff ff ff","}",
        'secret.txt=""','input.txt=""',"page wjoin","}else if(entry.field.val>2&&entry.field.val<5)","{",
        "if(home.online.val==1)","{","if(entry.field.val==3)","{",'prints "RC4:IP",0',"}else","{",
        'prints "RC4:PORT",0',"}","printh 00","prints input.txt,0","printh ff ff ff","}",
        'input.txt=""',"page printer","}else if(entry.field.val>5)","{",
        "if(entry.field.val==6)","{","guide.eName.txt=input.txt","}else","{",
        "guide.eRemarks.txt=input.txt","}","page guide","}else","{","if(entry.field.val==0)","{",
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
        "}else if(entry.field.val==5)","{","input.txt=entry.tSlot.txt",'tField.txt="Prüfspeichernummer"',"limit.val=3",
        "}else if(entry.field.val==6)","{","input.txt=guide.eName.txt",
        'tField.txt="Prüfperson"',"limit.val=48","}else","{","input.txt=guide.eRemarks.txt",
        'tField.txt="Bemerkung"',"limit.val=64","}",'settings.editText.txt=""',
        "click hLayout,0","click hCount,0"])
    p.save()


def rgb565(color):
    n = int(color[1:],16)
    return ((n>>19)<<11)|(((n>>10)&63)<<5)|((n>>3)&31)


def make_report():
    p = Page("report", "Prüfprotokoll", "02  Bericht   /   Vorschau vor der Ausgabe")
    p.var("ready")
    p.var("printing")
    p.var("vMore",global_=False)
    p.box(24,255,432,96)
    p.text("tOrigin",38,264,404,26,"",size=20,color=MUTED,bg=PANEL,global_=True,limit=55,align=1)
    p.text("tResult",38,289,404,52,"",size=36,color=WHITE,bg=PANEL,global_=True,limit=40,align=1)
    p.label(24,365,"PRÜFNUMMER",13,CYAN)
    p.text("tTicket",143,360,313,25,"",global_=True,limit=32,bg=BG,size=20)
    p.text("tDevice",24,386,432,48,"",global_=True,limit=64,bg=BG,isbr=1,size=20)
    p.text("tMeta",24,433,432,27,"",size=20,color=CYAN,bg=BG,global_=True,limit=69)
    p.text("tDate",24,460,432,26,"",size=20,color=MUTED,bg=BG,global_=True,limit=42)
    for i in range(3):
        p.text(f"tValue{i}",24,487+i*37,432,36,"",size=20,bg=BG,limit=94,isbr=1)
    p.text("tStatus",24,598,432,46,"Keine Messwerte vorhanden.",size=20,color=WARN,
           bg=BG,global_=True,limit=90,isbr=1)
    p.button("bPrint",24,651,210,54,"Beleg drucken",[
        "if(home.online.val==1&&ready.val==1&&printing.val==0)","{","printing.val=1",
        'tStatus.txt="Druckdaten werden gesendet ..."',*emit("RC3:PRINT"),"}else if(home.online.val==0)","{",
        'tStatus.txt="Host nicht verbunden. Druck nicht gesendet."',"}else if(ready.val==0)","{",
        'tStatus.txt="Bitte Bericht erneut im Verlauf öffnen."',"}"] ,True,20)
    p.button("bQR",246,651,210,54,"PDF / QR-Code",[
        "if(ready.val==1)","{","qrpage.qReady.val=0","page qrpage","}"],size=20)
    p.button("bHome",24,715,210,46,"Hauptmenü",["page home"],size=20)
    p.button("bValues",246,715,210,46,"Weitere Werte",["if(vMore.val==1&&home.online.val==1)","{",
             *emit("RC6:VALUES"),"}"],size=20)
    p.on("report.loadend",["if(vMore.val==0)","{","vis bValues,0","}"])
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
    p.text("mNote",24,612,432,55,"",size=20,color=WARN,bg=BG,limit=100,isbr=1)
    p.button("bUse",24,673,432,49,"Messung bestätigen",["if(mReady.val==1&&home.online.val==1)","{",
             "mReady.val=0","mSaving.val=1",*emit("RC5:USE"),"}"],True,20)
    p.button("bBack",24,730,432,40,"Zurück zur Eingabe",["page entry"],size=20)
    p.flow(["if(mSaving.val==1&&report.ready.val==1)","{","mSaving.val=0","page report","}"])
    p.save()


ART=("lcd","keys","class1","class2","iec","extension","store","recall","print","ports")
PICTURES=[s for p in PAGES for s in ((p,) if p in FLAT else (p,p+"_press"))]+[f"g_{s}" for s in ART]


def make_guide_art():
    """Independent schematics checked against the CH manual, Figs. 1–6b."""
    face=DESIGN/"typeface/NotoSans-Regular.ttf"
    for name in ART:
        im=Image.new("RGB",(432,96),BG)
        d=ImageDraw.Draw(im)
        def txt(x,y,label,size=16,colour=WHITE,anchor="lm"):
            d.text((x,y),label,font=ImageFont.truetype(str(face),size),fill=colour,anchor=anchor)
        def box(bounds,colour=PANEL):
            d.rounded_rectangle(bounds,8,fill=colour,outline=EDGE,width=2)
        def line(points,width=3,colour=CYAN):
            d.line(points,fill=colour,width=width,joint="curve")
        def key(x,label):
            d.ellipse((x-25,15,x+25,65),fill=PANEL,outline=ORANGE,width=2)
            if label=="Erdzeichen":
                line((x,25,x,42),2,WHITE)
                for idx,width in enumerate((23,15,7)):
                    line((x-width//2,42+idx*5,x+width//2,42+idx*5),2,WHITE)
            elif label=="Doppelquadrat":
                d.rectangle((x-14,26,x+14,54),outline=WHITE,width=2)
                d.rectangle((x-8,32,x+8,48),outline=WHITE,width=2)
            elif label=="Diskette":
                d.polygon([(x-15,24),(x+10,24),(x+15,29),(x+15,56),(x-15,56)],fill=WHITE)
                d.rectangle((x-10,27,x+5,37),fill=BG)
                d.rectangle((x-10,44,x+10,55),fill=BG)
            elif label=="Ordner":
                line((x-15,53,x-16,30,x-5,30,x,35,x+16,35,x+12,53,x-15,53),2,WHITE)
                line((x-15,53,x-10,38,x+17,38,x+12,53),2,WHITE)
            elif label=="Drucker":
                d.rounded_rectangle((x-17,33,x+17,49),3,outline=WHITE,width=2)
                d.rectangle((x-10,25,x+10,33),outline=WHITE,width=2)
                d.rectangle((x-10,44,x+10,55),outline=WHITE,width=2)
                line((x-5,48,x+5,48),1,WHITE)
            elif label=="250 / 500 V":
                txt(x,32,"250 V",11,anchor="mm")
                line((x-15,40,x+15,40),1,WHITE)
                txt(x,48,"500 V",11,anchor="mm")
            else:
                txt(x,40,label,11,anchor="mm")
            txt(x,81,label,14,anchor="mm")
        if name=="keys":
            for x,label in zip((54,162,270,378),("Erdzeichen","Doppelquadrat","IPE/IB","250 / 500 V")):
                key(x,label)
        elif name in ("store","recall","print"):
            symbol,verb,num={"store":("Diskette","STORE",13),"recall":("Ordner","RECALL",14),
                             "print":("Drucker","PRINT",15)}[name]
            key(67,symbol)
            txt(125,32,f"{verb}  ·  Taste {num}",22,ORANGE)
            txt(125,63,"BENNING ST 725 CH",16,MUTED)
        elif name=="ports":
            box((5,4,427,89))
            txt(216,17,"OBERSEITE  /  von links nach rechts",14,MUTED,anchor="mm")
            for x,symbol,label in zip((54,162,270,378),("9","12","10","11"),("4 mm","PS/2","IEC","Netz")):
                d.ellipse((x-17,29,x+17,63),outline=CYAN,width=2)
                txt(x,46,symbol,16,anchor="mm")
                txt(x,76,label,15,anchor="mm")
        elif name=="lcd":
            box((32,9,399,87))
            txt(50,29,"BENNING ST 725 CH",13,MUTED)
            txt(216,59,"ANZEIGE AM PRÜFGERÄT",20,ORANGE,anchor="mm")
        elif name in ("class1","class2"):
            box((3,7,146,88))
            box((263,7,427,88))
            txt(17,24,"BENNING",15)
            txt(277,24,"PRÜFLING",15)
            line((146,47,263,47))
            line((146,73,263,73),2,ORANGE)
            txt(18,47,"9 · 4 mm",15,CYAN)
            txt(18,73,"1 · Prüfung",15,ORANGE)
            txt(277,47,"PE-Metallteil" if name=="class1" else "Leitfähige Stelle",14,CYAN)
            txt(277,73,"Gerätestecker",14,ORANGE)
            txt(203,23,"11 · Netz optional*",12,MUTED,anchor="mm")
        else:
            box((4,5,124,90))
            box((302,5,427,90))
            txt(16,23,"BENNING",15)
            txt(316,23,"LEITUNG",15)
            txt(17,46,"10 · IEC",15,CYAN)
            txt(17,72,"1 · Prüfung",15,ORANGE)
            line((124,47,302,47))
            line((124,73,302,73),2,ORANGE)
            txt(214,22,"11 · Netz getrennt",14,MUTED,anchor="mm")
            txt(315,47,"IEC-Kupplung" if name=="iec" else "via IEC-Adapter",13,CYAN)
            txt(315,72,"Netzstecker",14,ORANGE)
        im.save(APP/f"pictures/g_{name}.png")


def add_guide_art(p,var,y):
    p.var(var,global_=False)
    p.add("pArt","picture",x=24,y=y,w=432,h=96,pic="g_lcd")
    p.add("hArt","hotspot",x=2,y=0,w=2,h=2)
    p.on("hArt.up",[line for i,name in enumerate(ART) for line in
                    (f"if({var}.val=={i})","{",f"pArt.pic={PICTURES.index('g_'+name)}","}")])


def make_guide():
    p=Page("guide","Geführte Prüfung","Vor Ort am BENNING bedienen")
    for name in ("gCount","gExam","gAdvance","gBusy"):
        p.var(name,global_=False)
    p.text("gProgress",24,258,432,22,"",size=20,bg=BG,color=CYAN,limit=50)
    p.text("gTitle",24,282,432,32,"Bitte warten ...",size=24,bg=BG,limit=52)
    add_guide_art(p,"gArt",316)
    p.text("gDisplay",50,369,380,38,"",size=24,color=ORANGE,bg=PANEL,limit=40,align=1)
    p.text("gBody",24,415,432,96,"",size=20,bg=BG,isbr=1,limit=230)
    p.text("gError",24,688,432,40,"",size=20,bg=BG,color=WARN,isbr=1,limit=82)
    for i in range(5):
        p.button(f"bStep{i}",24,514+i*35,432,33,"-",[
                  f"if(home.online.val==1&&gBusy.val==0&&gCount.val>{i})","{",
                  "gBusy.val=1",*emit(f"RC6:STEP:{i}"),"}"],i==0,20)
        p.doc["component"][-1]["txt_maxl"]=38
    p.text("eName",24,515,432,36,"",size=20,global_=True,limit=48)
    p.text("eRemarks",24,554,432,36,"",size=20,global_=True,limit=64)
    for field,(name,y,label) in enumerate((("bName",515,"Prüfperson"),("bRemark",554,"Bemerkung")),6):
        p.button(name,24,y,128,36,label,["if(gExam.val==1)","{",
                 f"entry.field.val={field}","page keyboard","}"],size=20)
        component=next(c for c in p.doc["component"] if c["name"]==("eName" if field==6 else "eRemarks"))
        component.update(x=157,w=299)
        hotspot="hName" if field==6 else "hRemark"
        p.add(hotspot,"hotspot",x=157,y=y,w=299,h=36)
        p.on(hotspot+".up",["if(gExam.val==1)","{",f"entry.field.val={field}","page keyboard","}"])
    p.button("gFunction",24,594,432,40,"Funktion: Offen",["if(gExam.val==1&&home.online.val==1)","{",
             *emit("RC6:FUNCTION"),"}"],size=20)
    p.doc["component"][-1]["txt_maxl"]=34
    p.button("gProceed",24,638,432,43,"Zum Import",["if(gExam.val==1&&home.online.val==1&&gBusy.val==0)","{",
             "gBusy.val=1","report.ready.val=0",'prints "RC6:EXAM",0',"printh 00","prints eName.txt,0",
             "printh 00","prints eRemarks.txt,0","printh ff ff ff","}"],True,20)
    p.doc["component"][-1]["txt_maxl"]=30
    p.add("hLayout","hotspot",x=4,y=0,w=2,h=2)
    widgets=("eName","eRemarks","bName","bRemark","hName","hRemark","gFunction","gProceed")
    p.on("hLayout.up",[*(f"vis bStep{i},0" for i in range(5)),*(f"vis {n},0" for n in widgets),
                       "if(gExam.val==1)","{",*(f"vis {n},1" for n in widgets),"}else","{",
                       *(line for i in range(5) for line in (f"if(gCount.val>{i})","{",f"vis bStep{i},1","}")),"}"])
    p.button("bBack",24,730,135,40,"Zurück",["if(home.online.val==1)","{",*emit("RC6:BACK"),
             "}else","{","page entry","}"],size=20)
    p.button("bHelp",173,730,135,40,"Hilfe",[*emit("RC6:HELP")],size=20)
    p.button("bCancel",322,730,134,40,"Abbrechen",["if(home.online.val==1)","{",
             *emit("RC6:CANCEL"),"}else","{","page entry","}"],size=20)
    p.on("guide.loadend",["vis gDisplay,0","click hLayout,0"])
    p.flow(["if(gAdvance.val==1)","{","gAdvance.val=0","page importer",
            "}else if(gAdvance.val==2&&report.ready.val==1)","{","gAdvance.val=0","page report",
            "}else if(gAdvance.val==3)","{","gAdvance.val=0","page entry","}",
            "if(home.online.val==0)","{",'gError.txt="Host getrennt. BENNING lokal sichern."',"gBusy.val=0","}"])
    p.save()


def make_importer():
    p=Page("importer","Messung übertragen","BENNING ST 725 CH · Empfang starten")
    p.var("iAdvance",global_=False)
    p.var("iAvailable",global_=False)
    add_guide_art(p,"iArt",273)
    p.text("iBody",24,390,432,115,"Warte auf Host ...",size=20,bg=BG,limit=220,isbr=1)
    p.text("iStatus",24,510,432,50,"",size=20,bg=BG,color=CYAN,limit=105,isbr=1)
    p.text("iMessage",24,562,432,59,"",size=20,bg=BG,color=WARN,limit=105,isbr=1)
    p.button("bManual",24,639,432,55,"Vorhandene Messung wählen",["if(home.online.val==1&&iAvailable.val==1)",
             "{",*emit("RC6:MANUAL"),"}else","{",'iMessage.txt="Noch kein bestätigter Speicherimport verfügbar."',
             "}"],size=20)
    p.button("bBack",24,722,210,45,"Zurück",["if(home.online.val==1)","{",*emit("RC6:BACK"),
             "}else","{","page entry","}"],size=20)
    p.button("bHelp",246,722,210,45,"Hilfe",[*emit("RC6:HELP")],size=20)
    p.flow(["if(iAdvance.val==1&&home.online.val==1)","{","iAdvance.val=0","page tester",
            "}else if(iAdvance.val==2)","{","iAdvance.val=0","if(entry.guided.val==1)",
            "{","page guide","}else","{","page entry","}","}",
            "if(home.online.val==0)","{",'iStatus.txt="Host getrennt. Verbindung prüfen."',"iAvailable.val=0","}"])
    p.save()


def main():
    for folder in ("pages","pictures"):
        for path in (APP/folder).glob("*"):
            if path.is_file():
                path.unlink()
    app = {"format":1,"name":"Repair Café Riehen · FMI Printstation v0.6",
           "language":"nextion_do_not_change_manually","screen":"NX8048T070",
           "rotation":270,"encoding":"iso-8859-15","pages":PAGES,
           "pictures":PICTURES,
           "fonts":["UI20","UI24","UI28","UI36"]}
    (APP/"app.toml").write_text(tomli_w.dumps(app),encoding="utf-8")
    typeface = TrueTypeFont((DESIGN/"typeface/NotoSans-Regular.ttf").read_bytes())
    for size in (20,24,28,36):
        (APP/f"fonts/UI{size}.zi").write_bytes(draw_font_block(
            f"UI{size}",typeface,size,"iso-8859-15",270))
    (APP/"program.nx").write_text(
        'int sys0=0,sys1=0,sys2=0\nbaud=115200\ndim=100\nrecmod=0\nsendxy=0\n'
        'printh 00 00 00 ff ff ff 88 ff ff ff\nprints "RC3:BOOT",0\nprinth ff ff ff\npage home\n',
        encoding="utf-8")
    make_home(); make_entry(); make_keyboard(); make_report(); make_qr(); make_history(); make_settings()
    make_wifi(); make_join(); make_printer(); make_receipt(); make_system(); make_power(); make_tester()
    make_guide_art(); make_guide(); make_importer()
    (ROOT/"hmi/design/keyboard-layout.json").write_text(json.dumps(
        dict(lower=LOWER,upper=UPPER,symbols=SYMBOL1,accents=SYMBOL2),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Generated native v0.6 pages; reference HMI left untouched.")


if __name__ == "__main__":
    main()
