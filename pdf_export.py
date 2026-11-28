"""Shared PDF download naming and an exclusive, atomic local export."""
from datetime import date, datetime
from pathlib import Path
import os
import re
import tempfile
from unicodedata import normalize
from zoneinfo import ZoneInfo


def pdf_filename(report, identifier):
    record=report.get("record") or {}
    stamp=record.get("iso_date")
    try:
        day=date.fromisoformat(stamp).isoformat()
    except (ValueError,TypeError):
        try:
            day=datetime.fromisoformat(report.get("created","")).astimezone(ZoneInfo("Europe/Zurich")).date().isoformat()
        except (ValueError,TypeError):
            day="undated"
    text=normalize("NFKD",str(report.get("ticket",""))).encode("ascii","ignore").decode()
    ticket=re.sub(r"[^a-zA-Z0-9_-]+","-",text).strip("-_")[:38] or "ticket"
    ident=re.sub(r"[^a-zA-Z0-9]+","",str(identifier))[:32]
    return f"FMI-{day}-{ticket}-R{ident}.pdf"


def save_pdf(directory,report,ident):
    from report_web import render_pdf

    directory=Path(directory)
    directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    name=pdf_filename(report,ident)
    data=render_pdf(report)
    fd,temp=tempfile.mkstemp(prefix=".fmi-pdf-",dir=directory)
    try:
        with os.fdopen(fd,"wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        stem=Path(name).stem
        for n in range(100):
            dest=directory/(name if n==0 else f"{stem}-{n+1}.pdf")
            try:
                # A hard link never overwrites, and exposes only a complete PDF.
                os.link(temp,dest)
                return dest
            except FileExistsError:
                continue
        raise FileExistsError(name)
    finally:
        Path(temp).unlink(missing_ok=True)
