"""Render actual native simulator states for review, without hardware."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from nxwright.mcp_server.headless import HeadlessSimulation

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/"hmi/previews"


def main():
    OUT.mkdir(exist_ok=True)
    s = HeadlessSimulation(ROOT/"hmi/native")
    s.send('home.online.val=1')
    s.send('home.tLink.txt="Host verbunden / Simulation"')
    s.send('home.tClock.txt="25.11.2026  17:30"')
    s.send('home.tHint.txt="Simulation bereit. Keine elektrische Prüfung."')
    shots=[]

    def shot(name,label):
        data=s.screen()["png"]
        (OUT/f"{name}.png").write_bytes(data)
        shots.append((name,label))

    shot("home","Startseite")
    s.send('page entry')
    s.send('tTicket.txt="RC-2026-042"')
    s.send('tDevice.txt="Kaffeemühle / Küche"')
    s.send('tStatus.txt="Felder antippen, um Text einzugeben."')
    shot("entry","Gerät erfassen")
    s.send('field.val=1')
    s.send('page keybdA')
    shot("keyboard","QWERTZ / klein")
    s.send('click bShift,0')
    shot("keyboard_upper","QWERTZ / gross")
    s.send('click bMode,0')
    shot("keyboard_symbols","Zahlen & Symbole")
    s.send('click bMode,0')
    shot("keyboard_accents","Umlaute & Akzente")
    s.send('page report')
    s.send('tTicket.txt="RC-2026-042"')
    s.send('tDevice.txt="Kaffeemühle / Küche"')
    s.send('tDate.txt="25.11.2026  17:30"')
    s.send('tStatus.txt="Keine Messwerte. Kein Sicherheitsnachweis."')
    shot("report","Simulationsbericht")
    s.send('page qrpage')
    s.send('qrReport.txt="http://192.168.1.42:8080/r/SIMULATION-PREVIEW-ONLY"')
    s.send('qReady.val=1')
    s.send('tNote.txt="Mit dem Handy scannen. Handy und Station müssen im selben Netz sein."')
    s.wait(200)
    shot("qr","PDF-Download")
    s.send('page history')
    for i,label in enumerate(("#42  RC-2026-042","#41  RC-2026-041","Keine weiteren Protokolle",
                               "Keine weiteren Protokolle","Keine weiteren Protokolle")):
        s.send(f'bRow{i}.txt="{label}"')
    s.send('tStatus.txt="Nur Simulationen / keine elektrischen Prüfungen"')
    shot("history","Protokollverlauf")
    s.send('settings.tPrinter.txt="169.254.223.252:9100 / TCP"')
    s.send('settings.tUrl.txt="http://192.168.1.42:8080"')
    s.send('page settings')
    shot("settings","Station & Verbindung")
    # A contact sheet is only a review image; the HMI uses individual pages.
    chosen=[shots[i] for i in (0,1,2,6,7)]
    canvas=Image.new("RGB",(5*288+6*18,560),"#090f16")
    draw=ImageDraw.Draw(canvas)
    face=ROOT/"hmi/design/typeface/NotoSans-Regular.ttf"
    font=ImageFont.truetype(str(face),16)
    for i,(name,label) in enumerate(chosen):
        x=18+i*306
        draw.text((x,14),label,font=font,fill="#afc2d0")
        canvas.paste(Image.open(OUT/f"{name}.png").resize((288,480),Image.Resampling.LANCZOS),(x,50))
    canvas.save(OUT/"overview.png")
    print(f"Rendered {len(shots)} native simulator states and overview.png")


if __name__=="__main__":
    main()
