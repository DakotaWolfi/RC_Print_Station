"""Render every guide state and sample reports from the production output code."""
import argparse
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
        elif data.startswith((b"\x1bt",b"\x1bE",b"\x1d!",b"\x1dV")):
            data=data[3:]
        elif data.startswith(b"\x1bJ"):
            y+=data[2]
            data=data[3:]
        elif data.startswith(b"\x1b@"):
            data=data[2:]
        else:
            line,sep,remainder=data.partition(b"\n")
            if any(byte<32 for byte in line):
                raise ValueError(f"Unexpected preview byte {line[:8]!r}")
            draw.text((width//2 if centred else 15,y+4),line.decode("cp850"),font=font,fill=0,
                      anchor="mt" if centred else "lt")
            data=remainder if sep else b""
            y+=26
    return paper.crop((0,0,width,y+12))


def examples(store):
    captured=(ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_text().splitlines()
    row=captured[2].split(";")
    examination={"visual":"Ohne Befund","functional":"Ohne Befund","examiner":"Prüfperson Muster",
                 "remarks":"Synthetischer Beleg zur Layoutprüfung.","status":"Erfasst"}
    for kind in ("PASS","FAIL","partial","unknown","simulation"):
        if kind=="simulation":
            yield kind,simulate("MUSTER-006","Kaffeemühle (Layoutmuster)")
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
        if kind=="unknown":
            report["record"]["verdict"]=None
            report["verdict"]=None
        yield kind,report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("directory",type=Path)
    out=p.parse_args().directory
    for name in ("hmi","receipt","pdf"):
        (out/name).mkdir(parents=True,exist_ok=True)
    sim=HeadlessSimulation(ROOT/"hmi/native")
    receiver=SimpleNamespace(mode="usb",status=ReceiverStatus("waiting","usb"),close=lambda:None)
    with tempfile.TemporaryDirectory() as tmp:
        ui=NativeUI(PreviewSerial(sim),"unused",Path(tmp)/"samples.sqlite3",tester_receiver=receiver)
        sim.send("home.online.val=1")
        sim.send('home.tLink.txt="Host verbunden"')
        def shot(name):
            (out/f"hmi/{name}.png").write_bytes(sim.screen()["png"])

        shot("home")
        sim.send("entry.guided.val=1")
        sim.send("page entry")
        sim.send('tTicket.txt="MUSTER-006"')
        sim.send('tDevice.txt="Kaffeemühle"')
        shot("entry")
        sim.send("page guide")
        ui.settings.page="guide"
        for each in STEPS:
            ui.workflow.guide=Guide(step=each,procedure="I",mode="Netz",stored=each=="exam")
            if each=="exam":
                sim.send('guide.eName.txt="Prüfperson Muster"')
                sim.send('guide.eRemarks.txt="Visuell geprüft."')
            ui.workflow.draw_guide()
            shot("guide-"+each)
            if each in ("connect1","connect2","iec","extension"):
                ui.workflow.help=True
                ui.workflow.draw_guide()
                shot("guide-"+each+"-help")
                ui.workflow.help=False
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
        ui.measurements.import_bytes((ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_bytes(),"file-csv")
        ui.tester.review(["MUSTER-006","Kaffeemühle","033","0","0"])
        ui.tester.draw()
        shot("confirmation")
        for kind,report in examples(ui.measurements):
            ui.settings.page="report"
            ui.load_report(1,report)
            sim.send("page report")
            ui.draw_measurements(report)
            shot("result-"+kind)
            preview=receipt(report,{"graphic":True,"density":"default","feed_mm":15})
            receipt_preview(preview).save(out/f"receipt/{kind}.png")
            (out/f"pdf/{kind}.pdf").write_bytes(render_pdf(report))
        ui.close()


if __name__=="__main__":
    main()
