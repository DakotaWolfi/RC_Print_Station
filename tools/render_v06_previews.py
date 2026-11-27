"""Render every guide state and sample reports from the production output code."""
import argparse
from copy import deepcopy
import re
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont
from nxwright.mcp_server.headless import HeadlessSimulation

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from benning_guide import Guide, STEPS
from benning_receiver import ReceiverStatus
from benning_store import Measurements, PHASES
from native_ui import END, ENCODING, NativeUI
from station_panel_settings import PAGES
from station_config import PRINTER_HOST
from station_network import Network
from i18n import LANGUAGES
from report_web import render_pdf
from station import receipt, simulate

TYPEFACE=ROOT/"hmi/design/typeface/NotoSans-Regular.ttf"


class PreviewSerial:
    def __init__(self,sim):
        self.sim=sim

    def write(self,data):
        for command in filter(None,data.split(END)):
            self.sim.send(command.decode(ENCODING))


def receipt_preview(data):
    """Display the receipt's raster blocks and text sent to the Epson."""
    width=576
    paper=Image.new("1",(width,2200),1)
    draw=ImageDraw.Draw(paper)
    font=ImageFont.truetype(str(TYPEFACE),19)
    y=10
    centred=False
    codepage="cp850"
    prefix=b"\x1dv0\x00"
    while data:
        if data.startswith(prefix):
            row=int.from_bytes(data[4:6],"little")
            height=int.from_bytes(data[6:8],"little")
            end=8+row*height
            raster=Image.frombytes("1",(row*8,height),data[8:end]).point(lambda p:255-p)
            paper.paste(raster,((width-raster.width)//2 if centred else 15,y))
            y+=height
            data=data[end:].removeprefix(b"\n")
        elif data.startswith(b"\x1ba"):
            centred=data[2]!=0
            data=data[3:]
        elif data.startswith(b"\x1bt"):
            codepage={0:"cp437",2:"cp850"}[data[2]]
            data=data[3:]
        elif data.startswith((b"\x1bE",b"\x1d!",b"\x1dV")):
            data=data[3:]
        elif data.startswith(b"\x1bJ"):
            y+=data[2]
            data=data[3:]
        elif data.startswith(b"\x1b@"):
            data=data[2:]
        else:
            line,sep,remainder=data.partition(b"\n")
            text=[]
            for part in re.split(b"(\x1bt[\x00\x02])",line):
                if part.startswith(b"\x1bt"):
                    codepage={0:"cp437",2:"cp850"}[part[2]]
                else:
                    if any(byte<32 for byte in part):
                        raise ValueError(f"Unexpected preview byte {part[:8]!r}")
                    text.append(part.decode(codepage))
            draw.text((width//2 if centred else 15,y+4),"".join(text),font=font,fill=0,
                      anchor="mt" if centred else "lt")
            data=remainder if sep else b""
            y+=26
    return paper.crop((0,0,width,y+12))


def examples(store):
    captured=(ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_text().splitlines()
    row=captured[2].split(";")
    examination={"visual":"Ohne Befund","functional":"Ohne Befund","examiner":"Prüfperson Muster",
                 "remarks":"Synthetischer Beleg zur Layoutprüfung.","status":"Erfasst"}
    for kind in ("PASS","FAIL","partial","exam-open","incomplete","unknown","simulation"):
        if kind=="simulation":
            yield kind,simulate("MUSTER-006","Kaffeemühle (Layoutmuster)")
            continue
        if kind=="incomplete":
            _,report=store.create_incomplete("MUSTER-007","Kaffeemühle (Layoutmuster)",PHASES[0],
                                             {**examination,"visual":"Mangel","functional":"Offen"})
            yield kind,report
            continue
        fields=row.copy()
        if kind=="FAIL":
            fields[3],fields[4],fields[6]="nicht bestanden",">2,34","nicht bestanden"
        elif kind=="partial":
            fields[9]=""
        payload=(captured[0]+"\n"+";".join(fields)+"\n").encode()
        store.import_bytes(payload,"file-csv")
        _,report=store.create_report("MUSTER-006","Kaffeemühle (Layoutmuster)",PHASES[0],
                                     store.slots("file-csv")[0],examination=examination)
        if kind=="exam-open":
            report["examination"]={**examination,"functional":"Offen","examiner":""}
        if kind=="unknown":
            report["record"]["verdict"]=None
            report["verdict"]=None
        yield kind,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    out=p.parse_args().directory
    for language in LANGUAGES:
        render(out/language,language)


def render(out,language):
    for name in ("hmi","receipt","pdf"):
        (out/name).mkdir(parents=True,exist_ok=True)
    sim=HeadlessSimulation(ROOT/"hmi/native")
    receiver=SimpleNamespace(mode="usb",status=ReceiverStatus("waiting","usb"),close=lambda:None)
    with tempfile.TemporaryDirectory() as tmp:
        ui=NativeUI(PreviewSerial(sim),PRINTER_HOST,Path(tmp)/"samples.sqlite3",tester_receiver=receiver,
                    config_path=Path(tmp)/"config.json")
        ui.language=language
        sim.send(f"home.lang.val={int(language=='en')}")
        sim.send("page home")
        sim.send("home.online.val=1")
        ui.say("home.tLink","Host verbunden",32)
        ui.home_hint()
        def shot(name):
            (out/f"hmi/{name}.png").write_bytes(sim.screen()["png"])

        ui.settings.page="home"
        ui.personality.draw_home()
        shot("home")
        ui.personality.milestone=50
        ui.personality.milestone_until=ui.personality.clock()+20
        ui.personality.draw_home()
        shot("home-milestone")
        ui.personality.milestone=0
        sim.send("entry.guided.val=1")
        sim.send("page entry")
        sim.send('tTicket.txt="MUSTER-006"')
        sim.send('tDevice.txt="Kaffeemühle"')
        ui.settings.page="entry"
        ui.text("tTicketView","MUSTER-006",34)
        ui.text("tDeviceView","Kaffeemaschine mit Milchtank",66)
        ui.workflow.draw_language()
        ui.tester.update_entry()
        shot("entry")
        sim.send("page guide")
        ui.settings.page="guide"
        for each in STEPS:
            procedure={"connect2":"II","class3":"III","iec":"IEC","extension":"Verlängerung"}.get(each,"I")
            ui.workflow.guide=Guide(step=each,procedure=procedure,
                                    mode="Netz" if procedure in ("I","II") else "Batterie",
                                    stored=each=="exam",observed="PASS")
            if each=="exam":
                ui.workflow.examiner_id=ui.picker.store.rename("Prüfperson Muster")
                sim.send('guide.eRemarks.txt="Visuell geprüft."')
            ui.workflow.draw_guide()
            shot("guide-"+each)
            ui.workflow.help=True
            ui.workflow.draw_guide()
            shot("guide-"+each+"-help")
            ui.workflow.help=False
        for state in ("start","low_continue","leak"):
            ui.workflow.guide=Guide(step=state,procedure="II")
            ui.workflow.draw_guide()
            shot("guide-"+state+"-class-ii")
        for mode in ("usb","rs232","file"):
            ui.settings.page="importer"
            sim.send("page importer")
            receiver.mode=mode
            receiver.status=ReceiverStatus("waiting",mode if mode in ("rs232","usb") else None)
            ui.workflow.baseline={}
            ui.workflow.begin_import()
            ui.workflow.poll()
            shot("import-"+mode)
        sim.send("page tester")
        ui.settings.page="tester"
        receiver.status=ReceiverStatus("waiting","usb")
        ui.measurements.import_bytes((ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_bytes(),"file-csv")
        ui.tester.review(["MUSTER-006","Kaffeemühle","033","0","0"])
        ui.tester.draw()
        shot("confirmation")
        for kind,original in examples(ui.measurements):
            report={**deepcopy(original),"language":language}
            ui.settings.page="report"
            ui.load_report(1,report)
            sim.send("page report")
            ui.draw_measurements(report)
            shot("result-"+kind)
            if kind in ("partial","exam-open"):
                ui.detail_page=1
                ui.draw_measurements(report)
                shot("result-"+kind+"-details")
                ui.detail_page=len(ui.report_details(report))
                ui.draw_measurements(report)
                shot("result-"+kind+"-protocol")
            preview=receipt(report,{"graphic":True,"density":"default","feed_mm":15})
            receipt_preview(preview).save(out/f"receipt/{kind}.png")
            (out/f"pdf/{kind}.pdf").write_bytes(render_pdf(report))
        for name in ("keyboard","qrpage","history","settings","wifi","wjoin","printer","receipt","system","power"):
            sim.send(f"page {name}")
            ui.settings.page=name
            if name in ("wifi","wjoin"):
                network=Network("/example",b"Repair Cafe Riehen",82,"WPA2","wpa-psk")
                ui.settings.networks=[network,Network("/guest",b"FMI Gast",55,"Offen","")]
                ui.settings.selected=network
                ui.settings.message("{count} Netze gefunden.",count=2)
            ui.settings.draw()
            if name=="qrpage":
                sim.send('qrReport.txt="http://192.168.1.42:8080/r/DEMO"')
                sim.send("qReady.val=1")
                ui.say("tNote","Mit dem Handy scannen. Handy und Station müssen im selben Netz sein.",100)
                sim.wait(200)
            elif name=="history":
                ui.refresh_history()
            elif name=="entry":
                ui.text("tStatus","Prüfnummer und Gerät eingeben.",100)
            shot(name)
            if name=="keyboard":
                for key,variant in (("bShift","upper"),("bMode","symbols"),("bMode","accents")):
                    sim.send(f"click {key},0")
                    shot("keyboard-"+variant)
        sim.send("page picker")
        ui.settings.page="picker"
        ui.picker.open("appliance")
        ui.picker.draw()
        shot("picker-appliances")
        ident=ui.picker.store.rename("Muster Fachperson")
        for name in ("Muster Person B","Muster Person C"):
            ui.picker.store.rename(name)
        ui.picker.open("people",ident)
        ui.picker.draw()
        shot("picker-examiners")
        ui.picker.note="Änderung mit «Bestätigen» übernehmen."
        ui.picker.confirm=ident
        ui.picker.draw()
        shot("picker-confirm-deactivation")
        sim.send("page pet")
        ui.settings.page="pet"
        ui.personality.pet_count=42
        ui.personality.pet_reply="Eine Pfote voller Dank."
        ui.personality.draw_pet()
        shot("pet")
        sim.send("page engineering")
        ui.settings.page="engineering"
        ui.personality.total_reports=55
        ui.personality.draw_diagnostic(((44.5,0.38,29,25,90600,True),
                                        (50,39,0),(42,(1,1475,0))))
        shot("engineering")
        sim.send("page power")
        ui.settings.page="power"
        ui.settings.power_note="Bis bald, Werkstattteam!"
        ui.settings.draw()
        shot("power-farewell")
        captured_pages={"home","entry","guide","importer","tester","report","picker",
                        "keyboard","qrpage","history","settings","wifi","wjoin","printer","receipt","system","power","pet","engineering"}
        assert captured_pages==set(PAGES)
        ui.close()
    images=sorted((out/"hmi").glob("*.png"))
    for start in range(0,len(images),24):
        group=images[start:start+24]
        sheet=Image.new("RGB",(1200,((len(group)+5)//6)*345),"#172431")
        draw=ImageDraw.Draw(sheet)
        for i,path in enumerate(group):
            x,y=i%6*200,i//6*345
            with Image.open(path) as screen:
                sheet.paste(screen.resize((192,320)),(x+4,y+3))
            draw.text((x+5,y+326),path.stem,fill="white")
        sheet.save(out/f"contact-hmi-{start//24+1}.png")


if __name__=="__main__":
    main()
