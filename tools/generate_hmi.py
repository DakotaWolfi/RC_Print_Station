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
PAGES = ["home", "entry", "keyboard", "report", "qrpage", "history", "settings"]

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
        self.label(390, 777, "v0.3 RC", 12, MUTED)
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
        (APP / f"pages/{self.name}.page.toml").write_text(tomli_w.dumps(self.doc), encoding="utf-8")
        (APP / f"pages/{self.name}.nx").write_text(self.code, encoding="utf-8")
        self.art.resize((480, 800), Image.Resampling.LANCZOS).save(APP / f"pictures/{self.name}.png")
        pressed = self.art.copy()
        draw = ImageDraw.Draw(pressed)
        for x, y, w, h, primary in self.shapes:
            draw.rounded_rectangle((x*2, y*2, (x+w)*2-1, (y+h)*2-1), radius=24,
                                   fill="#ffc071" if primary else "#365164")
        pressed.resize((480, 800), Image.Resampling.LANCZOS).save(APP / f"pictures/{self.name}_press.png")


def make_home():
    p = Page("home", "Reparieren. Weitergeben.", "Ein zweites Leben beginnt mit einer Reparatur.")
    p.var("proto", 3)
    for name in ("online", "age", "pending"):
        p.var(name)
    p.box(24, 273, 432, 115)
    p.label(40, 289, "ENTWICKLUNGSMODUS", 14, ORANGE)
    p.label(40, 315, "Simulation · keine elektrische Prüfung", 18, WARN)
    p.text("tLink", 40, 348, 400, 27, "Host nicht verbunden", size=20,
           color=MUTED, global_=True, limit=32)
    p.button("bNew", 24, 412, 432, 82, "Neues Protokoll", [
        'entry.tTicket.txt=""', 'entry.tDevice.txt=""', 'entry.tStatus.txt=""',
        "entry.busy.val=0", "page entry"], True, 28)
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
    p = Page("entry", "Gerät erfassen", "01  Angaben   /   02  Bericht   /   03  Ausgabe")
    p.var("field")
    p.var("busy")
    p.label(24, 284, "REPARATURNUMMER", 15, CYAN)
    p.box(24, 315, 432, 72, outline=EDGE)
    p.text("tTicket", 38, 325, 404, 50, global_=True, limit=32, isbr=1)
    p.label(24, 419, "GERÄTEBEZEICHNUNG", 15, CYAN)
    p.box(24, 450, 432, 86, outline=EDGE)
    p.text("tDevice", 38, 460, 404, 66, global_=True, limit=64, isbr=1, size=20)
    for field, (y, h) in enumerate(((315,72),(450,86))):
        p.add(f"hEdit{field}", "hotspot", x=24, y=y, w=432, h=h)
        p.on(f"hEdit{field}.up", ["if(busy.val==0)", "{", f"field.val={field}", "page keyboard", "}"])
    p.text("tStatus", 24, 548, 432, 51, "Felder antippen, um Text einzugeben.", size=20,
           color=WARN, bg=BG, global_=True, limit=80, isbr=1)
    p.button("bCreate", 24, 615, 432, 72, "Simulation erstellen", [
        "if(busy.val==0)", "{", 'if(tTicket.txt==""||tDevice.txt=="")', "{",
        'tStatus.txt="Bitte beide Felder ausfüllen."', "}else if(home.online.val==0)", "{",
        'tStatus.txt="Host nicht verbunden. Eingaben bleiben erhalten."', "}else", "{",
        "busy.val=1", "report.ready.val=0", 'tStatus.txt="Simulationsbericht wird erstellt ..."',
        'prints "RC3:CREATE",0', "printh 00", "prints tTicket.txt,0", "printh 00",
        "prints tDevice.txt,0", "printh ff ff ff", "}", "}"], True)
    p.button("bBack", 24, 707, 432, 52, "Zurück", ["if(busy.val==0)", "{", "page home", "}"])
    p.flow(["if(busy.val==1&&report.ready.val==1)", "{", "busy.val=0", "page report", "}",
            "if(busy.val==1&&home.online.val==0)", "{", "busy.val=0",
            'tStatus.txt="Host-Verbindung verloren. Bitte erneut versuchen."', "}"])
    p.save()


