"""Report host PSS, peak RSS and elapsed time for bounded demo scenarios."""
from argparse import ArgumentParser
import json
from pathlib import Path
import resource
import sys
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from benning_receiver import ReceiverStatus
from nextion_adapter import NextionAdapter
from report_web import render_pdf
from slogan_store import SloganStore
from station_core import StationCore
from station import receipt


def pss_mib():
    try:
        for line in Path("/proc/self/smaps_rollup").read_text().splitlines():
            if line.startswith("Pss:"):
                return round(int(line.split()[1])/1024,2)
    except OSError:
        return None


def main():
    p=ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("headless","nextion","hdmi","both","guided","import","receipt","pdf","pet"))
    args=p.parse_args()
    start,cpu=perf_counter(),process_time()
    serial=SimpleNamespace(write=len,flush=lambda:None)
    with TemporaryDirectory() as tmp:
        directory=Path(tmp)
        r=SimpleNamespace(mode="file",status=ReceiverStatus("file"),start=lambda:None,close=lambda:None)
        core=StationCore(directory/"reports.sqlite3",receiver=r,cache=SloganStore(directory/"slogans.sqlite3"),
                         config_path=directory/"settings.json")
        adapter=None
        surface=None
        try:
            if args.mode in ("nextion","both"):
                adapter=NextionAdapter(core,serial)
                adapter.connect_panel()
                adapter.handle(b"\x66\x00")
                adapter.sync()
            if args.mode in ("hdmi","both","guided","pet"):
                from PyQt5.QtWidgets import QApplication
                from hdmi_frontend import Surface
                app=QApplication([])
                surface=Surface(preview=True)
                surface.resize(800,480)
                surface.show()
            if args.mode in ("guided","import","receipt","pdf"):
                core.command({"op":"draft.new","args":{"mode":"guided"}})
                draft=core.draft
                ref={"draft":draft["id"],"version":draft["version"]}
                core.command({"op":"draft.edit","args":dict(ref,previous={"ticket":"","device":""},
                                                           changes={"ticket":"DEMO","device":"Bench sample"})})
                ref["version"]=draft["version"]
                core.command({"op":"exam.start","args":ref})
            if args.mode in ("import","receipt","pdf"):
                captured=(ROOT/"tests/fixtures/benning_usbcsv_examples.txt").read_bytes()
                core.store.import_bytes(captured,"file-csv")
                core.refresh_import()
                if args.mode!="import":
                    ident,report=core.store.create_report("DEMO","Bench sample","Eingangsprüfung",core.slots[0])
                    receipt(report) if args.mode=="receipt" else render_pdf(report)
            if surface:
                if args.mode=="pet":
                    surface.view="pet"
                surface.show_state(core.snapshot())
                app.processEvents()
                surface.grab()
            delta=perf_counter()-start
            print(json.dumps({"mode":args.mode,"elapsed_ms":round(delta*1000,1),
                              "cpu_ms":round((process_time()-cpu)*1000,1),
                              "pss_mib":pss_mib(),
                              "peak_rss_mib":round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,2)}))
        finally:
            if surface:
                surface.close()
            if adapter:
                adapter.close()
            core.close()


if __name__=="__main__":
    main()
