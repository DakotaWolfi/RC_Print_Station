#!/usr/bin/env python3
"""Set the local fallback hotspot password without command-line disclosure."""
import argparse
from getpass import getpass
import os
from pathlib import Path
import tempfile

DEFAULT=Path.home()/".config/rc-printstation/hotspot.psk"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file",type=Path,default=DEFAULT)
    args=parser.parse_args()
    password=getpass("Hotspot password (12–63 printable ASCII characters): ")
    if not 12<=len(password)<=63 or not all(32<=ord(c)<127 for c in password):
        parser.error("Invalid password length or characters")
    if password!=getpass("Repeat password: "):
        parser.error("Passwords differ")
    path=args.file
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    fd,temp=tempfile.mkstemp(prefix=".hotspot-",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="ascii") as out:
            out.write(password+"\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp,path)
    finally:
        Path(temp).unlink(missing_ok=True)


if __name__=="__main__":
    main()
