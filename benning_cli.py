"""Independent BENNING diagnostic and file importer. Uses no printer or HMI."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import time

from benning_csv import ImportErrorDetail, MAX_BYTES, validate_encoding
from benning_receiver import Receiver, choose_port
from benning_store import Measurements


def read_bounded(path):
    with Path(path).open("rb") as stream:
        data=stream.read(MAX_BYTES+1)
    if len(data)>MAX_BYTES:
        raise ImportErrorDetail("Datei ist zu gross.")
    return data


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",default="benning-diagnostic.sqlite3")
    p.add_argument("--encoding",default="auto")
    sub=p.add_subparsers(dest="command",required=True)
    for name in ("detect","listen"):
        cmd=sub.add_parser(name)
        cmd.add_argument("--mode",choices=("auto","usb","rs232"),default="auto")
        cmd.add_argument("--usb-device")
        cmd.add_argument("--rs232-device")
        cmd.add_argument("--gpio-rx",action="store_true",help="Explicit onboard RS232 RX converter")
        cmd.add_argument("--hmi-port",default="/dev/serial0")
        if name=="listen":
            cmd.add_argument("--idle",type=float,default=1.8)
            cmd.add_argument("--capture",type=Path,help="Save first framed capture, without overwriting")
            cmd.add_argument("--once",action="store_true")
            cmd.add_argument("--timeout",type=float,default=0,help="Exit after N seconds (0 waits)")
            cmd.add_argument("--accept-memory-reset",action="store_true",
                             help="Accept one shorter USB snapshot after intentional memory erasure")
    ingest=sub.add_parser("import")
    ingest.add_argument("--format",choices=("csv","txt"),required=True)
    ingest.add_argument("file")
    browse=sub.add_parser("slots")
    browse.add_argument("--source",choices=("usb","rs232","file-csv","file-txt"),default="usb")
    args=p.parse_args()
    try:
        encoding=validate_encoding(args.encoding)
        db=Measurements(args.db)
        if args.command=="detect":
            selected=choose_port(args.mode,args.usb_device,args.rs232_device,hmi=args.hmi_port,gpio=args.gpio_rx)
            print(json.dumps(selected))
            return 0 if selected else 1
        if args.command=="import":
            result=db.import_bytes(read_bounded(args.file),"file-"+args.format,encoding)
            print(json.dumps(asdict(result),ensure_ascii=False))
            return 0
        if args.command=="slots":
            for item in db.slots(args.source):
                r=item["original"]
                print(item["slot"],r["tester_date"],r["verdict"],item["record_id"])
            return 0
        captured=False
        def capture(data):
            nonlocal captured
            if args.capture and not captured:
                fd=os.open(args.capture,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,"wb") as stream:
                    stream.write(data)
                captured=True

        rx=Receiver(db,args.mode,args.usb_device,args.rs232_device,encoding,args.idle,
                    args.hmi_port,gpio=args.gpio_rx,raw_capture=capture,accept_reset=args.accept_memory_reset)
        rx.start()
        previous=None
        start=time.monotonic()
        try:
            while not args.timeout or time.monotonic()-start<args.timeout:
                status=rx.status
                if status!=previous:
                    print(json.dumps(asdict(status),ensure_ascii=False),flush=True)
                    if status.state=="imported":
                        print(json.dumps(db.latest((status.source,)),ensure_ascii=False),flush=True)
                    if args.once and status.state in ("imported","error","interrupted"):
                        return 0 if status.state=="imported" else 1
                    previous=status
                time.sleep(.1)
            return 1
        finally:
            rx.close()
    except (ImportErrorDetail,ImportError,OSError,ValueError) as exc:
        p.exit(1,f"BENNING: {exc}\n")
    except KeyboardInterrupt:
        return 130


if __name__=="__main__":
    raise SystemExit(main())
