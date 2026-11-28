"""Render compact receipts using genuine hardware captures and one synthetic failure."""
import argparse
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/"tests")]
from benning_hardware import RAW, USB_COMPLETE
from benning_store import Measurements, PHASES
from examination_rules import validate_selection
from report_web import render_pdf
from station import receipt
from render_v06_previews import receipt_preview


def render(folder):
    folder.mkdir(parents=True,exist_ok=True)
    mono="/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
    synthetic=RAW["rs232","044"].replace(b"Kabelpr\x81fung  Gut",b"Kabelpr\x81fung  OPEN")
    synthetic=synthetic.replace(b"Pr\x81fergebnis   Bestanden",b"Pr\x81fergebnis   Nicht bestanden")
    samples=[
        ("class-I-pass-en","rs232","011","en",False),
        ("class-I-early-fail-de","usb","040","de",False),
        ("class-II-pass-de","rs232","001","de",False),
        ("class-II-fail-en","usb","041","en",False),
        ("cable-pass-de","rs232","044","de",False),
        ("cable-fail-synthetic-en","rs232","044","en",True),
    ]
    with TemporaryDirectory() as tmp:
        store=Measurements(Path(tmp)/"fixtures.db")
        store.import_bytes(USB_COMPLETE,"usb")
        for slot in ("011","001","044"):
            store.import_bytes(RAW["rs232",slot],"rs232")
        for label,source,slot,language,mutated in samples:
            if mutated:
                store.import_bytes(synthetic,source)
            row=next(row for row in store.slots(source) if row["slot"]==slot)
            _,report=store.create_report("FIXTURE-084","SYNTHETIC CABLE FAILURE" if mutated else "BENNING bench capture",
                                         PHASES[0],row,language=language)
            job=receipt(report,{"graphic":True,"density":"default","feed_mm":30})
            receipt_preview(job,mono).save(folder/f"{label}.png")
            if label.startswith("cable"):
                (folder/f"{label}.pdf").write_bytes(render_pdf(report))
        row=next(row for row in store.slots("usb") if row["slot"]=="033")
        exam=validate_selection({"procedure":"I","observed":"PASS","voltage_confirmed":500},
                                row["original"],"usb",resolution="adopt")
        _,report=store.create_report("FIXTURE-084","Class mismatch bench capture",PHASES[0],row,examination=exam)
        (folder/"class-mismatch-de.pdf").write_bytes(render_pdf(report))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    render(parser.parse_args().output)
