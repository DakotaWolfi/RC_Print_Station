"""Linux connector/input discovery and optional Qt frontend supervisor."""
import argparse
from dataclasses import dataclass
import json
import logging
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
from threading import Event
from time import monotonic

from station_ipc import DEFAULT_SOCKET


LOG=logging.getLogger(__name__)
MODES=("auto","nextion","hdmi","both","headless")
GRAPHICS=("linuxfb","eglfs","wayland","xcb","offscreen")
MATRIX={
    0:"1 0 0 0 1 0",
    90:"0 -1 1 1 0 0",
    180:"-1 0 1 0 -1 1",
    270:"0 1 0 -1 0 1",
}


@dataclass(frozen=True)
class Connector:
    name: str
    connected: bool
    modes: tuple


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def connectors(root=Path("/sys/class/drm")):
    result=[]
    for port in sorted(Path(root).glob("card*-*")):
        if "-HDMI-" not in port.name and "-DP-" not in port.name:
            continue
        status=read(port/"status")
        if status not in ("connected","disconnected"):
            continue
        modes=tuple(mode for mode in read(port/"modes").splitlines() if re.fullmatch(r"\d{2,5}x\d{2,5}",mode))
        result.append(Connector(port.name.split("-",1)[1],status=="connected",modes))
    return result


def bits(value):
    # ARM64 and x86-64 sysfs list machine words, most significant first.
    return int("".join(part.zfill(16) for part in value.split()),16) if value else 0


def touchscreens(root=Path("/sys/class/input"), udev=Path("/run/udev/data")):
    result=[]
    for event in sorted(Path(root).glob("event*")):
        identity=read(event/"dev")
        props=dict(line[2:].split("=",1) for line in read(Path(udev)/("c"+identity)).splitlines()
                   if line.startswith("E:") and "=" in line)
        if props.get("ID_INPUT_TOUCHSCREEN")=="1":
            result.append("/dev/input/"+event.name)
            continue
        # Fallback requires direct input and absolute position, never generic HID.
        try:
            dev=event/"device"
            direct=bits(read(dev/"properties")) & (1<<1)
            axes=bits(read(dev/"capabilities/abs"))
            xy=axes & 3 == 3
            multitouch=axes & ((1<<53)|(1<<54)) == ((1<<53)|(1<<54))
            if direct and (xy or multitouch):
                result.append("/dev/input/"+event.name)
        except ValueError:
            continue
    return tuple(result)


def inspect(*, drm=Path("/sys/class/drm"), input_root=Path("/sys/class/input"),
            udev=Path("/run/udev/data"), env=os.environ, connector="", force=False):
    ports=[p for p in connectors(drm) if not connector or p.name==connector]
    active=next((p for p in ports if p.connected),None)
    has_drm=bool(ports) or bool(connector)
    # Session sockets and fb0 are fallback signals when DRM cannot report.
    fallback=bool(env.get("WAYLAND_DISPLAY") or env.get("DISPLAY") or Path("/dev/fb0").exists())
    return {"available":bool(active or force or not has_drm and fallback),
            "connector":active.name if active else connector,"modes":active.modes if active else (),
            "touch":touchscreens(input_root,udev),"drm":has_drm}


def qt_environment(backend,rotation,touch_device="",environ=os.environ):
    env=dict(environ)
    env["QT_QPA_PLATFORM"]=backend
    if backend in ("linuxfb","eglfs"):
        if touch_device:
            env["QT_QPA_EGLFS_NO_LIBINPUT"]="1"
            env["QT_QPA_FB_NO_LIBINPUT"]="1"
            env["QT_QPA_EVDEV_TOUCHSCREEN_PARAMETERS"]=touch_device
    return env


def supervise(args, stop, detection=inspect, launch=subprocess.Popen):
    child=None
    previous=None
    retry=0
    delay=1
    root=Path(__file__).resolve().parent
    try:
        while not stop.is_set():
            status=detection(connector=args.connector,force=args.force)
            fingerprint=(status["connector"],status["modes"])
            # The linuxfb and eglfs evdev plugins normally detect devices via udev.
            # A pinned device benefits from a relaunch when it is present again.
            if args.touch:
                fingerprint+= (args.touch in status["touch"],)
            if child and (not status["available"] or fingerprint!=previous):
                terminate(child)
                child=None
                retry=0
            if child and child.poll() is not None:
                LOG.warning("HDMI frontend exited, retry in %ss",delay)
                child=None
                retry=monotonic()+delay
                delay=min(delay*2,20)
            if child and monotonic()-started>20:
                delay=1
            if status["available"] and not child and monotonic()>=retry:
                command=["/usr/bin/python3",str(root/"hdmi_frontend.py"),"--socket",args.socket,"--rotation",str(args.rotation)]
                if status["connector"] and args.backend in ("xcb","wayland"):
                    command+=["--screen",status["connector"]]
                if args.touch:
                    command+=["--touch-device",args.touch]
                if args.window:
                    command+=["--window"]
                LOG.info("Starting HDMI (%s, modes=%s, touchscreen=%d)",args.backend,
                         ",".join(status["modes"]),len(status["touch"]))
                try:
                    child=launch(command,env=qt_environment(args.backend,args.rotation,args.touch))
                except OSError as error:
                    LOG.warning("HDMI launch failed (%s)",type(error).__name__)
                    retry=monotonic()+delay
                    delay=min(delay*2,20)
                previous=fingerprint
                started=monotonic()
            stop.wait(1.5)
    finally:
        if child:
            terminate(child)


def terminate(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=2)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode",choices=MODES,default="auto")
    p.add_argument("--backend",choices=GRAPHICS,default="linuxfb")
    p.add_argument("--rotation",type=int,choices=tuple(MATRIX),default=0)
    p.add_argument("--touch",default="")
    p.add_argument("--connector",default="")
    p.add_argument("--force",action="store_true")
    p.add_argument("--window",action="store_true")
    p.add_argument("--inspect",action="store_true")
    p.add_argument("--socket",default=DEFAULT_SOCKET)
    a=p.parse_args()
    logging.basicConfig(level=logging.INFO)
    if a.inspect:
        print(json.dumps(inspect(connector=a.connector,force=a.force),indent=2))
        return
    if a.mode in ("headless","nextion"):
        return
    stop=Event()
    for kind in (signal.SIGTERM,signal.SIGINT):
        signal.signal(kind,lambda *_:stop.set())
    supervise(a,stop)


if __name__=="__main__":
    main()
