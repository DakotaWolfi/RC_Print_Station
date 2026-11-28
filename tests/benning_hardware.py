"""Original BENNING ST 725 bytes from the v0.8.4 bench captures."""
from base64 import b64decode
from pathlib import Path
import json

FIXTURES=Path(__file__).parent/"fixtures"
BUNDLE=[json.loads(line) for line in (FIXTURES/"benning-st725-hardware.jsonl").read_text().splitlines()]
RAW={(row["source"],row["slot"]):b64decode(row["raw_b64"],validate=True) for row in BUNDLE}
USB_DUMP=b64decode((FIXTURES/"benning-st725-usb-hexdump.b64").read_bytes())
USB_COMPLETE=USB_DUMP[:USB_DUMP.rindex(b"\r\n")+2]
USB_HEADER=USB_DUMP.split(b"\r\n",1)[0]+b"\r\n"
USB_41=USB_HEADER+b"".join(RAW["usb",f"{slot:03d}"] for slot in range(1,42))
