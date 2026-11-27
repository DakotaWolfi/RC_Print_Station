"""Read-only printer-port transport and explicit Linux UART ownership checks."""
import array
import fcntl
import os
from pathlib import Path
import re
import select
import subprocess
import termios

from benning_csv import ImportErrorDetail

ONBOARD = re.compile(r"tty(?:AMA|S)[0-9]+")


def text(path):
    try:
        return path.read_text().strip()
    except OSError:
        return ""


def onboard_reserved(path, *, proc=Path("/proc"), sys=Path("/sys"), run=subprocess.run):
    # /dev/console can be held via a different node. Check both kernel views.
    alias_names = {Path(path).name}
    for alias in ("/dev/serial0", "/dev/serial1"):
        if os.path.realpath(alias) == path:
            alias_names.add(Path(alias).name)
    configured = {part.removeprefix("console=").split(",",1)[0] for part in
                  text(proc/"cmdline").split() if part.startswith("console=")}
    if alias_names & (configured | set(text(sys/"class/tty/console/active").split())):
        return True
    for name in alias_names:
        unit = "serial-getty@"+name+".service"
        try:
            for option in ("is-active","is-enabled"):
                state = run(["systemctl",option,unit],capture_output=True,text=True,timeout=.9).stdout.strip()
                if state not in ("", "inactive", "failed", "disabled", "masked", "not-found"):
                    return True
        except (OSError, subprocess.SubprocessError):
            # Without reliable ownership information leave the configured port alone.
            return True
    return False


def occupied(path, *, proc=Path("/proc")):
    for process in proc.iterdir():
        if not process.name.isdecimal() or int(process.name)==os.getpid():
            continue
        try:
            for fd in (process/"fd").iterdir():
                try:
                    if os.readlink(fd)==path:
                        return True
                except OSError:
                    continue
        except OSError:
            continue
    return False


class PrintReceiver:
    """Only an O_RDONLY descriptor is retained. No modem control or byte writes."""
    def __init__(self, path):
        self.port = path
        real=os.path.realpath(path)
        if occupied(real):
            raise ImportErrorDetail("BENNING-Port ist bereits belegt.")
        fd = os.open(real, os.O_RDONLY | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.ioctl(fd, termios.TIOCEXCL)
            attrs = termios.tcgetattr(fd)
            attrs[:6] = [0, 0, termios.CLOCAL | termios.CREAD | termios.CS8, 0,
                         termios.B9600, termios.B9600]
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except BaseException:
            os.close(fd)
            raise
        self.fd = fd

    @property
    def in_waiting(self):
        size = array.array("i", [0])
        fcntl.ioctl(self.fd, termios.FIONREAD, size, True)
        return size[0]

    def read(self, size):
        readable, _, _ = select.select([self.fd], [], [], .2)
        if not readable:
            return b""
        try:
            data = os.read(self.fd, size)
        except BlockingIOError:
            return b""
        if not data:
            raise OSError("Serial port disconnected")
        return data

    def __enter__(self):
        return self

    def __exit__(self, *error):
        os.close(self.fd)
