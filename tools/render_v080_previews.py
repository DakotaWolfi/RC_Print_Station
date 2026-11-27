"""Render responsive Qt screens and preserve production report examples."""
from argparse import ArgumentParser
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from PyQt5.QtWidgets import QApplication

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benning_receiver import ReceiverStatus
from hdmi_frontend import Surface
from report_web import render_pdf
from slogan_store import SloganStore
from station_core import StationCore
from station import receipt


def fixture(path):
    receiver=SimpleNamespace(mode="file",status=ReceiverStatus("file"),
                             start=lambda:None,close=lambda:None)
    core=StationCore(path/"reports.sqlite3",receiver=receiver,config_path=path/"options.json",
                     cache=SloganStore(path/"slogans.sqlite3"))
    raw=(ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_bytes()
    core.store.import_bytes(raw,"file-csv")
    core.refresh_import()
    return core


def run(core,op,**args):
    result=core.command({"op":op,"args":args})
    if not result["ok"]:
        raise RuntimeError(result["error"])
    return result["data"]


def ref(core,**args):
    return dict(draft=core.draft["id"],version=core.draft["version"],**args)


def showcase(core,lang):
    core.draft=None
    run(core,"settings.save",values={"language":lang})
    yield "home",core.snapshot(),None
    run(core,"draft.new",mode="guided")
    run(core,"draft.edit",**ref(core,changes={"ticket":"DEMO-V080-042","device":"BENCH SAMPLE - recorded test data"},
                                previous={"ticket":"","device":""}))
    yield "entry",core.snapshot(),None
    run(core,"exam.start",**ref(core))
    for step,index in (("visual",0),("kind",0),("connect1",0)):
        run(core,"guide.choose",**ref(core,step=step,choice=index))
    yield "guide",core.snapshot(),None
    run(core,"guide.choose",**ref(core,step="start",choice=1))
    yield "warning",core.snapshot(),None
    for step,index in (("leak",0),("energise",3),("save",0)):
        run(core,"guide.choose",**ref(core,step=step,choice=index))
    examiner=run(core,"person.save",name="FMI Bench")
    run(core,"person.pick",**ref(core,examiner=examiner))
    run(core,"exam.function",**ref(core,value="Ohne Befund"))
    run(core,"exam.submit",**ref(core))
    yield "import",core.snapshot(),None
    run(core,"review.manual",**ref(core))
    row=next(row for row in core.slots if row["original"]["protection_class"]=="Klasse I")
    run(core,"review.select",**ref(core,record=list(core.identity(row))))
    yield "review",core.snapshot(),None
    run(core,"review.confirm",**ref(core,record=list(core.identity(row))))
    yield "report",core.snapshot(),core.report


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("output",type=Path)
    args=p.parse_args()
    app=QApplication([])
    with TemporaryDirectory() as directory:
        core=fixture(Path(directory))
        try:
            for lang in ("de","en"):
                scenes=list(showcase(core,lang))
                for w,h in ((800,480),(480,800),(1024,600),(600,1024)):
                    target=args.output/lang/f"{w}x{h}"
                    target.mkdir(parents=True,exist_ok=True)
                    for name,state,report in scenes:
                        win=Surface(preview=True)
                        win.resize(w,h)
                        win.show()
                        win.loaded_report=state.get("report") if report else None
                        win.report=report
                        win.show_state(state)
                        app.processEvents()
                        win.grab().save(str(target/f"{name}.png"))
                        win.close()
                        app.processEvents()
                target=args.output/lang
                report=scenes[-1][-1]
                (target/"DEMO-Class-I.pdf").write_bytes(render_pdf(report))
                (target/"DEMO-Class-I.escpos").write_bytes(receipt(report,{"graphic":True,"feed_mm":45,"density":"default"}))
        finally:
            core.close()


if __name__=="__main__":
    main()
