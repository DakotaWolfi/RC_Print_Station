"""One atomic configuration shared by the native panel and loopback admin."""
import fcntl
from ipaddress import IPv4Address
import json
import os
from pathlib import Path
import tempfile

CONFIG = Path.home()/".config"/"rc-printstation"/"receipt.json"
PRINTER_HOST = "169.254.25.23"
PRINTER_PORT = 9100
DEFAULTS = dict(language="de", professional=False, graphic=True, feed_mm=45, density="default", brightness=100, standby=0)
DENSITIES = {"default": None, "light": 255, "dark": 1}


def validated(key, value):
    if key == "tester_mode" and value in ("auto","usb","rs232","file","simulation"):
        return value
    if key == "language" and value in ("de","en"):
        return value
    if key in ("graphic","professional") and type(value) is bool:
        return value
    if key == "density" and isinstance(value,str) and value in DENSITIES:
        return value
    if key == "printer_host":
        ip = IPv4Address(value)
        if ip.is_unspecified or ip.is_multicast or ip.is_loopback or int(ip)==0xffffffff:
            raise ValueError("Bitte eine gültige Drucker-IPv4-Adresse eingeben.")
        return str(ip)
    bounds = {"feed_mm": (0,100), "printer_port": (1,65535),
              "brightness": (10,100), "standby": (0,3600)}
    if key in bounds and type(value) is int and bounds[key][0] <= value <= bounds[key][1]:
        if key != "standby" or value == 0 or value >= 10:
            return value
    raise ValueError("Wert ausserhalb des erlaubten Bereichs.")


def raw(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(data,dict):
        raise ValueError("Ungültige Einstellungsdatei.")
    return data


def load(path=None):
    result = DEFAULTS.copy()
    try:
        data = raw(path or CONFIG)
    except (OSError,ValueError):
        return result
    for key,value in data.items():
        try:
            result[key] = validated(key,value)
        except (ValueError,TypeError):
            continue
    return result


def save(updates,path=None):
    data = {key: validated(key,value) for key,value in updates.items()}
    path = path or CONFIG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous = raw(path)
        previous.update(data)
        fd,tmp = tempfile.mkstemp(prefix=".receipt-",dir=path.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as file:
                json.dump(previous,file)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(tmp,path)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return load(path)
