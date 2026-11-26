"""Resolve service fallbacks while preserving an explicitly configured endpoint."""
import argparse
from pathlib import Path
import shlex
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from station_config import PRINTER_HOST, PRINTER_PORT, validated

OBSOLETE_FALLBACK = "169.254.223.252"


def resolve(unit, host=None, port=None):
    previous={}
    try:
        lines=Path(unit).read_text().splitlines()
    except FileNotFoundError:
        lines=[]
    for line in lines:
        if not line.startswith("ExecStart="):
            continue
        parts=shlex.split(line.partition("=")[2])
        if not any(arg.endswith("/native_ui.py") or arg=="native_ui.py" for arg in parts):
            continue
        for arg in ("--host","--printer-port"):
            for idx,value in enumerate(parts):
                if value==arg and idx+1<len(parts):
                    previous[arg]=parts[idx+1]
                elif value.startswith(arg+"="):
                    previous[arg]=value.partition("=")[2]
    old_host=previous.get("--host")
    if old_host==OBSOLETE_FALLBACK:
        old_host=None
    return (validated("printer_host",host or old_host or PRINTER_HOST),
            validated("printer_port",int(port or previous.get("--printer-port") or PRINTER_PORT)))


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("unit")
    p.add_argument("host")
    p.add_argument("port")
    args=p.parse_args()
    try:
        print(*resolve(args.unit,args.host,args.port))
    except (ValueError,OSError) as exc:
        p.exit(2,f"Invalid printer endpoint: {exc}\n")
