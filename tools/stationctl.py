"""Inspect or operate a station over its private local socket."""
import argparse
import getpass
import json
from pathlib import Path
import sys
from uuid import uuid4

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from station_ipc import DEFAULT_SOCKET, request


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket",default=DEFAULT_SOCKET)
    parser.add_argument("command",help="Semantic command, such as state or history")
    parser.add_argument("arguments",nargs="?",default="{}",help="One JSON object")
    parser.add_argument("--read-wifi-password",action="store_true")
    args=parser.parse_args()
    data=json.loads(args.arguments)
    if not isinstance(data,dict):
        parser.error("Command arguments must be a JSON object")
    if args.read_wifi_password:
        if args.command!="wifi.connect":
            parser.error("Password input is only available with wifi.connect")
        data["password"]=getpass.getpass("Wi-Fi password: ")
    elif "password" in data:
        parser.error("Use --read-wifi-password to keep credentials out of the shell history")
    result=request(args.socket,{"op":args.command,"args":data,"id":uuid4().hex,"client":"stationctl"})
    sys.stdout.write(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    return 0 if result["ok"] else 1


if __name__=="__main__":
    raise SystemExit(main())