def make_keyboard():
    p = Page("keyboard", "Texteingabe", "Schweiz · QWERTZ   /   direkt auf dem Display")
    for name in ("mode", "shift", "caps", "count", "limit"):
        p.var(name, global_=False)
    p.var("dirty", 1, global_=False)
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
        p.on(name+".up", ["strlen input.txt,count.val", "if(count.val<limit.val)", "{",
                            f"input.txt+={name}.txt", "}", "if(shift.val==1)", "{",
                            "shift.val=0", "click hLayout,0", "}", "click hCount,0"])
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
        ("bDel",437,599,36,50,"<",['input.txt-=1',"click hCount,0"],24),
        ("bMode",8,660,74,50,"123",["mode.val++","if(mode.val>2)","{","mode.val=0","}","click hLayout,0"],20),
        ("bCaps",88,660,74,50,"Caps",["caps.val=1-caps.val","shift.val=0","mode.val=0","click hLayout,0"],20),
        ("bSpace",168,660,204,50,"Leerzeichen",["strlen input.txt,count.val","if(count.val<limit.val)","{",'input.txt+=" "',"}","click hCount,0"],20),
        ("bClear",378,660,94,50,"Leeren",['input.txt=""',"click hCount,0"],20)]
    for name,x,y,w,h,label,lines,size in controls:
        p.add(name,"button",x=x,y=y,w=w,h=h,style=0,borderw=0,font=f"UI{size}",
              bco=PANEL,bco2=ORANGE,pco=WHITE,pco2=BG,txt=label,txt_maxl=max(len(label),5))
        p.on(name+".up", lines)
    p.button("bCancel",16,725,212,44,"Abbrechen",["page entry"],size=20)
    p.button("bOK",240,725,224,44,"Übernehmen",["if(entry.field.val==0)","{",
        "entry.tTicket.txt=input.txt","}else","{","entry.tDevice.txt=input.txt","}",
        'entry.tStatus.txt=""',"page entry"],True,20)
    p.on("keyboard.loadend", ["mode.val=0","shift.val=0","caps.val=0","if(entry.field.val==0)","{",
        "input.txt=entry.tTicket.txt",'tField.txt="Reparaturnummer"',"limit.val=32","}else","{",
        "input.txt=entry.tDevice.txt",'tField.txt="Gerätebezeichnung"',"limit.val=64","}",
        "click hLayout,0","click hCount,0"])
    p.save()


def rgb565(color):
    n = int(color[1:],16)
    return ((n>>19)<<11)|(((n>>10)&63)<<5)|((n>>3)&31)


def make_report():
    p = Page("report", "Simulationsbericht", "02  Bericht   /   Vorschau vor der Ausgabe")
    p.var("ready")
    p.var("printing")
    p.box(24,273,432,78,"#3a2c20")
    p.label(40,289,"SIMULATION · NICHT GEPRÜFT",21,WARN)
    p.label(40,323,"Kein Nachweis einer elektrischen Sicherheitsprüfung.",14,WARN)
    p.label(24,373,"TICKET",14,CYAN)
    p.text("tTicket",24,395,432,44,"",global_=True,limit=32,bg=BG,size=20,isbr=1)
    p.label(24,449,"GERÄT",14,CYAN)
    p.text("tDevice",24,471,432,70,"",global_=True,limit=64,bg=BG,isbr=1,size=20)
    p.text("tDate",24,547,432,28,"",size=20,color=MUTED,bg=BG,global_=True,limit=24)
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
    p.label(24,705,"SIMULATION · keine elektrische Prüfung",17,WARN)
    p.button("bBack",24,733,432,34,"Zurück zum Bericht",["page report"],size=20)
    p.on("qrpage.loadend",["shown.val=0","vis qrReport,0",*emit("RC3:QR")])
    p.flow(["if(qReady.val==1&&shown.val==0)","{","vis qrReport,1","shown.val=1","}",
            "if(qReady.val!=1&&shown.val==1)","{","vis qrReport,0","shown.val=0","}",
            "if(home.online.val==0)","{","qReady.val=2",
            'tNote.txt="Host nicht verbunden. Bitte Verbindung prüfen."',"}"])
    p.save()


def make_history():
    p = Page("history", "Protokollverlauf", "Die fünf zuletzt gespeicherten Simulationen.")
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


def make_settings():
    p = Page("settings", "Station & Verbindung", "FMI Printstation   /   lokale Geräte")
    for title,y in (("DRUCKER",282),("DISPLAY",389),("PDF-DOWNLOAD",496)):
        p.label(24,y,title,14,CYAN)
        p.box(24,y+25,432,68)
    p.text("tPrinter",38,311,404,60,"",size=20,limit=64,global_=True,isbr=1)
    p.text("tUart",38,418,404,60,"115200 Baud · 480 × 800 · 270°",size=20,limit=64,global_=True,isbr=1)
    p.text("tUrl",38,525,404,60,"Deaktiviert",size=20,limit=100,global_=True,isbr=1)
    p.text("tStatus",24,618,432,66,"Prüfgerät: Simulator. Keine Messwerte.",size=20,
           limit=80,color=WARN,bg=BG,isbr=1)
    p.button("bBack",24,715,432,52,"Hauptmenü",["page home"],size=20)
    p.save()


def main():
    for folder in ("pages","pictures"):
        for path in (APP/folder).glob("*"):
            if path.is_file():
                path.unlink()
    app = {"format":1,"name":"Repair Café Riehen · FMI Printstation v0.3",
           "language":"nextion_do_not_change_manually","screen":"NX8048T070",
           "rotation":270,"encoding":"iso-8859-15","pages":PAGES,
           "pictures":[s for p in PAGES for s in (p,p+"_press")],
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
    (ROOT/"hmi/design/keyboard-layout.json").write_text(json.dumps(
        dict(lower=LOWER,upper=UPPER,symbols=SYMBOL1,accents=SYMBOL2),ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("Generated seven candidate pages; reference HMI left untouched.")


if __name__ == "__main__":
    main()
